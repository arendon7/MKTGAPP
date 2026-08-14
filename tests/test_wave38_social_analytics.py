import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.meta_credentials import CredentialStatus
from binario_marketing.service_wave38_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave38AnalyticsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.credential = patch(
            "binario_marketing.service_wave38_app.MetaCredentialStore.status",
            return_value=CredentialStatus(False, "none", False),
        )
        self.credential.start()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")

    def tearDown(self):
        self.credential.stop()
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _company(self, name):
        return self.runtime.create_company({"name": name})

    def _published_instagram(self, company_id, target_id, message):
        row = self.runtime.social.create(company_id, {
            "channel": "instagram",
            "target_id": target_id,
            "target_name": "@analytics",
            "kind": "image",
            "message": message,
            "media_url": "https://example.com/image.jpg",
        })
        row = self.runtime.social.queue(row.id)
        row = self.runtime.social.transition(row.id, "PUBLISHING")
        return self.runtime.social.transition(row.id, "PUBLISHED", remote_id=f"remote_{row.id[:10]}")

    def test_local_summary_is_company_scoped_and_multi_company(self):
        greenatics = self._company("Greenatics")
        binario = self._company("Sistema Binario")
        self.runtime.update_company(greenatics["id"], {
            "facebook_page_id": "page-greenatics",
            "facebook_page_name": "Greenatics",
            "instagram_id": "ig-greenatics",
            "instagram_username": "greenatics",
        })
        facebook = self.runtime.social.create(greenatics["id"], {
            "channel": "facebook_page",
            "target_id": "page-greenatics",
            "target_name": "Greenatics",
            "kind": "text",
            "message": "Programada Greenatics",
            "scheduled_for": "2030-01-01T12:00:00+00:00",
        })
        instagram = self._published_instagram(greenatics["id"], "ig-greenatics", "Publicada Greenatics")
        self.runtime.social.create(binario["id"], {
            "channel": "facebook_page",
            "target_id": "page-binario",
            "target_name": "Sistema Binario",
            "kind": "text",
            "message": "Borrador Binario",
        })

        all_rows = self.runtime.social_analytics()
        self.assertEqual(all_rows["summary"]["total"], 3)
        self.assertEqual(all_rows["summary"]["queued"], 1)
        self.assertEqual(all_rows["summary"]["published"], 1)
        self.assertEqual(all_rows["summary"]["draft"], 1)
        self.assertEqual(len(all_rows["by_company"]), 2)

        selected = self.runtime.social_analytics(greenatics["id"])
        self.assertEqual(selected["summary"]["total"], 2)
        self.assertEqual(selected["summary"]["queued"], 1)
        self.assertEqual(selected["summary"]["published"], 1)
        self.assertEqual(selected["summary"]["published_with_remote_id"], 1)
        self.assertEqual(selected["channels"]["facebook_page"], 1)
        self.assertEqual(selected["channels"]["instagram"], 1)
        self.assertEqual({row["id"] for row in selected["recent"]}, {facebook.id, instagram.id})
        self.assertTrue(all(row["company_id"] == greenatics["id"] for row in selected["recent"]))

    def test_disconnected_meta_refresh_is_network_free_and_limit_is_bounded(self):
        company = self._company("Greenatics")
        with patch("binario_marketing.service_wave38_app.MetaObservability.from_env", side_effect=AssertionError("network client must not be created")):
            payload = self.runtime.social_analytics_meta(company["id"], limit=12)
        self.assertFalse(payload["configured"])
        self.assertEqual(payload["coverage"]["requested"], 0)
        self.assertEqual(payload["observations"], [])
        self.assertEqual(payload["totals"]["reach"], 0)
        with self.assertRaises(ValueError):
            self.runtime.social_analytics_meta(company["id"], limit=0)
        with self.assertRaises(ValueError):
            self.runtime.social_analytics_meta(company["id"], limit=21)


class Wave38AnalyticsHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.credential = patch(
            "binario_marketing.service_wave38_app.MetaCredentialStore.status",
            return_value=CredentialStatus(False, "none", False),
        )
        self.credential.start()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
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

    def _json(self, path):
        with urlopen(self.base + path, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_local_and_disconnected_meta_routes_are_get_only_readbacks(self):
        status, local = self._json(f"/api/analytics/social?company_id={self.company['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(local["company_id"], self.company["id"])
        self.assertEqual(local["summary"]["total"], 0)
        with patch("binario_marketing.service_wave38_app.MetaObservability.from_env", side_effect=AssertionError("network client must not be created")):
            status, remote = self._json(f"/api/analytics/social/meta?company_id={self.company['id']}&limit=12")
        self.assertEqual(status, 200)
        self.assertFalse(remote["configured"])
        self.assertEqual(remote["observations"], [])

    def test_wave38_loader_and_analytics_bundle_are_served(self):
        with urlopen(self.base + "/audiences.js", timeout=5) as response:
            loader = response.read().decode("utf-8")
        with urlopen(self.base + "/analytics.js", timeout=5) as response:
            analytics = response.read().decode("utf-8")
        self.assertIn("/audiences-wave37.js", loader)
        self.assertIn("/analytics.js", loader)
        self.assertIn("Actualizar desde Meta", analytics)
        self.assertIn("/api/analytics/social/meta", analytics)


class Wave38AnalyticsUiContractTests(unittest.TestCase):
    def test_ui_never_polls_or_mutates_meta_automatically(self):
        analytics = (ROOT / "web" / "analytics.js").read_text(encoding="utf-8")
        self.assertIn("Actualizar desde Meta", analytics)
        self.assertIn("analyticsRefreshMeta", analytics)
        self.assertIn("Todas las empresas", analytics)
        self.assertIn("permanece completamente local", analytics)
        self.assertNotIn("setInterval(", analytics)
        self.assertNotIn("MutationObserver", analytics)
        self.assertNotIn("method:'POST'", analytics)
        self.assertNotIn("method:'PATCH'", analytics)
        self.assertNotIn("method:'DELETE'", analytics)
        self.assertNotIn("analyticsRefreshMeta();", analytics)

    def test_runtime_routes_are_get_only_and_preserve_wave37_chain(self):
        service = (ROOT / "src" / "binario_marketing" / "service_wave38_app.py").read_text(encoding="utf-8")
        loader = (ROOT / "web" / "audiences-wave38-loader.js").read_text(encoding="utf-8")
        self.assertIn('parts == ["api", "analytics", "social"]', service)
        self.assertIn('parts == ["api", "analytics", "social", "meta"]', service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertIn("service_wave37_app as ui_base", service)
        self.assertIn("/audiences-wave37.js", loader)
        self.assertIn("/analytics.js", loader)


if __name__ == "__main__":
    unittest.main()
