import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave50_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave50CommandCenterRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_command_center_is_local_and_surfaces_flow_gaps(self):
        raw = b"\x89PNG\r\n\x1a\nwave50"
        media = self.runtime.upload_company_media(
            self.company["id"], "unprofiled.png", "image", io.BytesIO(raw), len(raw)
        )
        campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Campaña sin creativo",
            "objective": "LEADS",
            "status": "PLANNING",
            "channels": ["instagram"],
        })
        contact = self.runtime.create_contact(self.company["id"], {"name": "Cliente Uno"})
        self.runtime.create_activity(self.company["id"], {
            "contact_id": contact["id"],
            "kind": "CALL",
            "summary": "Llamar cliente",
            "due_at": "2026-01-01T10:00:00-05:00",
        })

        # A Command Center refresh must never use any provider-readback helper.
        self.runtime.social_analytics_meta = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("remote analytics called"))
        self.runtime.paid_media_observability = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("remote paid readback called"))

        payload = self.runtime.marketing_command_center(self.company["id"])
        self.assertEqual(payload["schema"], "binario.marketing.command-center.v1")
        self.assertEqual(payload["company"]["id"], self.company["id"])
        self.assertFalse(payload["safety"]["remote_refresh_performed"])
        self.assertFalse(payload["safety"]["provider_mutation_performed"])
        self.assertEqual(payload["creative"]["unprofiled"], 1)
        self.assertEqual(payload["flow"]["campaigns_active"], 1)
        self.assertEqual(payload["attention"]["crm_overdue"], 1)
        kinds = [row["kind"] for row in payload["priorities"]]
        self.assertIn("crm_overdue", kinds)
        self.assertIn("creative_unprofiled", kinds)
        self.assertIn("campaign_media", kinds)
        self.assertIn("setup_meta", kinds)
        self.assertEqual(payload["campaigns"][0]["id"], campaign["id"])
        self.assertEqual(payload["campaigns"][0]["media"], 0)
        self.assertEqual(payload["readiness"]["total"], 8)
        self.assertLess(payload["readiness"]["percent"], 100)
        self.assertEqual(payload["creative"]["total"], 1)
        self.assertEqual(payload["creative"]["counts"]["UNPROFILED"], 1)
        self.assertEqual(payload["legacy_dashboard"]["content"]["total"], 1)
        self.assertEqual(media["company_id"], self.company["id"])

    def test_ready_creative_and_company_meta_improve_readiness(self):
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "111111111111",
            "facebook_page_name": "Greenatics",
            "instagram_id": "222222222222",
            "instagram_username": "greenatics",
            "ad_account_id": "333333333333",
            "ad_account_name": "Greenatics Ads",
        })
        self.runtime.ensure_company_workspace(self.company["id"])
        raw = b"\x89PNG\r\n\x1a\nwave50-ready"
        media = self.runtime.upload_company_media(
            self.company["id"], "ready.png", "image", io.BytesIO(raw), len(raw)
        )
        campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Campaña A",
            "objective": "LEADS",
            "status": "READY",
            "channels": ["facebook_page", "instagram"],
            "media_ids": [media["id"]],
        })
        self.runtime.upsert_company_creative(self.company["id"], media["id"], {
            "title": "Creative A",
            "stage": "READY",
            "purpose": "LEADS",
            "campaign_id": campaign["id"],
            "channels": ["facebook_page", "paid_media"],
            "primary_copy": "Copy",
        })
        payload = self.runtime.marketing_command_center(self.company["id"])
        self.assertEqual(payload["flow"]["creatives_ready"], 1)
        self.assertEqual(payload["creative"]["unprofiled"], 0)
        self.assertNotIn("creative_campaign", [row["kind"] for row in payload["priorities"]])
        steps = {row["id"]: row["ready"] for row in payload["readiness"]["steps"]}
        self.assertTrue(steps["workspace"])
        self.assertTrue(steps["facebook"])
        self.assertTrue(steps["instagram"])
        self.assertTrue(steps["ads"])
        self.assertTrue(steps["campaign"])
        self.assertTrue(steps["creative"])


class Wave50CommandCenterHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
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

    def test_bundle_and_local_command_endpoint_are_served(self):
        with urlopen(self.base + "/command-center.js", timeout=5) as response:
            text = response.read().decode("utf-8")
        for marker in ("MARKETING COMMAND CENTER", "SIGUIENTE MEJOR ACCIÓN", "CAMPAIGN COCKPIT", "READINESS"):
            self.assertIn(marker, text)
        with urlopen(self.base + f"/api/companies/{self.company['id']}/command-center", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["company"]["id"], self.company["id"])
        self.assertFalse(payload["safety"]["remote_refresh_performed"])

    def test_loader_orders_command_center_after_creative_studio(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("creative.src='/creative-studio.js'", loader)
        self.assertIn("creative.addEventListener('load',loadCommandCenter", loader)
        self.assertIn("command.src='/command-center.js'", loader)

    def test_command_center_has_no_remote_refresh_or_direct_mutation_surface(self):
        ui = (ROOT / "web" / "command-center.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave50_app.py").read_text(encoding="utf-8")
        self.assertNotIn("/api/meta/", ui)
        self.assertNotIn("social_analytics_meta(", service)
        self.assertNotIn("paid_media_observability(", service)
        self.assertNotIn("setInterval(", ui)
        self.assertNotIn("publish-now", ui)
        self.assertNotIn("/activate", ui)
        self.assertIn('"remote_refresh_performed": False', service)
        self.assertIn('"provider_mutation_performed": False', service)

    def test_current_arm64_builder_launches_and_audits_wave50(self):
        build = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave50_app", build)
        self.assertIn("audit_wave50_command_center.sh", build)
        self.assertIn('[[ "$ARCH" == "arm64" ]]', build)


if __name__ == "__main__":
    unittest.main()
