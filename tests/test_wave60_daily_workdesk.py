import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave60_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave60DailyWorkdeskTests(unittest.TestCase):
    def _runtime(self, root: Path):
        runtime = AppRuntime.create(ROOT, root / "data")
        company = runtime.create_company({"name": "Workdesk Local"})
        contact = runtime.crm.create_contact(company["id"], {"name": "Cliente Uno", "instagram": "@clienteuno"})
        return runtime, company, contact

    def test_workdesk_prioritizes_overdue_and_unscheduled_crm_without_remote_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, company, contact = self._runtime(Path(tmp))
            try:
                overdue = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
                runtime.crm.create_activity(company["id"], {
                    "contact_id": contact.id,
                    "opportunity_id": None,
                    "kind": "TASK",
                    "summary": "Seguimiento vencido de prueba",
                    "due_at": overdue,
                })
                runtime.crm.create_activity(company["id"], {
                    "contact_id": contact.id,
                    "opportunity_id": None,
                    "kind": "TASK",
                    "summary": "Seguimiento sin fecha",
                    "due_at": None,
                })
                data = runtime.daily_workdesk(company["id"])
                self.assertEqual(data["schema"], "binario.marketing.workdesk.v1")
                self.assertEqual(data["company"]["id"], company["id"])
                self.assertEqual(data["next_action"]["kind"], "crm_overdue")
                kinds = [row["kind"] for row in data["queue"]]
                self.assertIn("crm_overdue", kinds)
                self.assertIn("crm_unscheduled", kinds)
                self.assertEqual(data["crm"]["overdue"], 1)
                self.assertEqual(data["crm"]["unscheduled"], 1)
                self.assertFalse(data["safety"]["remote_refresh_performed"])
                self.assertFalse(data["safety"]["provider_mutation_performed"])
                self.assertFalse(data["safety"]["background_polling"])
                self.assertFalse(data["safety"]["cloud_required"])
                self.assertTrue(data["inbox"]["manual_refresh_required"])
                self.assertFalse(data["inbox"]["automatic_refresh"])
            finally:
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()

    def test_http_serves_workdesk_and_ui_from_loopback_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, company, _contact = self._runtime(Path(tmp))
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(base + "/workdesk.js", timeout=5) as response:
                    ui = response.read().decode("utf-8")
                self.assertIn("MESA DE TRABAJO · W60", ui)
                with urlopen(base + f"/api/companies/{company['id']}/workdesk", timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                self.assertEqual(data["schema"], "binario.marketing.workdesk.v1")
                self.assertFalse(data["safety"]["remote_refresh_performed"])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()

    def test_frontend_integrates_home_inbox_crm_without_automatic_meta_read(self):
        ui = (ROOT / "web" / "workdesk.js").read_text(encoding="utf-8")
        for marker in (
            "MESA DE TRABAJO · W60", "SIGUIENTE ACCIÓN", "COLA OPERATIVA", "Actualizar Inbox",
            "Seguimientos CRM", "Foco comercial", "crmState.tab='followups'", "crmState.tab='pipeline'",
            "/workdesk", "wave60InboxCache", "wave60ExplicitInboxRefresh",
        ):
            self.assertIn(marker, ui)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("/api/inbox/meta", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertNotIn("SUPABASE_", ui)
        self.assertNotIn("VERCEL_", ui)

    def test_service_is_get_only_local_composition(self):
        service = (ROOT / "src" / "binario_marketing" / "service_wave60_app.py").read_text(encoding="utf-8")
        self.assertIn("service_wave59_app as base", service)
        self.assertIn("def daily_workdesk", service)
        self.assertIn('path == "/workdesk.js"', service)
        self.assertIn('parts[3] == "workdesk"', service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertNotIn("meta_inbox", service)
        self.assertNotIn("/api/inbox/meta", service)
        self.assertIn('host: str = "127.0.0.1"', service)
        self.assertIn("refusing non-loopback bind without --allow-network", service)

    def test_loader_chains_wave60_after_wave59_and_preserves_wave56_order(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("gateway.addEventListener('load',loadLocalProduct", loader)
        self.assertIn("local.src='/local-product-integration.js'", loader)
        self.assertIn("local.addEventListener('load',loadWorkdesk", loader)
        self.assertIn("workdesk.src='/workdesk.js'", loader)
        self.assertIn("workdesk.dataset.workdeskWave60='1'", loader)

    def test_builder_retains_historical_audits_and_makes_wave60_current(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave56_app','service_wave59_app','service_wave60_app", builder)
        self.assertIn("audit_wave59_local_product_integration.sh", builder)
        self.assertIn("audit_wave60_daily_workdesk.sh", builder)
        self.assertIn("CURRENT ARM64 ITERATION BUILD PASS: Wave 60", builder)
        self.assertIn('[[ "$ARCH" == "arm64" ]]', builder)

    def test_workflow_and_release_boundaries_remain_unchanged(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)


if __name__ == "__main__":
    unittest.main()
