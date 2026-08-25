import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_executive_cockpit_app import (
    AppRuntime,
    compose_executive_cockpit,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    return {
        "company": {"id": "company_demo", "name": "Demo"},
        "action_center": {
            "summary": {"queue_total": 0, "blocking": 0, "critical": 0, "high": 0},
            "queue": [],
            "next_action": None,
        },
        "pipeline": {
            "summary": {
                "opportunities": 0, "open_opportunities": 0, "requires_attention": 0,
                "proposals": 0, "won": 0, "lost": 0, "amounts_by_currency": [],
            }
        },
        "outcomes": {
            "summary": {
                "attention": 0, "captured_leads": 0, "converted_leads": 0,
                "attributed_opportunities": 0, "attributed_won": 0,
                "value_by_currency": {},
            }
        },
        "results": {
            "summary": {
                "active_campaigns": 0, "requires_attention": 0,
                "with_observed_evidence": 0, "with_attributed_opportunities": 0,
                "with_human_decision": 0,
            },
            "latest_snapshot": None,
        },
        "review": {
            "summary": {
                "campaigns_with_decision": 0, "ready_for_review": 0,
                "follow_through_required": 0, "awaiting_evidence": 0,
            }
        },
    }


class PostW99ExecutiveCockpitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_stable_inputs_do_not_create_fake_health_score(self):
        payload = compose_executive_cockpit(**_inputs())
        self.assertEqual(payload["schema"], "binario.marketing.executive-cockpit.v1")
        self.assertEqual(payload["status"]["state"], "STABLE")
        self.assertTrue(all(row["state"] == "STABLE" for row in payload["lanes"]))
        self.assertTrue(payload["contracts"]["no_business_health_score"])
        self.assertTrue(payload["contracts"]["no_probability_of_close"])
        self.assertTrue(payload["contracts"]["no_causal_inference"])

    def test_blocker_is_elevated_without_reordering_action_center(self):
        data = _inputs()
        first = {"id": "first", "source": "OPERATIONS", "urgency": "CRITICAL", "blocking": True, "title": "Resolver publicación", "detail": "Falló", "action": {"view": "execution", "label": "Resolver"}}
        second = {"id": "second", "source": "COMMERCIAL", "urgency": "HIGH", "blocking": False, "title": "Lead", "detail": "Resolver", "action": {"view": "commercial-desk", "label": "Abrir"}}
        data["action_center"] = {
            "summary": {"queue_total": 2, "blocking": 1, "critical": 1, "high": 1},
            "queue": [first, second], "next_action": first,
        }
        payload = compose_executive_cockpit(**data)
        self.assertEqual(payload["status"]["state"], "BLOCKED")
        self.assertEqual(payload["next_action"]["id"], "first")
        self.assertEqual([row["id"] for row in payload["top_actions"]], ["first", "second"])
        operations = next(row for row in payload["lanes"] if row["key"] == "OPERATIONS")
        commercial = next(row for row in payload["lanes"] if row["key"] == "COMMERCIAL")
        self.assertEqual(operations["state"], "BLOCKED")
        self.assertEqual(commercial["state"], "ATTENTION")
        self.assertTrue(payload["contracts"]["action_center_order_preserved"])
        self.assertTrue(payload["contracts"]["lane_state_uses_authoritative_source"])

    def test_pipeline_attention_is_not_probability_or_forecast(self):
        data = _inputs()
        data["pipeline"]["summary"].update({"opportunities": 4, "open_opportunities": 3, "requires_attention": 2})
        payload = compose_executive_cockpit(**data)
        self.assertEqual(payload["status"]["state"], "ATTENTION")
        commercial = next(row for row in payload["lanes"] if row["key"] == "COMMERCIAL")
        self.assertEqual(commercial["state"], "ATTENTION")
        self.assertEqual(commercial["metrics"]["requires_attention"], 2)
        self.assertTrue(payload["contracts"]["no_probability_of_close"])

    def test_currencies_remain_separate(self):
        data = _inputs()
        data["pipeline"]["summary"]["amounts_by_currency"] = [
            {"currency": "COP", "value": 500000, "opportunities": 1},
            {"currency": "USD", "value": 300, "opportunities": 1},
        ]
        data["outcomes"]["summary"]["value_by_currency"] = {
            "COP": {"won_count": 1, "won_value": 250000},
            "USD": {"won_count": 1, "won_value": 120},
        }
        payload = compose_executive_cockpit(**data)
        self.assertEqual(payload["commercial"]["pipeline"]["open_amounts_by_currency"][0]["currency"], "COP")
        self.assertEqual(payload["commercial"]["pipeline"]["open_amounts_by_currency"][1]["currency"], "USD")
        self.assertEqual(payload["commercial"]["attribution"]["value_by_currency"]["COP"]["won_value"], 250000)
        self.assertEqual(payload["commercial"]["attribution"]["value_by_currency"]["USD"]["won_value"], 120)
        self.assertTrue(payload["contracts"]["no_mixed_currency_aggregation"])

    def test_real_runtime_is_company_scoped_and_includes_decision_governance(self):
        campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Campaña ejecutiva", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]
        })
        self.runtime.record_learning_decision(self.company["id"], {
            "entity_kind": "CAMPAIGN", "entity_id": campaign["id"], "action": "HOLD",
            "rationale": "Esperar evidencia adicional antes de cambiar inversión.",
        })
        payload = self.runtime.executive_cockpit(self.company["id"])
        self.assertEqual(payload["company"]["id"], self.company["id"])
        self.assertEqual(payload["campaigns"]["decision_review"]["campaigns_with_decision"], 1)
        self.assertEqual(payload["campaigns"]["decision_review"]["awaiting_evidence"], 1)
        self.assertTrue(payload["safety"]["company_scoped"])
        self.assertTrue(payload["safety"]["read_only_projection"])

    def test_http_bootstrap_endpoint_and_frontend_are_read_only(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/decision-review.js", timeout=5) as response:
                bootstrap = response.read().decode("utf-8")
            self.assertIn("executive-cockpit.js", bootstrap)
            self.assertIn("data-post-w99-executive-cockpit", bootstrap)
            with urlopen(base + "/executive-cockpit.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Marketing Command View", ui)
            self.assertIn("no suma COP + USD", ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/executive-cockpit", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.executive-cockpit.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        ui = (ROOT / "web" / "executive-cockpit.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_executive_cockpit_app.py").read_text(encoding="utf-8")
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", "setInterval", "sendBeacon", "fetch('https://"):
            self.assertNotIn(forbidden, ui)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)

    def test_release_boundary_is_documented(self):
        doc = (ROOT / "docs" / "POST_W99_EXECUTIVE_COCKPIT.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No constituye W100", doc)
        self.assertIn("sin score", doc.lower())


if __name__ == "__main__":
    unittest.main()
