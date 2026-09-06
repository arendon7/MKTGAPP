import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gateway.social_api import SocialQueueGatewayService, derive_social_secret
from gateway.social_queue import MemorySocialQueueStorage, RemoteSocialQueueService
from binario_marketing.cloud_social_bridge import (
    CloudSocialBridge,
    CloudSocialBridgeError,
    CloudSocialDelegationStore,
    CloudSocialGatewayClient,
    CloudSocialTransportError,
)
from binario_marketing.public_gateway import PublicGatewayConfigStore
from binario_marketing.social_store import SocialStore


COMPANY = "company_" + "a" * 24
TENANT = "tenant_" + "b" * 24
MASTER = "gateway-master-" + "m" * 40
NOW = datetime.now(timezone.utc)


class FakeCredentials:
    def __init__(self, value=MASTER):
        self.value = value
        self.reads = 0

    def read(self):
        self.reads += 1
        return self.value


class FakeCloudClient:
    def __init__(self, gateway_url, tenant_id, secret, *, bridge_social=None, fail_enqueue=False, statuses=None):
        self.gateway_url = gateway_url
        self.tenant_id = tenant_id
        self.secret = secret
        self.bridge_social = bridge_social
        self.fail_enqueue = fail_enqueue
        self.statuses = list(statuses or [])
        self.enqueue_calls = 0
        self.seen_local_statuses = []

    def enqueue(self, payload):
        self.enqueue_calls += 1
        if self.bridge_social is not None:
            self.seen_local_statuses.append(self.bridge_social.get(payload["publication"]["id"]).status)
        if self.fail_enqueue:
            raise CloudSocialTransportError("network unavailable")
        return {
            "schema": "binario.marketing.remote-social-receipt.v1",
            "publication_id": payload["publication"]["id"],
            "accepted": True,
            "idempotent_reuse": self.enqueue_calls > 1,
        }

    def status(self, publication_id):
        if not self.statuses:
            return 200, {
                "schema": "binario.marketing.remote-social-status.v1",
                "publication_id": publication_id,
                "found": True,
                "status": "PENDING",
                "remote_id": None,
                "provider_outcome_ambiguous": False,
            }
        return self.statuses.pop(0)


class DesktopCloudSocialBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.social = SocialStore(root / "social")
        self.configs = PublicGatewayConfigStore(root / "gateway-config")
        self.delegations = CloudSocialDelegationStore(root / "delegations")
        self.configs.upsert(COMPANY, {"gateway_url": "https://gateway.example.com", "tenant_id": TENANT})

    def tearDown(self):
        self.tmp.cleanup()

    def publication(self, *, channel="facebook_page", kind="text", media_url=None):
        return self.social.create(COMPANY, {
            "channel": channel,
            "target_id": "page-1" if channel == "facebook_page" else "ig-1",
            "target_name": "Greenatics",
            "kind": kind,
            "message": "Contenido aprobado",
            "media_url": media_url,
            "scheduled_for": (NOW + timedelta(minutes=30)).isoformat(),
        })

    def bridge(self, client, credentials=None):
        return CloudSocialBridge(
            self.social,
            self.configs,
            credentials or FakeCredentials(),
            self.delegations,
            client_factory=lambda gateway, tenant, secret: client,
        )

    def test_success_withdraws_local_authority_before_remote_enqueue(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64, bridge_social=self.social)
        result = self.bridge(client).delegate(COMPANY, row.id)
        self.assertEqual(client.seen_local_statuses, ["DELEGATED"])
        self.assertEqual(self.social.get(row.id).status, "DELEGATED")
        self.assertEqual(self.social.due(NOW + timedelta(hours=1)), [])
        self.assertEqual(result["delegation"]["status"], "CONFIRMED")
        self.assertFalse(result["local_scheduler_authority"])
        self.assertFalse(result["secret_returned"])
        self.assertFalse(result["publication_body_returned"])

    def test_network_failure_after_authority_withdrawal_stays_delegated_and_retryable(self):
        row = self.publication()
        failed = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64, bridge_social=self.social, fail_enqueue=True)
        bridge = self.bridge(failed)
        result = bridge.delegate(COMPANY, row.id)
        self.assertEqual(self.social.get(row.id).status, "DELEGATED")
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])
        self.assertEqual(result["delegation"]["status"], "PREPARED")
        self.assertEqual(result["delegation"]["transport_error_type"], "CloudSocialTransportError")

        recovered = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64, bridge_social=self.social)
        bridge.client_factory = lambda gateway, tenant, secret: recovered
        retried = bridge.retry_enqueue(COMPANY, row.id)
        self.assertEqual(recovered.seen_local_statuses, ["DELEGATED"])
        self.assertEqual(retried["delegation"]["status"], "CONFIRMED")
        self.assertEqual(self.social.get(row.id).status, "DELEGATED")

    def test_missing_gateway_credential_consumes_no_local_scheduler_authority(self):
        row = self.publication()
        client = FakeCloudClient("https://gateway.example.com", TENANT, "0" * 64)
        result = self.bridge(client, FakeCredentials(None)).delegate(COMPANY, row.id)
        self.assertEqual(self.social.get(row.id).status, "DELEGATED")
        self.assertEqual(client.enqueue_calls, 0)
        self.assertEqual(result["delegation"]["status"], "PREPARED")
        self.assertEqual(result["delegation"]["transport_error_type"], "CloudSocialBridgeError")

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
            "remote_id": "fb_123",
            "provider_outcome_ambiguous": False,
        }))
        result = bridge.refresh_status(COMPANY, row.id)
        local = self.social.get(row.id)
        self.assertEqual(local.status, "PUBLISHED")
        self.assertEqual(local.remote_id, "fb_123")
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
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])
        self.assertEqual(result["delegation"]["status"], "AMBIGUOUS")
        self.assertTrue(result["requires_manual_reconciliation"])
        with self.assertRaises(CloudSocialBridgeError):
            bridge.retry_enqueue(COMPANY, row.id)

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
        # It remains absent from due() until a human explicitly queues it again.
        self.assertEqual(self.social.due(NOW + timedelta(days=1)), [])

    def test_delegated_state_is_not_a_local_publish_or_recovery_state(self):
        row = self.publication()
        self.social.delegate(row.id)
        with self.assertRaisesRegex(ValueError, "QUEUED"):
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
        for bad in ("https://user:pass@gateway.example.com", "https://gateway.example.com/evil"):
            with self.subTest(bad=bad):
                payload["gateway_url"] = bad
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.delegations.get(row.id)
                payload["gateway_url"] = "https://gateway.example.com"
                path.write_text(json.dumps(payload), encoding="utf-8")

    def test_social_secret_matches_server_derivation_without_being_persisted(self):
        row = self.publication()
        captured = {}
        def factory(gateway, tenant, secret):
            captured["secret"] = secret
            return FakeCloudClient(gateway, tenant, secret)
        bridge = CloudSocialBridge(self.social, self.configs, FakeCredentials(), self.delegations, client_factory=factory)
        bridge.delegate(COMPANY, row.id)
        self.assertEqual(captured["secret"], derive_social_secret(MASTER, TENANT))
        self.assertNotEqual(captured["secret"], MASTER)
        raw = (self.delegations.root / f"{row.id}.json").read_text(encoding="utf-8")
        self.assertNotIn(captured["secret"], raw)
        self.assertNotIn(MASTER, raw)


