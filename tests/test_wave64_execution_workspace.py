import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave64_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave64ExecutionWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "111111111111", "facebook_page_name": "Greenatics",
            "instagram_id": "222222222222", "instagram_username": "greenatics",
            "ad_account_id": "333333333333", "ad_account_name": "Greenatics Ads",
        })

    def tearDown(self):
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def _campaign(self, name="Campaña W64", channels=None, status="PLANNING"):
        return self.runtime.create_campaign(self.company["id"], {"name": name, "objective": "LEADS", "status": status, "channels": channels if channels is not None else ["facebook_page", "instagram"]})

    def _image(self, name="creative.png"):
        payload = b"\x89PNG\r\n\x1a\nwave64"
        return self.runtime.upload_company_media(self.company["id"], name, "image", io.BytesIO(payload), len(payload))

    def _ready_creative(self, campaign, name="Creative W64"):
        media = self._image()
        self.runtime.upsert_company_creative(self.company["id"], media["id"], {
            "title": name, "stage": "READY", "purpose": "LEADS", "campaign_id": campaign["id"],
            "channels": ["facebook_page", "paid_media"], "primary_copy": "Mensaje de campaña",
            "public_media_url": "https://cdn.example.com/w64.png", "destination_url": "https://example.com/landing",
        })
        return media

    def test_workspace_prioritizes_missing_channels_then_missing_creative(self):
        missing_channels = self._campaign("A sin canales", channels=[]); missing_creative = self._campaign("B sin creativo")
        payload = self.runtime.campaign_execution_workspace(self.company["id"])
        self.assertEqual(payload["schema"], "binario.marketing.execution-workspace.v1")
        self.assertEqual([row["campaign"]["id"] for row in payload["campaigns"][:2]], [missing_channels["id"], missing_creative["id"]])
        self.assertEqual(payload["campaigns"][0]["next_action"]["code"], "DEFINE_CHANNELS")
        self.assertEqual(payload["campaigns"][1]["next_action"]["code"], "CREATE_CREATIVE")
        self.assertEqual(payload["summary"]["requires_action"], 2)

    def test_ready_creative_flows_to_distribution_without_mutation(self):
        campaign = self._campaign(); media = self._ready_creative(campaign); before = self.runtime.creatives.get(self.company["id"], media["id"])
        payload = self.runtime.campaign_execution_workspace(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["creative"]["ready"], 1); self.assertEqual(row["next_action"]["code"], "PREPARE_DISTRIBUTION"); self.assertEqual(row["next_action"]["view"], "content")
        self.assertEqual(before, self.runtime.creatives.get(self.company["id"], media["id"])); self.assertEqual(row["organic"]["publications"], 0)

    def test_prepared_publication_is_reflected_from_canonical_social_store(self):
        campaign = self._campaign(); media = self._ready_creative(campaign)
        prepared = self.runtime.prepare_creative_publication(self.company["id"], media["id"], {"channel": "facebook_page", "scheduled_for": "2026-08-25T15:00:00-05:00"})
        self.assertEqual(prepared["publication"]["status"], "QUEUED")
        payload = self.runtime.campaign_execution_workspace(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["organic"]["counts"].get("QUEUED"), 1); self.assertEqual(row["next_action"]["code"], "CALENDAR")
        self.assertEqual(next(step for step in row["steps"] if step["code"] == "ORGANIC")["state"], "ACTIVE")

    def test_paid_draft_is_linked_without_remote_creation(self):
        campaign = self._campaign(); media = self._ready_creative(campaign)
        paid = self.runtime.create_company_paid_media(self.company["id"], {
            "campaign_id": campaign["id"], "source_kind": "company_media", "company_media_id": media["id"], "campaign_name": "Meta Leads",
            "campaign_objective": "OUTCOME_LEADS", "special_ad_categories": [], "adset_name": "CO Leads", "daily_budget": 10000,
            "optimization_goal": "LINK_CLICKS", "targeting": {"geo_locations": {"countries": ["CO"]}, "age_min": 25, "age_max": 55},
            "creative_name": "Creative W64", "message": "Mensaje de campaña", "link_url": "https://example.com/landing", "call_to_action": "LEARN_MORE", "ad_name": "Ad W64",
        })
        self.assertEqual(paid["status"], "DRAFT")
        payload = self.runtime.campaign_execution_workspace(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["paid"]["plans"], 1); self.assertEqual(row["paid"]["counts"].get("DRAFT"), 1); self.assertEqual(row["next_action"]["code"], "REVIEW_PAID")
        self.assertFalse(payload["safety"]["automatic_paid_activation"]); self.assertFalse(payload["safety"]["provider_mutation_performed"])

    def test_workspace_is_company_scoped_and_provider_read_free(self):
        first = self._campaign("Solo Greenatics"); other = self.runtime.create_company({"name": "Otra empresa"}); second = self.runtime.create_campaign(other["id"], {"name": "Solo otra", "objective": "LEADS", "channels": ["facebook_page"]})
        with patch("binario_marketing.service_wave48_app.MetaGraphClient.from_env", side_effect=AssertionError("provider read forbidden")):
            first_payload = self.runtime.campaign_execution_workspace(self.company["id"]); second_payload = self.runtime.campaign_execution_workspace(other["id"])
        self.assertEqual({row["campaign"]["id"] for row in first_payload["campaigns"]}, {first["id"]}); self.assertEqual({row["campaign"]["id"] for row in second_payload["campaigns"]}, {second["id"]})
        self.assertFalse(first_payload["safety"]["provider_read_performed"]); self.assertFalse(first_payload["safety"]["background_polling"]); self.assertFalse(first_payload["safety"]["cloud_required"])

    def test_http_serves_execution_workspace_and_wave64_bootstrap(self):
        self._campaign(); server = create_server(self.runtime, "127.0.0.1", 0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/commercial-pipeline.js", timeout=5) as response: pipeline_ui = response.read().decode("utf-8")
            self.assertIn("execution-workspace.js", pipeline_ui); self.assertIn("data-execution-workspace-wave64", pipeline_ui)
            with urlopen(base + "/execution-workspace.js", timeout=5) as response: execution_ui = response.read().decode("utf-8")
            self.assertIn("Centro de ejecución de campañas", execution_ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/execution-workspace", timeout=5) as response: payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.execution-workspace.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_is_navigation_only_without_direct_mutations_or_polling(self):
        ui = (ROOT / "web" / "execution-workspace.js").read_text(encoding="utf-8")
        for marker in ("Centro de ejecución de campañas", "De plan a distribución", "Solo requieren acción", "Creative Studio", "Calendario", "Pauta", "Resultados", "execution-workspace"): self.assertIn(marker, ui)
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", "setInterval", "sendBeacon", "fetch('https://"): self.assertNotIn(forbidden, ui)
        self.assertIn("opsShowView(view)", ui); self.assertIn("opsShowLegacy()", ui)

    def test_builder_service_workflows_and_release_boundary(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8"); service = (ROOT / "src" / "binario_marketing" / "service_wave64_app.py").read_text(encoding="utf-8")
        self.assertIn("service_wave63_app','service_wave64_app", builder)
        for audit in ("audit_wave59_local_product_integration.sh", "audit_wave60_daily_workdesk.sh", "audit_wave61_commercial_desk.sh", "audit_wave62_contact_360.sh", "audit_wave63_commercial_pipeline.sh", "audit_wave64_execution_workspace.sh"): self.assertIn(audit, builder)
        for wave in (59, 60, 61, 62, 63, 64): self.assertIn(f"CURRENT ARM64 ITERATION BUILD PASS: Wave {wave}", builder)
        self.assertIn("service_wave63_app as base", service); self.assertIn("execution.src='/execution-workspace.js'", service); self.assertNotIn("def do_POST", service); self.assertNotIn("def do_PATCH", service); self.assertNotIn("def do_DELETE", service); self.assertIn('host: str = "127.0.0.1"', service)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml")); self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8"); self.assertIn('__version__ = "0.9.0"', version); self.assertIn("RELEASE_READY = True", version); self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        self.assertEqual(source_release_state(), PREPARED_RELEASE); readiness = source_release_readiness(); self.assertTrue(readiness["source_ready"]); self.assertFalse(readiness["operational_inputs_complete"]); self.assertFalse(readiness["production_ready"])


if __name__ == "__main__":
    unittest.main()
