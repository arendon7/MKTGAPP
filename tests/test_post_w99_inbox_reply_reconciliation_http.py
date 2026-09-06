from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_post_w99_inbox_reply_reconciliation_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class InboxReplyReconciliationHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.companies.create("Empresa prueba")
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

    def request_json(self, path: str, *, method: str = "GET", body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = Request(self.base + path, data=data, headers=headers, method=method)
        with urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None

    @property
    def route(self):
        return f"/api/companies/{self.company.id}/inbox/reply-reconcile"

    def ambiguous(self):
        row, _ = self.runtime.inbox_replies.begin(self.company.id, "facebook_message", "msg-1", "Privado")
        return self.runtime.inbox_replies.ambiguous(row.key)

    def test_post_sent_reconciliation_is_local_and_terminal(self):
        row = self.ambiguous()
        status, result = self.request_json(self.route, method="POST", body={
            "kind": "facebook_message",
            "interaction_id": "msg-1",
            "expected_stage": "AMBIGUOUS",
            "expected_updated_at": row.updated_at,
            "outcome": "SENT",
            "provider_checked": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["stage"], "RECONCILED_SENT")
        self.assertFalse(result["provider_call_performed"])
        self.assertFalse(result["retry_requires_new_explicit_send"])
        with self.assertRaises(Exception):
            self.runtime.inbox_replies.begin(self.company.id, "facebook_message", "msg-1", "Otro")

    def test_post_not_sent_restores_only_explicit_future_attempt(self):
        row = self.ambiguous()
        status, result = self.request_json(self.route, method="POST", body={
            "kind": "facebook_message",
            "interaction_id": "msg-1",
            "expected_stage": "AMBIGUOUS",
            "expected_updated_at": row.updated_at,
            "outcome": "NOT_SENT",
            "provider_checked": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["stage"], "RETRY_ALLOWED")
        self.assertTrue(result["retry_requires_new_explicit_send"])
        current = self.runtime.inbox_replies.for_interaction(self.company.id, "facebook_message", "msg-1")[0]
        self.assertEqual(current.stage, "RETRY_ALLOWED")

    def test_provider_checked_and_fresh_observation_are_mandatory(self):
        row = self.ambiguous()
        body = {
            "kind": "facebook_message",
            "interaction_id": "msg-1",
            "expected_stage": "AMBIGUOUS",
            "expected_updated_at": row.updated_at,
            "outcome": "SENT",
            "provider_checked": False,
        }
        with self.assertRaises(HTTPError) as caught:
            self.request_json(self.route, method="POST", body=body)
        self.assertEqual(caught.exception.code, 400)
        body["provider_checked"] = True
        body["expected_updated_at"] = "stale"
        with self.assertRaises(HTTPError) as caught:
            self.request_json(self.route, method="POST", body=body)
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.runtime.inbox_replies.for_interaction(self.company.id, "facebook_message", "msg-1")[0].stage, "AMBIGUOUS")

    def test_browser_asset_is_get_only_surface(self):
        request = Request(self.base + "/inbox-reply-reconciliation.js", method="GET")
        with urlopen(request, timeout=5) as response:
            source = response.read().decode("utf-8")
        self.assertIn("reply-reconcile", source)
        self.assertIn("window.confirm", source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("https://graph", source)


if __name__ == "__main__":
    unittest.main()
