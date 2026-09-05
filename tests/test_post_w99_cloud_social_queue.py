import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from gateway.core import Conflict
from gateway.social_queue import (
    MAX_ATTEMPTS,
    MemorySocialQueueStorage,
    REMOTE_SOCIAL_JOB_SCHEMA,
    RemoteSocialQueueService,
    SocialQueueError,
    validate_remote_social_job,
)


ROOT = Path(__file__).resolve().parents[1]
TENANT = "tenant_" + "a" * 24
PUB = "1" * 32
NOW = datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)


def body(*, publication_id=PUB, channel="facebook_page", kind="text", scheduled=None, **overrides):
    publication = {
        "id": publication_id,
        "project_id": "company_greenatics",
        "channel": channel,
        "target_id": "page-1" if channel == "facebook_page" else "ig-1",
        "target_name": "Greenatics",
        "kind": kind,
        "message": "Contenido aprobado",
        "link_url": None,
        "media_url": None,
        "scheduled_for": (scheduled or (NOW + timedelta(minutes=5))).isoformat(),
    }
    publication.update(overrides)
    payload = {
        "schema": REMOTE_SOCIAL_JOB_SCHEMA,
        "publication": publication,
        "approval": {"source_status": "QUEUED", "operator_approved": True},
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class RemoteSocialJobValidationTests(unittest.TestCase):
    def test_facebook_text_normalizes_as_secret_free_queued_approval(self):
        payload = validate_remote_social_job(body(), now=NOW)
        self.assertEqual(payload["publication"]["id"], PUB)
        self.assertEqual(payload["publication"]["channel"], "facebook_page")
        self.assertEqual(payload["approval"], {"source_status": "QUEUED", "operator_approved": True})
        self.assertIsNone(payload["publication"]["media_url"])

    def test_instagram_reel_requires_public_https_media(self):
        payload = validate_remote_social_job(
            body(channel="instagram", kind="reel", media_url="https://cdn.example.com/reel.mp4"),
            now=NOW,
        )
        self.assertEqual(payload["publication"]["kind"], "reel")
        for invalid in ("file:///tmp/reel.mp4", "http://cdn.example.com/reel.mp4", "/tmp/reel.mp4", ""):
            with self.subTest(invalid=invalid), self.assertRaises(SocialQueueError):
                validate_remote_social_job(body(channel="instagram", kind="reel", media_url=invalid), now=NOW)

    def test_cloud_facebook_rejects_local_reel_and_unapproved_jobs(self):
        with self.assertRaisesRegex(SocialQueueError, "cloud Facebook v1"):
            validate_remote_social_job(body(kind="reel", media_url="https://cdn.example.com/reel.mp4"), now=NOW)
        raw = json.loads(body().decode("utf-8"))
        raw["approval"]["operator_approved"] = False
        with self.assertRaisesRegex(SocialQueueError, "explicitly approved"):
            validate_remote_social_job(json.dumps(raw).encode("utf-8"), now=NOW)

    def test_secret_bearing_fields_fail_closed_at_any_depth(self):
        raw = json.loads(body().decode("utf-8"))
        raw["publication"]["metadata"] = {"access_token": "never-store"}
        with self.assertRaisesRegex(SocialQueueError, "secret-bearing"):
            validate_remote_social_job(json.dumps(raw).encode("utf-8"), now=NOW)
        raw = json.loads(body().decode("utf-8"))
        raw["approval"]["authorization"] = "Bearer secret"
        with self.assertRaisesRegex(SocialQueueError, "secret-bearing"):
            validate_remote_social_job(json.dumps(raw).encode("utf-8"), now=NOW)

    def test_schedule_requires_timezone_and_is_bounded(self):
        with self.assertRaisesRegex(SocialQueueError, "timezone"):
            validate_remote_social_job(body(scheduled=datetime(2026, 9, 6, 10, 0)), now=NOW)
        with self.assertRaisesRegex(SocialQueueError, "too far"):
            validate_remote_social_job(body(scheduled=NOW + timedelta(days=400)), now=NOW)


class RemoteSocialQueueStateTests(unittest.TestCase):
    def setUp(self):
        self.storage = MemorySocialQueueStorage()
        self.service = RemoteSocialQueueService(self.storage)

    def test_enqueue_is_idempotent_but_same_id_changed_payload_conflicts(self):
        status, receipt = self.service.enqueue(TENANT, body(), now=NOW)
        self.assertEqual(status, 202)
        self.assertFalse(receipt["idempotent_reuse"])
        status, receipt = self.service.enqueue(TENANT, body(), now=NOW)
        self.assertEqual(status, 200)
        self.assertTrue(receipt["idempotent_reuse"])
        with self.assertRaises(Conflict):
            self.service.enqueue(TENANT, body(message="Contenido cambiado"), now=NOW)

    def test_future_job_is_not_claimed_before_due(self):
        self.service.enqueue(TENANT, body(scheduled=NOW + timedelta(hours=1)), now=NOW)
        leases = self.service.claim_due(TENANT, "worker_0123456789abcdef", now=NOW, lease_seconds=60)
        self.assertEqual(leases, [])
        leases = self.service.claim_due(TENANT, "worker_0123456789abcdef", now=NOW + timedelta(hours=1), lease_seconds=60)
        self.assertEqual(len(leases), 1)

    def test_claim_uses_ephemeral_token_and_only_valid_lease_can_publish(self):
        self.service.enqueue(TENANT, body(scheduled=NOW), now=NOW)
        with patch("gateway.social_queue.secrets.token_hex", return_value="b" * 64):
            lease = self.service.claim_due(TENANT, "worker_0123456789abcdef", now=NOW, lease_seconds=60)[0]
        row = self.storage.get(TENANT, PUB)
        self.assertEqual(row.status, "LEASED")
        self.assertNotEqual(row.lease_sha256, lease["lease_token"])
        self.assertNotIn(lease["lease_token"], json.dumps(row.payload))
        with self.assertRaisesRegex(Conflict, "token mismatch"):
            self.service.mark_published(TENANT, PUB, "wrong-token", "remote-1", now=NOW + timedelta(seconds=10))
        done = self.service.mark_published(TENANT, PUB, lease["lease_token"], "remote-1", now=NOW + timedelta(seconds=10))
        self.assertEqual(done.status, "PUBLISHED")
        self.assertEqual(done.remote_id, "remote-1")
        self.assertIsNone(done.lease_sha256)

    def test_retryable_failure_uses_backoff_and_preserves_same_job_identity(self):
        self.service.enqueue(TENANT, body(scheduled=NOW), now=NOW)
        lease = self.service.claim_due(TENANT, "worker_0123456789abcdef", now=NOW, lease_seconds=60)[0]
        failed = self.service.mark_failed(
            TENANT, PUB, lease["lease_token"], "provider temporarily unavailable", retryable=True,
            now=NOW + timedelta(seconds=5),
        )
        self.assertEqual(failed.status, "PENDING")
        self.assertEqual(failed.attempts, 1)
        self.assertEqual(failed.available_at, (NOW + timedelta(seconds=35)).isoformat())
        self.assertEqual(self.service.claim_due(TENANT, "worker_0123456789abcdef", now=NOW + timedelta(seconds=34)), [])
        self.assertEqual(len(self.service.claim_due(TENANT, "worker_0123456789abcdef", now=NOW + timedelta(seconds=35))), 1)

    def test_retry_stops_after_max_attempts(self):
        self.service.enqueue(TENANT, body(scheduled=NOW), now=NOW)
        moment = NOW
        for attempt in range(1, MAX_ATTEMPTS + 1):
            lease = self.service.claim_due(TENANT, "worker_0123456789abcdef", now=moment, lease_seconds=60)[0]
            row = self.service.mark_failed(
                TENANT, PUB, lease["lease_token"], f"failure {attempt}", retryable=True,
                now=moment + timedelta(seconds=1),
            )
            if attempt < MAX_ATTEMPTS:
                self.assertEqual(row.status, "PENDING")
                moment = datetime.fromisoformat(row.available_at)
            else:
                self.assertEqual(row.status, "FAILED")
                self.assertEqual(row.attempts, MAX_ATTEMPTS)
        self.assertEqual(self.service.claim_due(TENANT, "worker_0123456789abcdef", now=moment + timedelta(days=1)), [])

    def test_expired_lease_is_requeued_without_provider_claim(self):
        self.service.enqueue(TENANT, body(scheduled=NOW), now=NOW)
        first = self.service.claim_due(TENANT, "worker_0123456789abcdef", now=NOW, lease_seconds=30)[0]
        self.assertTrue(first["lease_token"])
        second = self.service.claim_due(TENANT, "worker_fedcba9876543210", now=NOW + timedelta(seconds=31), lease_seconds=30)
        self.assertEqual(len(second), 1)
        row = self.storage.get(TENANT, PUB)
        self.assertEqual(row.attempts, 2)
        self.assertEqual(row.lease_worker_id, "worker_fedcba9876543210")

    def test_core_contains_no_meta_transport_or_credential_store(self):
        source = (ROOT / "gateway" / "social_queue.py").read_text(encoding="utf-8")
        self.assertNotIn("MetaGraphClient", source)
        self.assertNotIn("graph.facebook.com", source)
        self.assertNotIn("keychain", source.lower())
        self.assertNotIn("SUPABASE_SECRET_KEY", source)


class RemoteSocialQueueSqlContractTests(unittest.TestCase):
    def test_social_queue_is_separate_server_only_table(self):
        sql = (ROOT / "gateway" / "supabase" / "002_social_publish_queue.sql").read_text(encoding="utf-8")
        self.assertIn("binario_social_publish_queue", sql)
        self.assertNotIn("binario_public_intake_queue", sql)
        self.assertIn("enable row level security", sql.lower())
        self.assertIn("revoke all", sql.lower())
        self.assertIn("from anon, authenticated", sql.lower())
        self.assertIn("where status = 'PENDING'", sql)
        self.assertIn("where status = 'LEASED'", sql)
        self.assertNotIn("access_token", sql)

    def test_remote_queue_does_not_add_a_fourth_github_workflow(self):
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual({path.name for path in workflows}, {"ci.yml", "full-mac-app.yml", "persistent-release.yml"})
        self.assertEqual(len(workflows), 3)


if __name__ == "__main__":
    unittest.main()
