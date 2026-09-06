import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.cloud_social_bridge import CloudSocialBridge
from binario_marketing.service_post_w99_cloud_social_bridge_app import AppRuntime, create_server
from binario_marketing.social_process_lock import SocialProcessLock


ROOT = Path(__file__).resolve().parents[1]
TENANT = "tenant_" + "d" * 24
MASTER = "bridge-http-master-" + "x" * 40


class FakeCredentials:
    def read(self):
        return MASTER


class FakeClient:
    def __init__(self):
        self.enqueue_calls = 0
        self.remote_status = "PENDING"
        self.remote_id = None
        self.ambiguous = False

    def enqueue(self, payload):
        self.enqueue_calls += 1
        return {
            "schema": "binario.marketing.remote-social-receipt.v1",
            "publication_id": payload["publication"]["id"],
            "accepted": True,
            "idempotent_reuse": self.enqueue_calls > 1,
        }

    def status(self, publication_id):
        return 200, {
            "schema": "binario.marketing.remote-social-status.v1",
            "publication_id": publication_id,
            "found": True,
            "status": self.remote_status,
            "remote_id": self.remote_id,
            "provider_outcome_ambiguous": self.ambiguous,
        }


class CloudSocialBridgeHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.configure_public_gateway(self.company["id"], {
            "gateway_url": "https://gateway.example.com",
            "tenant_id": TENANT,
        })
        self.client = FakeClient()
        self.runtime.cloud_social_bridge = CloudSocialBridge(
            self.runtime.social,
            self.runtime.public_gateway_configs,
            FakeCredentials(),
            self.runtime.cloud_social_delegations,
            client_factory=lambda gateway, tenant, secret: self.client,
        )
        self.publication = self.runtime.create_company_publication(self.company["id"], {
            "channel": "facebook_page",
            "target_id": "page-1",
            "target_name": "Greenatics",
            "kind": "text",
            "message": "Contenido aprobado",
            "scheduled_for": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def request_json(self, path, *, method="GET"):
        request = Request(self.base + path, method=method)
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    @property
    def route(self):
        return f"/api/companies/{self.company['id']}/publications/{self.publication['id']}/cloud"

    def test_get_is_read_only_and_delegate_is_explicit_post(self):
        status, before = self.request_json(self.route + "/status")
        self.assertEqual(status, 200)
        self.assertEqual(before["local_status"], "QUEUED")
        self.assertFalse(before["delegated"])
        self.assertEqual(self.client.enqueue_calls, 0)

        status, delegated = self.request_json(self.route + "/delegate", method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(delegated["local_status"], "DELEGATED")
        self.assertEqual(delegated["delegation"]["status"], "CONFIRMED")
        self.assertEqual(self.client.enqueue_calls, 1)

    def test_delegated_publication_cannot_use_local_publish_now(self):
        self.request_json(self.route + "/delegate", method="POST")
        local_publish = (
            f"/api/companies/{self.company['id']}/publications/{self.publication['id']}/publish-now"
        )
        with self.assertRaises(HTTPError) as caught:
            self.request_json(local_publish, method="POST")
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.client.enqueue_calls, 1)

    def test_explicit_refresh_reconciles_remote_published(self):
        self.request_json(self.route + "/delegate", method="POST")
        self.client.remote_status = "PUBLISHED"
        self.client.remote_id = "fb_remote_1"
        _, result = self.request_json(self.route + "/refresh", method="POST")
        self.assertEqual(result["local_status"], "PUBLISHED")
        self.assertEqual(result["delegation"]["status"], "REMOTE_PUBLISHED")
        self.assertEqual(self.runtime.social.get(self.publication["id"]).remote_id, "fb_remote_1")

    def test_explicit_refresh_preserves_ambiguous_failure_as_delegated(self):
        self.request_json(self.route + "/delegate", method="POST")
        self.client.remote_status = "FAILED"
        self.client.ambiguous = True
        _, result = self.request_json(self.route + "/refresh", method="POST")
        self.assertEqual(result["local_status"], "DELEGATED")
        self.assertTrue(result["requires_manual_reconciliation"])
        self.assertEqual(self.runtime.social.get(self.publication["id"]).status, "DELEGATED")

    def test_process_contention_blocks_delegation_before_state_change(self):
        lock = SocialProcessLock(self.runtime.social.root)
        self.assertTrue(lock.acquire())
        try:
            with self.assertRaises(HTTPError) as caught:
                self.request_json(self.route + "/delegate", method="POST")
            self.assertEqual(caught.exception.code, 400)
            self.assertEqual(self.runtime.social.get(self.publication["id"]).status, "QUEUED")
            self.assertIsNone(self.runtime.cloud_social_delegations.get(self.publication["id"]))
            self.assertEqual(self.client.enqueue_calls, 0)
        finally:
            lock.release()

    def test_no_automatic_polling_or_cloud_delegation_exists_in_terminal(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_cloud_social_bridge_app.py").read_text(encoding="utf-8")
        bridge = (ROOT / "src" / "binario_marketing" / "cloud_social_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("setInterval", source + bridge)
        self.assertNotIn("threading.Thread", source + bridge)
        self.assertNotIn("/cloud/delegate'", source)
        self.assertIn('action == "delegate"', source)
        self.assertIn("SocialProcessLock", bridge)


if __name__ == "__main__":
    unittest.main()
