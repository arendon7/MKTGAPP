import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CloudSocialWorkerDatabaseClockTests(unittest.TestCase):
    def test_execution_rpcs_use_database_clock_for_lease_authority(self):
        sql = (ROOT / "gateway" / "supabase" / "003_social_worker_execution.sql").read_text(encoding="utf-8")
        self.assertGreaterEqual(sql.count("v_now timestamptz := clock_timestamp()"), 4)
        self.assertIn("q.lease_expires_at <= v_now", sql)
        self.assertIn("q.lease_expires_at > v_now", sql)
        self.assertIn("q.available_at <= v_now", sql)
        self.assertIn("expiry := v_now + make_interval", sql)
        self.assertIn("power(2, greatest(0, current_row.attempts - 1))", sql)

    def test_wire_compatibility_parameter_is_not_used_as_lease_clock(self):
        sql = (ROOT / "gateway" / "supabase" / "003_social_worker_execution.sql").read_text(encoding="utf-8")
        # Keep the existing p_now RPC argument so the deployed adapter does not require
        # a synchronized signature migration, but never compare lease state against it.
        self.assertIn("p_now timestamptz", sql)
        forbidden = (
            "lease_expires_at <= p_now",
            "lease_expires_at > p_now",
            "available_at <= p_now",
            "provider_started_at = p_now",
            "updated_at = p_now",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, sql)


if __name__ == "__main__":
    unittest.main()
