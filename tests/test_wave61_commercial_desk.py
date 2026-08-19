import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service_wave61_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave61CommercialDeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_commercial_desk_prioritizes_exact_identity_resolution_without_meta_read(self):
        company_id = self.company["id"]
        matched_contact = self.runtime.create_contact(company_id, {"name": "Exacto", "email": "exact@example.com"})
        self.runtime.intake_lead(company_id, {"connector": "MANUAL", "name": "Nuevo", "email": "new@example.com"})
        matched = self.runtime.intake_lead(company_id, {"connector": "MANUAL", "name": "Coincide", "email": "EXACT@example.com"})
        self.runtime.create_contact(company_id, {"name": "Conflicto A", "email": "conflict@example.com"})
        self.runtime.create_contact(company_id, {"name": "Conflicto B", "email": "conflict@example.com"})
        conflict = self.runtime.intake_lead(company_id, {"connector": "MANUAL", "name": "Conflicto", "email": "conflict@example.com"})
        with patch.object(self.runtime, "social_inbox", side_effect=AssertionError("commercial desk must not read Meta")):
            desk = self.runtime.commercial_desk(company_id)
        self.assertEqual(desk["schema"], "binario.marketing.commercial-desk.v1")
        self.assertEqual(desk["lead_queue"][0]["lead_id"], conflict["id"])
        self.assertEqual(desk["lead_queue"][0]["status"], "CONFLICT")
        matched_row = next(row for row in desk["lead_queue"] if row["lead_id"] == matched["id"])
        self.assertEqual(matched_row["candidate_contacts"][0]["id"], matched_contact["id"])
        self.assertFalse(desk["safety"]["provider_read_performed"])
        self.assertFalse(desk["safety"]["automatic_crm_conversion"])
        self.assertTrue(desk["inbox"]["manual_refresh_required"])

    def test_converted_lead_handoff_moves_from_opportunity_to_followup(self):
        company_id = self.company["id"]
        lead = self.runtime.intake_lead(company_id, {"connector": "MANUAL", "name": "Venta", "email": "venta@example.com"})
        converted = self.runtime.convert_lead(company_id, lead["id"], {"action": "CREATE_CONTACT"})
        desk = self.runtime.commercial_desk(company_id)
        handoff = next(row for row in desk["handoffs"] if row["lead_id"] == lead["id"])
        self.assertEqual(handoff["handoff_state"], "NEEDS_OPPORTUNITY")

        opportunity = self.runtime.create_opportunity(company_id, {
            "contact_id": converted["converted_contact_id"],
            "title": "Venta nueva",
            "stage": "NEW",
            "currency": "COP",
        })
        # W55 conversion is idempotent and can attach an explicitly requested opportunity.
        linked = self.runtime.convert_lead(company_id, lead["id"], {
            "action": "LINK_CONTACT",
            "contact_id": converted["converted_contact_id"],
            "opportunity": {"title": "Venta intake", "stage": "NEW", "currency": "COP"},
        })
        self.assertNotEqual(linked["converted_opportunity_id"], opportunity["id"])
        desk = self.runtime.commercial_desk(company_id)
        handoff = next(row for row in desk["handoffs"] if row["lead_id"] == lead["id"])
        self.assertEqual(handoff["handoff_state"], "NEEDS_FOLLOWUP")
        self.runtime.create_activity(company_id, {
            "contact_id": converted["converted_contact_id"],
            "opportunity_id": linked["converted_opportunity_id"],
            "kind": "TASK",
            "summary": "Confirmar siguiente paso",
        })
        desk = self.runtime.commercial_desk(company_id)
        handoff = next(row for row in desk["handoffs"] if row["lead_id"] == lead["id"])
        self.assertEqual(handoff["handoff_state"], "FOLLOWUP_PLANNED")
        self.assertEqual(handoff["pending_activity_count"], 1)

    def test_http_serves_get_only_commercial_desk_and_browser_layer(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/commercial-desk.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Mesa comercial", ui)
            self.assertIn("Pasar a Lead Intake", ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/commercial-desk", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.commercial-desk.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_stages_cached_inbox_before_crm_and_keeps_every_side_effect_explicit(self):
        ui = (ROOT / "web" / "commercial-desk.js").read_text(encoding="utf-8")
        for marker in (
            "INBOX → LEAD → CRM",
            "Pasar a Lead Intake",
            "Interacción enviada a Lead Intake; CRM sigue sin cambios",
            "Resolver conflicto exacto",
            "Crear oportunidad",
            "Programar seguimiento",
            "Actualizar Inbox",
        ):
            self.assertIn(marker, ui)
        self.assertIn("meta_inbox:", ui)
        self.assertIn("/lead-intake", ui)
        self.assertIn("/opportunities", ui)
        self.assertIn("/activities", ui)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertNotIn("sendBeacon", ui)
        self.assertNotIn("automatic", ui.lower().replace("automáticamente", ""))

    def test_service_is_local_get_composition_and_preserves_loopback_boundary(self):
        service = (ROOT / "src" / "binario_marketing" / "service_wave61_app.py").read_text(encoding="utf-8")
        self.assertIn("service_wave60_app as base", service)
        self.assertIn('path == "/commercial-desk.js"', service)
        self.assertIn('parts[3] == "commercial-desk"', service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("social_inbox(", service)
        self.assertIn('host: str = "127.0.0.1"', service)
        self.assertIn("refusing non-loopback bind without --allow-network", service)

    def test_loader_builder_workflows_and_release_boundary(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("workdesk.addEventListener('load',loadCommercialDesk", loader)
        self.assertIn("commercial.src='/commercial-desk.js'", loader)
        self.assertIn("service_wave60_app','service_wave61_app", builder)
        for audit in (
            "audit_wave55_lead_intake.sh",
            "audit_wave59_local_product_integration.sh",
            "audit_wave60_daily_workdesk.sh",
            "audit_wave61_commercial_desk.sh",
        ):
            self.assertIn(audit, builder)
        self.assertIn("CURRENT ARM64 ITERATION BUILD PASS: Wave 61", builder)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)


if __name__ == "__main__":
    unittest.main()
