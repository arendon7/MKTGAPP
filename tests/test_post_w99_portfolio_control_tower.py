import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service_post_w99_portfolio_control_tower_app import (
    AppRuntime,
    create_server,
    portfolio_control_tower_projection,
)


ROOT = Path(__file__).resolve().parents[1]


def _action(company_id, company_name, *, rank=None, urgency=None, blocking=False, title="Acción", value_tag="x"):
    queue = []
    summary = {
        "queue_total": 0, "blocking": 0, "critical": 0, "high": 0, "medium": 0, "low": 0,
        "by_source": {}, "decision_reviews_ready": 0, "decision_follow_through": 0,
    }
    if rank is not None:
        urgency = urgency or "MEDIUM"
        item = {
            "id": f"item-{value_tag}", "rank": rank, "urgency": urgency, "source": "COMMERCIAL",
            "kind": "test", "title": title, "detail": "Hecho observable", "blocking": blocking,
            "action": {"label": "Abrir", "view": "crm", "opportunity_id": None},
            "reason": {"code": "TEST", "explanation": "Prioridad canónica de prueba"},
        }
        queue = [item]
        summary["queue_total"] = 1
        summary[urgency.lower()] = 1
        summary["blocking"] = int(blocking)
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": company_id, "name": company_name},
        "summary": summary,
        "next_action": queue[0] if queue else None,
        "queue": queue,
    }


def _commercial(company_id, company_name, *, currency=None, open_value=0, won_value=0, captured=0):
    values = {}
    if currency:
        values[currency] = {
            "open_count": int(bool(open_value)), "won_count": int(bool(won_value)), "lost_count": 0,
            "open_value": open_value, "won_value": won_value, "lost_value": 0,
        }
    return {
        "schema": "binario.marketing.commercial-outcomes.v1",
        "company": {"id": company_id, "name": company_name},
        "summary": {
            "captured_leads": captured, "converted_leads": 0,
            "converted_without_opportunity": 0, "attributed_opportunities": 0,
            "attributed_won": int(bool(won_value)), "value_by_currency": values,
        },
    }


