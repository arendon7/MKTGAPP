import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave63_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave63CommercialPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _contact(self, name="Cliente pipeline"):
        return self.runtime.create_contact(self.company["id"], {"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com"})

    def test_pipeline_groups_stages_and_keeps_currency_buckets_separate(self):
        contact = self._contact()
        self.runtime.create_opportunity(self.company["id"], {
            "contact_id": contact["id"], "title": "Contrato Colombia", "stage": "PROPOSAL",
            "value": 3500000, "currency": "COP", "next_action": "Revisar propuesta",
            "next_action_at": "2030-01-01T12:00:00+00:00",
        })
        self.runtime.create_opportunity(self.company["id"], {
            "contact_id": contact["id"], "title": "Contrato exterior", "stage": "INTERESTED",
            "value": 1800, "currency": "USD", "next_action": "Enviar alcance",
            "next_action_at": "2030-01-02T12:00:00+00:00",
        })
        payload = self.runtime.commercial_pipeline(self.company["id"])
        self.assertEqual(payload["schema"], "binario.marketing.commercial-pipeline.v1")
        self.assertEqual([lane["stage"] for lane in payload["lanes"]], ["NEW", "CONTACTED", "INTERESTED", "PROPOSAL", "WON", "LOST"])
        amounts = payload["summary"]["amounts_by_currency"]
        self.assertEqual([(row["currency"], row["value"]) for row in amounts], [("COP", 3500000), ("USD", 1800)])
        self.assertFalse(payload["safety"]["mixed_currency_aggregation"])
        self.assertNotIn("total_value", payload["summary"])

    def test_pipeline_prioritizes_overdue_then_missing_followup(self):
        contact = self._contact("Prioridades")
        overdue = self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "A vencida", "stage": "NEW", "currency": "COP"})
        missing = self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "B sin acción", "stage": "NEW", "currency": "COP"})
        on_track = self.runtime.create_opportunity(self.company["id"], {
            "contact_id": contact["id"], "title": "C en curso", "stage": "NEW", "currency": "COP",
            "next_action": "Llamar", "next_action_at": "2030-01-01T12:00:00+00:00",
        })
        self.runtime.create_activity(self.company["id"], {
            "contact_id": contact["id"], "opportunity_id": overdue["id"], "kind": "TASK",
            "summary": "Seguimiento vencido", "due_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        })
        payload = self.runtime.commercial_pipeline(self.company["id"])
        lane = next(row for row in payload["lanes"] if row["stage"] == "NEW")
        self.assertEqual([row["id"] for row in lane["opportunities"]], [overdue["id"], missing["id"], on_track["id"]])
        self.assertEqual(lane["opportunities"][0]["attention"]["code"], "OVERDUE_FOLLOWUP")
        self.assertEqual(lane["opportunities"][1]["attention"]["code"], "NO_FOLLOWUP")
        self.assertEqual(lane["opportunities"][2]["attention"]["code"], "ON_TRACK")
        self.assertEqual(payload["summary"]["requires_attention"], 2)

    def test_closed_opportunities_do_not_require_attention(self):
        contact = self._contact("Cierres")
        won = self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "Ganada", "stage": "WON", "value": 900000, "currency": "COP"})
        lost = self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "Perdida", "stage": "LOST", "value": 500000, "currency": "COP"})
        payload = self.runtime.commercial_pipeline(self.company["id"])
        closed = [row for lane in payload["lanes"] if lane["stage"] in {"WON", "LOST"} for row in lane["opportunities"]]
        self.assertEqual({row["id"] for row in closed}, {won["id"], lost["id"]})
        self.assertTrue(all(row["attention"]["code"] == "CLOSED" for row in closed))
        self.assertTrue(all(row["attention"]["requires_attention"] is False for row in closed))
        self.assertEqual(payload["summary"]["open_opportunities"], 0)
        self.assertEqual(payload["summary"]["amounts_by_currency"], [])

    def test_pipeline_is_company_scoped(self):
        first_contact = self._contact("Empresa A")
        first = self.runtime.create_opportunity(self.company["id"], {"contact_id": first_contact["id"], "title": "Solo A", "currency": "COP"})
        other = self.runtime.create_company({"name": "Otra empresa"})
        second_contact = self.runtime.create_contact(other["id"], {"name": "Empresa B", "email": "b@example.com"})
        second = self.runtime.create_opportunity(other["id"], {"contact_id": second_contact["id"], "title": "Solo B", "currency": "USD"})
        first_payload = self.runtime.commercial_pipeline(self.company["id"])
        second_payload = self.runtime.commercial_pipeline(other["id"])
        first_ids = {row["id"] for lane in first_payload["lanes"] for row in lane["opportunities"]}
        second_ids = {row["id"] for lane in second_payload["lanes"] for row in lane["opportunities"]}
        self.assertEqual(first_ids, {first["id"]})
        self.assertEqual(second_ids, {second["id"]})

    def test_pipeline_get_never_reads_provider(self):
        contact = self._contact("Sin Meta")
        self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "Local", "currency": "COP"})
        with patch.object(self.runtime, "social_inbox", side_effect=AssertionError("pipeline must not read Meta")):
            payload = self.runtime.commercial_pipeline(self.company["id"])
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["provider_mutation_performed"])
        self.assertFalse(payload["safety"]["automatic_stage_change"])
        self.assertFalse(payload["safety"]["cloud_required"])

    def test_http_serves_pipeline_bootstrap_and_inherited_explicit_patch(self):
        contact = self._contact("HTTP pipeline")
        opportunity = self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "HTTP oportunidad", "stage": "NEW", "currency": "COP"})
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/contact-360.js", timeout=5) as response: contact_ui = response.read().decode("utf-8")
            self.assertIn("commercial-pipeline.js", contact_ui)
            self.assertIn("data-commercial-pipeline-wave63", contact_ui)
            with urlopen(base + "/commercial-pipeline.js", timeout=5) as response: pipeline_ui = response.read().decode("utf-8")
            self.assertIn("Pipeline comercial operativo", pipeline_ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/commercial-pipeline", timeout=5) as response: payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.commercial-pipeline.v1")
            request = Request(base + f"/api/companies/{self.company['id']}/opportunities/{opportunity['id']}", data=json.dumps({"stage": "CONTACTED"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="PATCH")
            with urlopen(request, timeout=5) as response: updated = json.loads(response.read().decode("utf-8"))
            self.assertEqual(updated["stage"], "CONTACTED")
            self.assertEqual(self.runtime.crm.get_opportunity(opportunity["id"]).stage, "CONTACTED")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_requires_explicit_stage_save_and_has_no_polling(self):
        ui = (ROOT / "web" / "commercial-pipeline.js").read_text(encoding="utf-8")
        for marker in ("Pipeline comercial operativo", "Valores separados por moneda", "Solo requieren atención", "Guardar etapa", "Contacto 360", "select.addEventListener('change',()=>{save.disabled=select.value===row.stage})", "save.addEventListener('click',()=>wave63SaveStage", "window.confirm", "method:'PATCH'"):
            self.assertIn(marker, ui)
        self.assertNotIn("addEventListener('change',async", ui)
        self.assertEqual(ui.count("method:'PATCH'"), 1)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertNotIn("sendBeacon", ui)

    def test_builder_service_workflows_and_release_boundary(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave63_app.py").read_text(encoding="utf-8")
        self.assertIn("service_wave60_app','service_wave61_app','service_wave62_app','service_wave63_app", builder)
        for audit in ("audit_wave55_lead_intake.sh", "audit_wave59_local_product_integration.sh", "audit_wave60_daily_workdesk.sh", "audit_wave61_commercial_desk.sh", "audit_wave62_contact_360.sh", "audit_wave63_commercial_pipeline.sh"):
            self.assertIn(audit, builder)
        for wave in (59, 60, 61, 62, 63): self.assertIn(f"CURRENT ARM64 ITERATION BUILD PASS: Wave {wave}", builder)
        self.assertIn("service_wave62_app as base", service)
        self.assertIn("pipeline.src='/commercial-pipeline.js'", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("social_inbox(", service)
        self.assertIn('host: str = "127.0.0.1"', service)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        self.assertEqual(source_release_state(), PREPARED_RELEASE)
        readiness = source_release_readiness(); self.assertTrue(readiness["source_ready"]); self.assertFalse(readiness["operational_inputs_complete"]); self.assertFalse(readiness["production_ready"])


if __name__ == "__main__":
    unittest.main()
