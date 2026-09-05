import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RemoteSocialQueueAtomicSqlTests(unittest.TestCase):
    def test_claim_is_atomic_skip_locked_and_uses_hashed_one_time_lease(self):
        sql = (ROOT / "gateway" / "supabase" / "002_social_publish_queue.sql").read_text(encoding="utf-8").lower()
        self.assertIn("binario_claim_social_publish_jobs", sql)
        self.assertIn("for update skip locked", sql)
        self.assertIn("gen_random_bytes(32)", sql)
        self.assertIn("digest(raw_token, 'sha256')", sql)
        self.assertIn("status = 'leased'", sql)
        self.assertIn("attempts = q.attempts + 1", sql)
        self.assertIn("lease_expires_at", sql)

    def test_claim_rpc_is_service_role_only(self):
        sql = (ROOT / "gateway" / "supabase" / "002_social_publish_queue.sql").read_text(encoding="utf-8").lower()
        signature = "function public.binario_claim_social_publish_jobs(text,text,timestamptz,integer,integer)"
        self.assertIn(f"revoke all on {signature} from public, anon, authenticated", sql)
        self.assertIn(f"grant execute on {signature} to service_role", sql)
        self.assertIn("security definer", sql)
        self.assertIn("set search_path = public", sql)

    def test_expired_leases_fail_closed_after_attempt_cap(self):
        sql = (ROOT / "gateway" / "supabase" / "002_social_publish_queue.sql").read_text(encoding="utf-8").lower()
        self.assertIn("case when q.attempts >= 5 then 'failed' else 'pending' end", sql)
        self.assertIn("worker lease expired before completion", sql)
        self.assertIn("q.attempts < 5", sql)


if __name__ == "__main__":
    unittest.main()
