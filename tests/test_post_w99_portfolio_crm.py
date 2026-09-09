from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.portfolio_crm import PORTFOLIO_CRM_SCHEMA, build_portfolio_crm
from binario_marketing.service_post_w99_portfolio_crm_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PortfolioCRMPureTests(unittest.TestCase):
    def test_projection_preserves_owner_classifications_and_omits_contact_pii(self):
        first = {"id": "company_" + "1" * 24, "name": "Marca Uno"}
        second = {"id": "company_" + "2" * 24, "name": "Marca Dos"}
        pipelines = {
            first["id"]: {
                "summary": {"open_opportunities": 2},
                "lanes": [{"opportunities": [
                    {"id": "opp-a", "title": "Propuesta A", "stage": "PROPOSAL", "value": 100, "currency": "COP", "notes": "secret notes", "contact": {"name": "Persona", "email": "secret@example.com"}, "next_action_at": "2026-09-08T10:00:00+00:00", "followup": {"pending_activities": 1, "overdue_activities": 1, "next_due_at": "2026-09-08T09:00:00+00:00", "next_activity_id": "act-a"}, "attention": {"code": "OVERDUE_FOLLOWUP", "label": "Seguimiento vencido", "priority": 0, "requires_attention": True}},
                    {"id": "opp-closed", "title": "Ganada", "stage": "WON", "attention": {"code": "CLOSED", "label": "Cerrada", "priority": 90, "requires_attention": False}},
                ]}],
            },
            second["id"]: {
                "summary": {"open_opportunities": 1},
                "lanes": [{"opportunities": [{"id": "opp-b", "title": "Venta B", "stage": "NEW", "value": None, "currency": "COP", "next_action_at": None, "followup": {"pending_activities": 0, "overdue_activities": 0, "next_due_at": None, "next_activity_id": None}, "attention": {"code": "NO_FOLLOWUP", "label": "Sin siguiente acción", "priority": 1, "requires_attention": True}}]}],
            },
        }
        workdesks = {
            first["id"]: {"crm": {"pending": 2}, "queue": [{"priority": 2, "kind": "crm_overdue", "title": "Seguimiento vencido", "detail": "private activity body phone +57 300 000 0000", "due_at": "2026-09-08T09:00:00+00:00", "entity_id": "act-a", "contact_id": "contact-secret", "opportunity_id": "opp-a"}]},
            second["id"]: {"crm": {"pending": 1}, "queue": [{"priority": 5, "kind": "crm_unscheduled", "title": "Seguimiento sin fecha", "detail": "private body", "due_at": None, "entity_id": "act-b", "contact_id": "contact-secret-2", "opportunity_id": "opp-b"}]},
        }
        payload = build_portfolio_crm([second, first], pipelines, workdesks, generated_at="2026-09-09T12:00:00+00:00")
        self.assertEqual(payload["schema"], PORTFOLIO_CRM_SCHEMA)
        self.assertEqual([row["id"] for row in payload["opportunities"]], ["opp-a", "opp-b"])
        self.assertEqual([row["id"] for row in payload["activities"]], ["act-a", "act-b"])
        self.assertEqual(payload["summary"]["open_opportunities"], 3)
        self.assertEqual(payload["summary"]["pending_activities"], 3)
        self.assertTrue(payload["contracts"]["no_cross_type_priority_score"])
        serialized = json.dumps(payload)
        for forbidden in ("secret@example.com", "contact-secret", "private activity body", "+57 300", "secret notes", '"contact"', '"notes"', '"detail"'):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(payload["activities"][0]["opportunity_title"], "Propuesta A")
        self.assertEqual(payload["activities"][0]["action"]["entity_id"], "act-a")
        self.assertEqual(payload["opportunities"][0]["action"]["opportunity_id"], "opp-a")

    def test_non_attention_and_completed_owner_rows_are_not_invented(self):
        company = {"id": "company_" + "3" * 24, "name": "Marca"}
        payload = build_portfolio_crm([company], {company["id"]: {"summary": {"open_opportunities": 1}, "lanes": [{"opportunities": [{"id": "opp-ok", "title": "OK", "stage": "INTERESTED", "attention": {"code": "ON_TRACK", "label": "En curso", "priority": 4, "requires_attention": False}}]}]}}, {company["id"]: {"crm": {"pending": 0}, "queue": []}})
        self.assertEqual(payload["opportunities"], [])
        self.assertEqual(payload["activities"], [])
        self.assertEqual(payload["summary"]["companies_with_attention"], 0)


class PortfolioCRMRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.companies.create("Marca Runtime")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_runtime_and_http_are_local_read_only(self):
        payload = self.runtime.portfolio_crm()
        self.assertEqual(payload["schema"], PORTFOLIO_CRM_SCHEMA)
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["crm_mutation_performed"])
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/api/portfolio/crm", timeout=5) as response:
                api_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(api_payload["schema"], PORTFOLIO_CRM_SCHEMA)
            with urlopen(root + "/portfolio-crm.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_PORTFOLIO_CRM", source)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_contract_has_no_portfolio_mutation_or_background_loop(self):
        source = (ROOT / "web" / "portfolio-crm.js").read_text(encoding="utf-8")
        for required in ("CRM / MULTIEMPRESA", "/api/portfolio/crm", "portfolioNavigate", "actionCenterOpen", "Volver a todas las empresas", "Commercial Pipeline"):
            self.assertIn(required, source)
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'DELETE'", "setInterval(", "setTimeout(", "MutationObserver", "localStorage", "sessionStorage", "fetch('https://", 'fetch("https://'):
            self.assertNotIn(forbidden, source)

    def test_source_bundle_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_crm_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_inbox_app as base", service)
        self.assertIn("/api/portfolio/crm", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_crm_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PORTFOLIO_CRM.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("exactamente tres workflows", docs.casefold())


if __name__ == "__main__":
    unittest.main()
