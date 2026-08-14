import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.meta_credentials import CredentialStatus
from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.meta_inbox import InboxReadResult, MetaInboxReader
from binario_marketing.service_wave39_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class MetaInboxReaderTests(unittest.TestCase):
    def test_conversations_and_comments_use_get_only_with_page_credentials(self):
        calls = []

        def transport(method, url, params):
            calls.append((method, url, dict(params)))
            if url.endswith('/me/accounts'):
                return {"data": [{
                    "id": "page-1",
                    "name": "Greenatics",
                    "access_token": "PAGE_SECRET",
                    "instagram_business_account": {"id": "ig-1", "username": "greenatics"},
                }]}
            if url.endswith('/page-1/conversations'):
                return {"data": [{"id": "conv-1", "updated_time": "2026-08-14T15:00:00+0000"}]}
            if url.endswith('/conv-1'):
                return {"messages": {"data": [{"id": "msg-1", "created_time": "2026-08-14T14:59:00+0000"}]}}
            if url.endswith('/msg-1'):
                return {
                    "id": "msg-1",
                    "created_time": "2026-08-14T14:59:00+0000",
                    "from": {"id": "igsid-1", "username": "cliente"},
                    "to": {"data": [{"id": "ig-1", "username": "greenatics"}]},
                    "message": "Hola, quiero información",
                }
            if url.endswith('/media-1/comments'):
                return {"data": [{
                    "id": "comment-1",
                    "from": {"id": "igsid-1", "username": "cliente"},
                    "text": "¿Dónde compro?",
                    "timestamp": "2026-08-14T14:00:00+0000",
                }]}
            raise AssertionError(f"unexpected Meta request: {method} {url}")

        client = MetaGraphClient("USER_SECRET", transport=transport)
        reader = MetaInboxReader(client)
        result = reader.read_company(
            page_id="page-1",
            instagram_id="ig-1",
            instagram_media_ids=["media-1"],
            conversation_limit=10,
            messages_per_conversation=5,
            comments_per_media=20,
        )
        self.assertEqual(len(result.conversations), 1)
        self.assertEqual(result.conversations[0]["messages"][0]["message"], "Hola, quiero información")
        self.assertEqual(result.comments[0]["text"], "¿Dónde compro?")
        self.assertEqual(result.warnings, ())
        self.assertTrue(calls)
        self.assertTrue(all(method == "GET" for method, _, _ in calls))
        self.assertTrue(all("USER_SECRET" not in url and "PAGE_SECRET" not in url for _, url, _ in calls))

    def test_reader_bounds_remote_work(self):
        reader = MetaInboxReader(MetaGraphClient("token", transport=lambda *_: {"data": []}))
        with self.assertRaises(ValueError):
            reader.conversations("page", limit=21)
        with self.assertRaises(ValueError):
            reader.conversations("page", messages_per_conversation=11)
        with self.assertRaises(ValueError):
            reader.instagram_comments("ig", [], comments_per_media=51)


class Wave39RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_disconnected_inbox_is_network_free(self):
        with patch(
            "binario_marketing.service_wave39_app.MetaCredentialStore.status",
            return_value=CredentialStatus(False, "none", False),
        ), patch(
            "binario_marketing.service_wave39_app.MetaInboxReader.from_env",
            side_effect=AssertionError("inbox network client must not be created"),
        ):
            payload = self.runtime.social_inbox(self.company["id"])
        self.assertFalse(payload["configured"])
        self.assertEqual(payload["conversations"], [])
        self.assertEqual(payload["comments"], [])

    def test_inbox_matches_instagram_people_to_company_crm_without_mutation(self):
        company = self.runtime.update_company(self.company["id"], {
            "facebook_page_id": "page-1",
            "facebook_page_name": "Greenatics",
            "instagram_id": "ig-1",
            "instagram_username": "greenatics",
        })
        contact = self.runtime.create_contact(company["id"], {"name": "Cliente CRM", "instagram": "@cliente"})
        result = InboxReadResult(
            conversations=({
                "id": "conv-1",
                "updated_time": "2026-08-14T15:00:00+0000",
                "link": None,
                "messages": [{
                    "id": "msg-1",
                    "created_time": "2026-08-14T14:59:00+0000",
                    "from": {"id": "igsid-1", "username": "cliente"},
                    "to": [],
                    "message": "Hola",
                    "unavailable": False,
                    "error": None,
                }],
            },),
            comments=({
                "id": "comment-1",
                "media_id": "media-1",
                "from": {"id": "igsid-1", "username": "cliente"},
                "text": "Info",
                "timestamp": "2026-08-14T14:00:00+0000",
            },),
            warnings=(),
        )
        fake_reader = type("Reader", (), {"read_company": lambda self, **kwargs: result})()
        before_contacts = self.runtime.contacts_payload(company["id"])
        before_social = self.runtime.social.list(company["id"])
        with patch(
            "binario_marketing.service_wave39_app.MetaCredentialStore.status",
            return_value=CredentialStatus(True, "keychain", True),
        ), patch(
            "binario_marketing.service_wave39_app.MetaInboxReader.from_env",
            return_value=fake_reader,
        ):
            payload = self.runtime.social_inbox(company["id"])
        self.assertEqual(payload["summary"]["crm_matches"], 1)
        self.assertEqual(payload["conversations"][0]["messages"][0]["crm_contact"]["id"], contact["id"])
        self.assertEqual(payload["comments"][0]["crm_contact"]["id"], contact["id"])
        self.assertEqual(self.runtime.contacts_payload(company["id"]), before_contacts)
        self.assertEqual(self.runtime.social.list(company["id"]), before_social)


class Wave39HttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.credential = patch(
            "binario_marketing.service_wave39_app.MetaCredentialStore.status",
            return_value=CredentialStatus(False, "none", False),
        )
        self.credential.start()
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.credential.stop()
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_inbox_http_and_bundles_are_read_only(self):
        with urlopen(self.base + f"/api/inbox/meta?company_id={self.company['id']}&limit=10", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertFalse(payload["configured"])
        with urlopen(self.base + "/audiences.js", timeout=5) as response:
            loader = response.read().decode("utf-8")
        with urlopen(self.base + "/inbox.js", timeout=5) as response:
            inbox = response.read().decode("utf-8")
        self.assertIn("/audiences-wave38.js", loader)
        self.assertIn("/inbox.js", loader)
        self.assertIn("Actualizar desde Meta", inbox)
        self.assertIn("Wave 39 es sólo lectura", inbox)

    def test_ui_has_no_auto_refresh_or_meta_mutation(self):
        inbox = (ROOT / "web" / "inbox.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave39_app.py").read_text(encoding="utf-8")
        self.assertIn("inboxRefresh", inbox)
        self.assertNotIn("inboxRefresh();", inbox)
        self.assertNotIn("setInterval(", inbox)
        self.assertNotIn("MutationObserver", inbox)
        self.assertNotIn("method:'POST'", inbox)
        self.assertNotIn("method:'PATCH'", inbox)
        self.assertNotIn("method:'DELETE'", inbox)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertIn("service_wave38_app as ui_base", service)


if __name__ == "__main__":
    unittest.main()