class PostW99PortfolioControlTowerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_empty_portfolio_is_honest_and_non_authoritative(self):
        payload = self.runtime.portfolio_control_tower()
        self.assertEqual(payload["schema"], "binario.marketing.portfolio-control-tower.v1")
        self.assertEqual(payload["summary"]["active_companies"], 0)
        self.assertEqual(payload["companies"], [])
        self.assertEqual(payload["queue"], [])
        self.assertIsNone(payload["next_action"])
        self.assertTrue(payload["contracts"]["no_opaque_health_score"])
        self.assertTrue(payload["contracts"]["no_value_weighted_priority"])
        self.assertTrue(payload["contracts"]["no_fx_conversion"])
        self.assertTrue(payload["safety"]["read_only_projection"])
        self.assertFalse(payload["safety"]["forecasting"])
        self.assertFalse(payload["safety"]["causal_inference"])

    def test_global_order_comes_from_action_center_not_commercial_value(self):
        alpha = self.runtime.create_company({"name": "Alpha"})
        beta = self.runtime.create_company({"name": "Beta"})
        actions = {
            alpha["id"]: _action(alpha["id"], "Alpha", rank=40, urgency="HIGH", title="Alpha hoy", value_tag="a"),
            beta["id"]: _action(beta["id"], "Beta", rank=5, urgency="CRITICAL", blocking=True, title="Beta bloqueada", value_tag="b"),
        }
        commercial = {
            alpha["id"]: _commercial(alpha["id"], "Alpha", currency="COP", open_value=900000000, captured=9),
            beta["id"]: _commercial(beta["id"], "Beta", currency="USD", open_value=10, captured=1),
        }
        with patch.object(self.runtime, "action_center", side_effect=lambda cid: actions[cid]), patch.object(
            self.runtime, "commercial_outcomes", side_effect=lambda cid: commercial[cid]
        ):
            payload = portfolio_control_tower_projection(self.runtime)
        self.assertEqual(payload["next_action"]["company"]["id"], beta["id"])
        self.assertEqual(payload["companies"][0]["company"]["id"], beta["id"])
        self.assertEqual(payload["companies"][0]["attention"]["state"], "BLOCKING")
        self.assertEqual(payload["summary"]["companies_blocking"], 1)
        self.assertEqual(payload["summary"]["value_by_currency"]["COP"]["open_value"], 900000000)
        self.assertEqual(payload["summary"]["value_by_currency"]["USD"]["open_value"], 10)
        self.assertNotIn("TOTAL", payload["summary"]["value_by_currency"])

    def test_same_currency_values_sum_but_never_change_priority(self):
        alpha = self.runtime.create_company({"name": "Alpha"})
        beta = self.runtime.create_company({"name": "Beta"})
        actions = {
            alpha["id"]: _action(alpha["id"], "Alpha", rank=20, urgency="HIGH", value_tag="a"),
            beta["id"]: _action(beta["id"], "Beta", rank=30, urgency="HIGH", value_tag="b"),
        }
        commercial = {
            alpha["id"]: _commercial(alpha["id"], "Alpha", currency="COP", open_value=1),
            beta["id"]: _commercial(beta["id"], "Beta", currency="COP", open_value=999999999),
        }
        with patch.object(self.runtime, "action_center", side_effect=lambda cid: actions[cid]), patch.object(
            self.runtime, "commercial_outcomes", side_effect=lambda cid: commercial[cid]
        ):
            payload = self.runtime.portfolio_control_tower()
        self.assertEqual(payload["companies"][0]["company"]["id"], alpha["id"])
        self.assertEqual(payload["summary"]["value_by_currency"]["COP"]["open_value"], 1000000000)
        self.assertTrue(payload["contracts"]["action_center_is_priority_authority"])

    def test_inactive_company_is_excluded(self):
        active = self.runtime.create_company({"name": "Activa"})
        inactive = self.runtime.create_company({"name": "Inactiva"})
        self.runtime.companies.update(inactive["id"], {"active": False})
        payload = self.runtime.portfolio_control_tower()
        self.assertEqual(payload["summary"]["active_companies"], 1)
        self.assertEqual([row["company"]["id"] for row in payload["companies"]], [active["id"]])

    def test_real_company_projection_reuses_existing_company_scoped_truth(self):
        company = self.runtime.create_company({"name": "Greenatics"})
        payload = self.runtime.portfolio_control_tower()
        self.assertEqual(payload["summary"]["active_companies"], 1)
        row = payload["companies"][0]
        self.assertEqual(row["company"]["id"], company["id"])
        self.assertIn(row["attention"]["state"], {"CLEAR", "LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKING"})
        self.assertIsInstance(row["commercial"]["value_by_currency"], dict)
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["business_mutation_performed"])

    def test_http_and_frontend_are_get_only_and_switch_context_via_existing_ops_state(self):
        company = self.runtime.create_company({"name": "HTTP Portfolio"})
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/decision-review.js", timeout=5) as response:
                bootstrap = response.read().decode("utf-8")
            self.assertIn("portfolio-control-tower.js", bootstrap)
            self.assertIn("data-post-w99-portfolio-control-tower", bootstrap)
            with urlopen(root + "/portfolio-control-tower.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Portfolio Control Tower", ui)
            self.assertIn("marketingOpsState.selectedCompanyId=companyId", ui)
            self.assertIn("refreshMarketingOps", ui)
            with urlopen(root + "/api/portfolio-control-tower", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.portfolio-control-tower.v1")
            self.assertEqual(payload["companies"][0]["company"]["id"], company["id"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        ui = (ROOT / "web" / "portfolio-control-tower.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_control_tower_app.py").read_text(encoding="utf-8")
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", "setInterval", "sendBeacon", "fetch('https://"):
            self.assertNotIn(forbidden, ui)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)


if __name__ == "__main__":
    unittest.main()
