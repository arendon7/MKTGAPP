from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.cloud_social_bridge import (
    CloudSocialBridge,
    CloudSocialDelegationStore,
    CloudSocialGatewayClient,
)
from binario_marketing.public_gateway import GatewayCredentialStore, PublicGatewayConfigStore
from binario_marketing.social_store import SocialStore
from gateway.social_api import derive_social_secret


COMPANY = "company_" + "a" * 24
TENANT = "tenant_" + "b" * 24
MASTER = "m" * 48
NOW = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)


class MemoryCredentialStore(GatewayCredentialStore):
    def __init__(self, value: str | None = MASTER):
        self.value = value
        self.helper = None

    def read(self) -> str | None:
        return self.value


class FakeCloudClient:
    def __init__(self, gateway_url: str, tenant_id: str, social_secret: str):
        self.gateway_url = gateway_url
        self.tenant_id = tenant_id
        self.social_secret = social_secret
        self.enqueues: list[dict] = []
        self.statuses: list[tuple[int, dict]] = []
        self.enqueue_error: Exception | None = None

    def enqueue(self, payload: dict) -> dict:
        self.enqueues.append(payload)
        if self.enqueue_error:
            raise self.enqueue_error
        publication_id = payload["publication"]["id"]
        return {
            "schema": "binario.marketing.remote-social-receipt.v1",
            "publication_id": publication_id,
            "status": "PENDING",
            "idempotent": len(self.enqueues) > 1,
        }

    def status(self, publication_id: str) -> tuple[int, dict]:
        if not self.statuses:
            raise AssertionError("fake cloud status not configured")
        return self.statuses.pop(0)


class DesktopCloudSocialBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.social = SocialStore(root / "social")
        self.configs = PublicGatewayConfigStore(root / "public-gateway")
        self.configs.upsert(COMPANY, {
            "gateway_url": "https://gateway.example.com",
            "tenant_id": TENANT,
        })
        self.credentials = MemoryCredentialStore()
        self.delegations = CloudSocialDelegationStore(root / "cloud-social-delegations")

    def tearDown(self):
        self.temp.cleanup()

    def publication(self):
        return self.social.create(COMPANY, {
            "channel": "facebook_page",
            "target_id": "page_123",
            "target_name": "Page",
            "kind": "text",
            "message": "Contenido aprobado",
            "scheduled_for": (NOW + timedelta(minutes=5)).isoformat(),
        })

    def bridge(self, client: FakeCloudClient) -> CloudSocialBridge:
        def client_factory(gateway_url: str, tenant_id: str, secret: str) -> FakeCloudClient:
            client.gateway_url = gateway_url
            client.tenant_id = tenant_id
            client.social_secret = secret
            return client

        return CloudSocialBridge(
            self.social,
            self.configs,
            self.credentials,
            self.delegations,
            client_factory=client_factory,
        )

    def test_success_withdraws_local_authority_before_remote_enqueue(self):
        row = self.publication()
        observed_local_statuses: list[str] = []
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        original_enqueue = client.enqueue

        def enqueue(payload):
            observed_local_statuses.append(self.social.get(row.id).status)
            return original_enqueue(payload)

        client.enqueue = enqueue
        result = self.bridge(client).delegate(COMPANY, row.id)
        self.assertEqual(observed_local_statuses, ["DELEGATED"])
        self.assertEqual(self.social.get(row.id).status, "DELEGATED")
        self.assertFalse(result["local_scheduler_authority"])
        self.assertEqual(result["delegation"]["status"], "CONFIRMED")
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])

    def test_network_failure_after_authority_withdrawal_stays_delegated_and_retryable(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        client.enqueue_error = RuntimeError("network down")
        bridge = self.bridge(client)
        first = bridge.delegate(COMPANY, row.id)
        self.assertEqual(first["local_status"], "DELEGATED")
        self.assertEqual(first["delegation"]["status"], "PREPARED")
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])
        client.enqueue_error = None
        second = bridge.retry_enqueue(COMPANY, row.id)
        self.assertEqual(second["delegation"]["status"], "CONFIRMED")
        self.assertEqual(len(client.enqueues), 2)
        self.assertEqual(self.social.get(row.id).status, "DELEGATED")

    def test_missing_gateway_credential_consumes_no_local_scheduler_authority(self):
        row = self.publication()
        self.credentials.value = None
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        result = self.bridge(client).delegate(COMPANY, row.id)
        self.assertEqual(result["local_status"], "DELEGATED")
        self.assertEqual(result["delegation"]["status"], "PREPARED")
        self.assertEqual(client.enqueues, [])
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])

    def test_social_secret_matches_server_derivation_without_being_persisted(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        self.bridge(client).delegate(COMPANY, row.id)
        self.assertEqual(client.social_secret, derive_social_secret(MASTER, TENANT))
        raw = (self.delegations.root / f"{row.id}.json").read_text(encoding="utf-8")
        self.assertNotIn(client.social_secret, raw)
        self.assertNotIn(MASTER, raw)

    def test_remote_published_reconciles_exact_local_row(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        bridge = self.bridge(client)
        bridge.delegate(COMPANY, row.id)
        client.statuses.append((200, {
            "schema": "binario.marketing.remote-social-status.v1",
            "publication_id": row.id,
            "found": True,
            "status": "PUBLISHED",
            "remote_id": "remote_123",
            "provider_outcome_ambiguous": False,
        }))
        result = bridge.refresh_status(COMPANY, row.id)
        self.assertEqual(self.social.get(row.id).status, "PUBLISHED")
        self.assertEqual(self.social.get(row.id).remote_id, "remote_123")
        self.assertEqual(result["delegation"]["status"], "REMOTE_PUBLISHED")

    def test_remote_ambiguous_failure_never_returns_local_authority(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        bridge = self.bridge(client)
        bridge.delegate(COMPANY, row.id)
        client.statuses.append((200, {
            "schema": "binario.marketing.remote-social-status.v1",
            "publication_id": row.id,
            "found": True,
            "status": "FAILED",
            "remote_id": None,
            "provider_outcome_ambiguous": True,
        }))
        result = bridge.refresh_status(COMPANY, row.id)
        self.assertEqual(self.social.get(row.id).status, "DELEGATED")
        self.assertEqual(result["delegation"]["status"], "AMBIGUOUS")
        self.assertTrue(result["requires_manual_reconciliation"])
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])

    def test_remote_non_ambiguous_failure_can_only_return_through_explicit_review(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        bridge = self.bridge(client)
        bridge.delegate(COMPANY, row.id)
        client.statuses.append((200, {
            "schema": "binario.marketing.remote-social-status.v1",
            "publication_id": row.id,
            "found": True,
            "status": "FAILED",
            "remote_id": None,
            "provider_outcome_ambiguous": False,
        }))
        result = bridge.refresh_status(COMPANY, row.id)
        self.assertEqual(self.social.get(row.id).status, "FAILED")
        self.assertEqual(result["delegation"]["status"], "REMOTE_FAILED")
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])

    def test_delegated_state_is_not_a_local_publish_or_recovery_state(self):
        row = self.publication()
        self.social.delegate(row.id)
        with self.assertRaisesRegex(ValueError, "DELEGATED -> PUBLISHING"):
            self.social.transition(row.id, "PUBLISHING")
        self.assertEqual(self.social.recover_interrupted(), [])
        self.assertEqual(self.social.get(row.id).attempts, 0)

    def test_sidecar_contains_identity_evidence_not_content_or_secret(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        self.bridge(client).delegate(COMPANY, row.id)
        raw = (self.delegations.root / f"{row.id}.json").read_text(encoding="utf-8")
        lowered = raw.lower()
        self.assertNotIn("contenido aprobado", lowered)
        for forbidden in ("message", "media_url", "link_url", "access_token", MASTER.lower()):
            self.assertNotIn(forbidden, lowered)

    def test_tampered_sidecar_origin_with_credentials_or_path_is_rejected(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        self.bridge(client).delegate(COMPANY, row.id)
        path = self.delegations.root / f"{row.id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for bad in ("https://user:pass@gateway.example.com", "https://gateway.example.com/path"):
            payload["gateway_url"] = bad
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.delegations.get(row.id)
        payload["gateway_url"] = "https://gateway.example.com"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertIsNotNone(self.delegations.get(row.id))


class CloudGatewayOriginTests(unittest.TestCase):
    def test_client_rejects_credentials_paths_queries_and_insecure_origins(self):
        for bad in (
            "http://gateway.example.com",
            "https://user:pass@gateway.example.com",
            "https://gateway.example.com/path",
            "https://gateway.example.com/?x=1",
            "https://gateway.example.com/#frag",
        ):
            with self.assertRaises(ValueError, msg=bad):
                CloudSocialGatewayClient(bad, TENANT, "0" * 64)


class RemoteStatusAmbiguityTests(unittest.TestCase):
    def test_signed_status_exposes_ambiguity_boolean_but_not_provider_error(self):
        from gateway.social_api import SocialQueueGatewayService, social_request_headers
        from gateway.social_queue import MemorySocialQueueStorage, RemoteSocialJob

        storage = MemorySocialQueueStorage()
        publication = "c" * 32
        row = RemoteSocialJob(
            tenant_id=TENANT,
            publication_id=publication,
            payload={"schema": "binario.marketing.remote-social-job.v1"},
            payload_sha256=hashlib.sha256(b"x").hexdigest(),
            scheduled_for=NOW.isoformat(),
            available_at=NOW.isoformat(),
            status="FAILED",
            attempts=1,
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
            remote_id=None,
            last_error="provider secret diagnostic",
        )
        storage.insert(row)
        storage.status_metadata = lambda tenant_id, publication_id: {"provider_outcome_ambiguous": True}
        service = SocialQueueGatewayService(storage, MASTER)
        body = json.dumps({"publication_id": publication}, separators=(",", ":")).encode("utf-8")
        social_secret = derive_social_secret(MASTER, TENANT)
        headers = social_request_headers(
            social_secret,
            TENANT,
            method="POST",
            path="/api/social_status",
            body=body,
            timestamp=int(NOW.timestamp()),
            nonce="d" * 32,
        )
        status, result = service.status(headers, body, now=int(NOW.timestamp()))
        self.assertEqual(status, 200)
        self.assertTrue(result["provider_outcome_ambiguous"])
        self.assertNotIn("last_error", result)
        self.assertFalse(result["provider_error_exposed"])


if __name__ == "__main__":
    unittest.main()
