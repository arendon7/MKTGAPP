from __future__ import annotations

import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_post_w99_inbox_crm_identity_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class InboxCRMIdentityHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        company = self.runtime.companies.create("Empresa HTTP")
        self.company = self.runtime.companies.update(company.id, {"facebook_page_id": "page-http"})
        self.contact = self.runtime.crm.create_contact(self.company.id, {"name": "Contacto HTTP"})
        self.actor = "17890000111122223"
        self.interaction = "msg-http-1"
        payload = {
            "configured": True,
            "conversations": [{"messages": [{
                "id": self.interaction,
                "created_time": datetime.now(timezone.utc).isoformat(),
                "from": {"id": self.actor},
                "to": [{"id": "page-http"}],
                "message": "Hola",
                "reply_eligible": True,
                "crm_contact": None,
            }]}],
            "comments": [],
        }
        snapshot = self.runtime.inbox_attention_store.capture(
            self.company.id, page_id="page-http", instagram_id=None, payload=payload
        )
        self.observed = snapshot["captured_at"]
        self.token = self.runtime.inbox_crm_identities.intent_token(
            self.company.id, "facebook", self.interaction, self.actor, self.observed
        )
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

    def request(self, path: str, *, method: str = "GET", body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = Request(self.base + path, data=data, headers=headers, method=method)
        with urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, raw, json.loads(raw) if raw and "json" in response.headers.get_content_type() else None

    @property
    def route(self):
        return f"/api/companies/{self.company.id}/inbox/crm-identity-link"

    def body(self):
        return {
            "kind": "facebook_message",
            "interaction_id": self.interaction,
            "provider_person_id": self.actor,
            "intent_token": self.token,
            "observed_at": self.observed,
            "contact_id": self.contact.id,
            "expected_contact_id": None,
            "replace_confirmed": False,
        }

    def test_explicit_post_links_locally_and_response_is_identity_secret_free(self):
        status, raw, result = self.request(self.route, method="POST", body=self.body())
        self.assertEqual(status, 201)
        self.assertEqual(result["contact"]["id"], self.contact.id)
        self.assertFalse(result["provider_call_performed"])
        self.assertFalse(result["provider_person_id_exposed"])
        self.assertFalse(result["fingerprint_exposed"])
        self.assertFalse(result["intent_token_exposed"])
        self.assertNotIn(self.actor, raw)
        self.assertNotIn(self.token, raw)

    def test_stale_observation_and_wrong_intent_fail_with_conflict(self):
        body = self.body(); body["observed_at"] = "2026-09-05T00:00:00+00:00"
        with self.assertRaises(HTTPError) as caught:
            self.request(self.route, method="POST", body=body)
        self.assertEqual(caught.exception.code, 409)
        body = self.body(); body["intent_token"] = "0" * 64
        with self.assertRaises(HTTPError) as caught:
            self.request(self.route, method="POST", body=body)
        self.assertEqual(caught.exception.code, 409)

    def test_browser_asset_is_explicit_and_has_no_provider_or_polling_path(self):
        status, source, _ = self.request("/inbox-crm-identity.js")
        self.assertEqual(status, 200)
        self.assertIn("crm-identity-link", source)
        self.assertIn("window.confirm", source)
        self.assertIn("provider_person_id", source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("setTimeout", source)
        self.assertNotIn("MutationObserver", source)
        self.assertNotIn("graph.facebook", source)
        self.assertNotIn("https://", source)


if __name__ == "__main__":
    unittest.main()
