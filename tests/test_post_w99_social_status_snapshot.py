import json
import unittest
from datetime import datetime, timezone

from gateway.social_api import (
    SOCIAL_STATUS_PATH,
    SocialQueueGatewayService,
    derive_social_secret,
    social_request_headers,
)
from gateway.social_queue import RemoteSocialJob


TENANT = "tenant_" + "e" * 24
MASTER = "snapshot-master-" + "s" * 40
PUBLICATION = "9" * 32
NOW = datetime.now(timezone.utc)


class SnapshotOnlyStorage:
    def __init__(self):
        self.snapshot_calls = 0
        self.get_calls = 0
        now = NOW.isoformat()
        self.row = RemoteSocialJob(
            tenant_id=TENANT,
            publication_id=PUBLICATION,
            payload={"schema": "binario.marketing.remote-social-job.v1"},
            payload_sha256="a" * 64,
            scheduled_for=now,
            available_at=now,
            status="FAILED",
            attempts=2,
            created_at=now,
            updated_at=now,
            remote_id=None,
        )

    def status_snapshot(self, tenant_id, publication_id):
        self.snapshot_calls += 1
        self.assertions = (tenant_id, publication_id)
        return self.row, True

    def get(self, tenant_id, publication_id):
        self.get_calls += 1
        raise AssertionError("status() must not split production state across a second get")

    def insert(self, row):
        raise AssertionError("status() is read-only")


class RemoteSocialStatusSnapshotTests(unittest.TestCase):
    def test_gateway_prefers_single_atomic_status_snapshot(self):
        storage = SnapshotOnlyStorage()
        service = SocialQueueGatewayService(storage, MASTER)
        body = json.dumps({"publication_id": PUBLICATION}, separators=(",", ":")).encode("utf-8")
        stamp = int(NOW.timestamp())
        headers = social_request_headers(
            derive_social_secret(MASTER, TENANT),
            TENANT,
            method="POST",
            path=SOCIAL_STATUS_PATH,
            body=body,
            timestamp=stamp,
            nonce="f" * 32,
        )
        status, result = service.status(headers, body, now=stamp)
        self.assertEqual(status, 200)
        self.assertEqual(storage.snapshot_calls, 1)
        self.assertEqual(storage.get_calls, 0)
        self.assertEqual(storage.assertions, (TENANT, PUBLICATION))
        self.assertEqual(result["status"], "FAILED")
        self.assertTrue(result["provider_outcome_ambiguous"])
        self.assertFalse(result["provider_error_exposed"])
        self.assertFalse(result["lease_exposed"])


if __name__ == "__main__":
    unittest.main()
