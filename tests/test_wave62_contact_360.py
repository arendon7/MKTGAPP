import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave62_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave62Contact360Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _build_evidence_contact(self):
        company_id = self.company["id"]
        contact = self.runtime.create_contact(company_id, {
            "name": "Cliente 360",
            "organization": "Finca Norte",
            "email": "cliente@example.com",
            "whatsapp": "+57 300 111 2233",
            "source": "Lead Intake",
        })
        campaign = self.runtime.create_campaign(company_id, {
            "name": "Campaña comercial",
            "objective": "LEADS",
            "status": "IN_PROGRESS",
            "channels": ["email", "whatsapp"],
            "audience_contact_ids": [contact["id"]],
        })
        link = self.runtime.attribution.create_link(company_id, {
            "campaign_id": campaign["id"],
            "destination_url": "https://example.com/landing",
            "utm_source": "instagram",
            "utm_medium": "social",
            "utm_campaign": "campana-comercial",
            "utm_id": "cmp-360",
            "utm_content": "reel-a",
            "utm_source_platform": "meta",
        })
        lead = self.runtime.lead_intake.create(company_id, {
            "connector": "FIRST_PARTY_FORM",
            "source_ref": "form:contact-360:001",
            "name": "Cliente 360",
            "email": "cliente@example.com",
            "source": "Landing comercial",
            "tracking_link_id": link.id,
            "tracking_code": link.tracking_code,
            "utm_source": link.utm_source,
            "utm_medium": link.utm_medium,
            "utm_campaign": link.utm_campaign,
            "utm_id": link.utm_id,
            "utm_content": link.utm_content,
            "utm_source_platform": link.utm_source_platform,
        })
        self.runtime.lead_intake.mark_contact_conversion(
            company_id, lead.id, contact["id"], basis="CREATED_NEW_CONTACT"
        )
        opportunity = self.runtime.create_opportunity(company_id, {
            "contact_id": contact["id"],
            "title": "Implementación 360",
            "stage": "INTERESTED",
            "value": 3500000,
            "currency": "COP",
        })
        self.runtime.attribution.create_claim(company_id, {
            "tracking_code": link.tracking_code,
            "contact_id": contact["id"],
            "opportunity_id": opportunity["id"],
            "evidence": "CAPTURED_TRACKING_CODE",
        })
        return contact, campaign, link, lead, opportunity

    def test_contact_360_composes_crm_lead_attribution_and_campaign_without_provider_read(self):
        contact, campaign, _link, lead, opportunity = self._build_evidence_contact()
        self.runtime.create_activity(self.company["id"], {
            "contact_id": contact["id"],
            "opportunity_id": opportunity["id"],
            "kind": "TASK",
            "summary": "Enviar alcance",
            "due_at": "2030-01-01T12:00:00+00:00",
        })
        with patch.object(self.runtime, "social_inbox", side_effect=AssertionError("Contact 360 must not read Meta")):
            payload = self.runtime.contact_360(self.company["id"], contact["id"])
        self.assertEqual(payload["schema"], "binario.marketing.contact-360.v1")
        self.assertEqual(payload["contact"]["id"], contact["id"])
        self.assertEqual(payload["summary"]["lead_origins"], 1)
        self.assertEqual(payload["summary"]["attribution_claims"], 1)
        self.assertEqual(payload["summary"]["campaigns"], 1)
        self.assertEqual(payload["lead_origins"][0]["lead_id"], lead.id)
        self.assertEqual(payload["attribution"][0]["campaign_id"], campaign["id"])
        self.assertTrue(payload["campaigns"][0]["audience_membership"])
        self.assertTrue(payload["campaigns"][0]["attribution_evidence"])
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["automatic_action_execution"])

    def test_contact_360_next_action_prioritizes_overdue_followup(self):
        contact, _campaign, _link, _lead, opportunity = self._build_evidence_contact()
        activity = self.runtime.create_activity(self.company["id"], {
            "contact_id": contact["id"],
            "opportunity_id": opportunity["id"],
            "kind": "TASK",
            "summary": "Seguimiento vencido",
            "due_at": "2020-01-01T12:00:00+00:00",
        })
        payload = self.runtime.contact_360(self.company["id"], contact["id"])
        self.assertEqual(payload["summary"]["overdue_activities"], 1)
        self.assertEqual(payload["next_action"]["code"], "RESOLVE_OVERDUE_FOLLOWUP")
        self.assertEqual(payload["next_action"]["activity_id"], activity["id"])

    def test_contact_360_without_pending_activity_recommends_followup_then_opportunity(self):
        company_id = self.company["id"]
        contact = self.runtime.create_contact(company_id, {"name": "Pipeline", "email": "pipe@example.com"})
        opportunity = self.runtime.create_opportunity(company_id, {
            "contact_id": contact["id"], "title": "Venta", "stage": "NEW", "currency": "COP"
        })
        payload = self.runtime.contact_360(company_id, contact["id"])
        self.assertEqual(payload["next_action"]["code"], "PLAN_FOLLOWUP")
        self.runtime.update_opportunity(company_id, opportunity["id"], {"stage": "LOST"})
        lead = self.runtime.lead_intake.create(company_id, {
            "connector": "MANUAL", "name": "Pipeline", "email": "pipe@example.com", "source": "Feria"
        })
        self.runtime.lead_intake.mark_contact_conversion(company_id, lead.id, contact["id"], basis="USER_SELECTED_CONTACT")
        payload = self.runtime.contact_360(company_id, contact["id"])
        self.assertEqual(payload["next_action"]["code"], "CREATE_OPPORTUNITY")

    def test_contact_360_never_exposes_tracking_code_or_tracked_url(self):
        contact, _campaign, link, _lead, _opportunity = self._build_evidence_contact()
        payload = self.runtime.contact_360(self.company["id"], contact["id"])
        encoded = json.dumps(payload, sort_keys=True)
        self.assertNotIn(link.tracking_code, encoded)
        self.assertNotIn(link.tracked_url, encoded)
        self.assertTrue(payload["safety"]["tracking_code_exposed"] is False)
        self.assertTrue(payload["safety"]["tracked_url_exposed"] is False)
        self.assertEqual(payload["evidence_contract"]["attribution"], "CAPTURED_TRACKING_CODE_ONLY")

    def test_cross_company_contact_fails_closed(self):
        contact = self.runtime.create_contact(self.company["id"], {"name": "Privado", "email": "private@example.com"})
        other = self.runtime.create_company({"name": "Otra empresa"})
        with self.assertRaises(KeyError):
            self.runtime.contact_360(other["id"], contact["id"])

    def test_http_serves_contact_360_and_browser_layer(self):
        contact = self.runtime.create_contact(self.company["id"], {"name": "HTTP 360", "email": "http360@example.com"})
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/contact-360.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Contacto 360", ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/contacts/{contact['id']}/360", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.contact-360.v1")
            other = self.runtime.create_company({"name": "Otra"})
            with self.assertRaises(HTTPError) as error:
                urlopen(base + f"/api/companies/{other['id']}/contacts/{contact['id']}/360", timeout=5)
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_is_local_read_only_composition_without_polling(self):
        ui = (ROOT / "web" / "contact-360.js").read_text(encoding="utf-8")
        for marker in (
            "CRM → EVIDENCIA → SIGUIENTE ACCIÓN",
            "Origen & atribución",
            "Atribución verificada",
            "Campañas relacionadas",
            "Línea de tiempo",
            "Abrir Mesa comercial",
            "/contacts/${encodeURIComponent(id)}/360",
        ):
            self.assertIn(marker, ui)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertNotIn("sendBeacon", ui)
        self.assertNotIn("method:'POST'", ui)
        self.assertNotIn("method:'PATCH'", ui)

    def test_loader_builder_service_workflows_and_release_boundary(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave62_app.py").read_text(encoding="utf-8")
        self.assertIn("workdesk.addEventListener('load',loadCommercialDesk", loader)
        self.assertIn("commercial.addEventListener('load',loadContact360", loader)
        self.assertIn("contact360.src='/contact-360.js'", loader)
        self.assertIn("service_wave60_app','service_wave61_app','service_wave62_app", builder)
        for audit in (
            "audit_wave55_lead_intake.sh",
            "audit_wave59_local_product_integration.sh",
            "audit_wave60_daily_workdesk.sh",
            "audit_wave61_commercial_desk.sh",
            "audit_wave62_contact_360.sh",
        ):
            self.assertIn(audit, builder)
        self.assertIn("CURRENT ARM64 ITERATION BUILD PASS: Wave 61", builder)
        self.assertIn("CURRENT ARM64 ITERATION BUILD PASS: Wave 62", builder)
        self.assertIn("service_wave61_app as base", service)
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
        readiness = source_release_readiness()
        self.assertTrue(readiness["source_ready"])
        self.assertFalse(readiness["operational_inputs_complete"])
        self.assertFalse(readiness["production_ready"])


if __name__ == "__main__":
    unittest.main()