class RemoteStatusAmbiguityTests(unittest.TestCase):
    def test_signed_status_exposes_ambiguity_boolean_but_not_provider_error(self):
        class Storage(MemorySocialQueueStorage):
            def status_metadata(self, tenant_id, publication_id):
                return {"provider_outcome_ambiguous": True, "last_error": "must-not-leak"}

        tenant = TENANT
        storage = Storage()
        service = RemoteSocialQueueService(storage)
        body = json.dumps({
            "schema": "binario.marketing.remote-social-job.v1",
            "publication": {
                "id": "1" * 32,
                "project_id": COMPANY,
                "channel": "facebook_page",
                "target_id": "page-1",
                "target_name": "Greenatics",
                "kind": "text",
                "message": "Aprobado",
                "link_url": None,
                "media_url": None,
                "scheduled_for": (NOW + timedelta(minutes=10)).isoformat(),
            },
            "approval": {"source_status": "QUEUED", "operator_approved": True},
        }, separators=(",", ":")).encode("utf-8")
        service.enqueue(tenant, body, now=NOW)

        from gateway.social_api import SOCIAL_STATUS_PATH, social_request_headers
        social_secret = derive_social_secret(MASTER, tenant)
        query = json.dumps({"publication_id": "1" * 32}, separators=(",", ":")).encode("utf-8")
        stamp = int(NOW.timestamp())
        headers = social_request_headers(social_secret, tenant, method="POST", path=SOCIAL_STATUS_PATH, body=query, timestamp=stamp, nonce="c" * 32)
        status, result = SocialQueueGatewayService(storage, MASTER).status(headers, query, now=stamp)
        self.assertEqual(status, 200)
        self.assertTrue(result["provider_outcome_ambiguous"])
        self.assertFalse(result["provider_error_exposed"])
        self.assertNotIn("must-not-leak", json.dumps(result))


class CloudGatewayOriginTests(unittest.TestCase):
    def test_client_rejects_credentials_paths_queries_and_insecure_origins(self):
        secret = "a" * 64
        invalid = (
            "http://gateway.example.com",
            "https://user:pass@gateway.example.com",
            "https://gateway.example.com/api",
            "https://gateway.example.com?token=x",
        )
        for origin in invalid:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                CloudSocialGatewayClient(origin, TENANT, secret)


if __name__ == "__main__":
    unittest.main()
