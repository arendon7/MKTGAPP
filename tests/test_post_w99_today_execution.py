import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_today_execution_app import (
    AppRuntime,
    compose_today_execution,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


def action(action_id, rank, urgency, source="OPERATIONS", *, blocking=False, due_at=None, value=None):
    row = {
        "id": action_id,
        "rank": rank,
        "urgency": urgency,
        "source": source,
        "kind": action_id,
        "title": f"Acción {action_id}",
        "detail": f"Detalle {action_id}",
        "action": {"label": f"Abrir {action_id}", "view": "home"},
        "reason": {"code": action_id.upper(), "explanation": f"Razón {action_id}"},
        "due_at": due_at,
        "blocking": blocking,
        "requires_human_action": True,
        "read_only_recommendation": True,
    }
    if value is not None:
        row["value"] = value
    return row


def cockpit():
    return {
        "status": {"state": "ATTENTION", "headline": "Hay frentes que requieren atención"},
        "commercial": {"pipeline": {"open_opportunities": 7, "requires_attention": 2}},
        "campaigns": {"active": 3, "requires_attention": 1},
    }


class TodayProjectionTests(unittest.TestCase):
    def test_first_five_are_preserved_in_exact_action_center_order(self):
        queue = [
            action("a", 50, "MEDIUM", value=100000000),
            action("b", 1, "LOW", value=1),
            action("c", 99, "CRITICAL", blocking=True),
            action("d", 10, "HIGH"),
            action("e", 20, "MEDIUM"),
            action("f", 0, "CRITICAL"),
        ]
        payload = compose_today_execution(
            company={"id": "c1", "name": "Empresa"},
            action_center={"queue": queue},
            cockpit=cockpit(),
        )
        self.assertEqual([row["id"] for row in payload["plan"]], ["a", "b", "c", "d", "e"])
        self.assertEqual([row["rank"] for row in payload["plan"]], [50, 1, 99, 10, 20])
        self.assertEqual(payload["overflow"]["count"], 1)
        self.assertEqual(payload["overflow"]["next_action_id"], "f")
        self.assertTrue(payload["contracts"]["canonical_order_preserved"])
        self.assertTrue(payload["contracts"]["no_reprioritization"])
        self.assertTrue(payload["contracts"]["no_value_weighting"])

    def test_focus_labels_are_presentation_only(self):
        queue = [
            action("critical", 0, "CRITICAL", blocking=True),
            action("high", 1, "HIGH"),
            action("medium", 2, "MEDIUM"),
            action("low", 3, "LOW"),
        ]
        payload = compose_today_execution(
            company={"id": "c1", "name": "Empresa"},
            action_center={"queue": queue},
            cockpit=cockpit(),
        )
        self.assertEqual([row["operator"]["focus"] for row in payload["plan"]], ["NOW", "NOW", "TODAY", "OPTIONAL"])
        self.assertEqual(payload["status"]["state"], "BLOCKED")
        self.assertEqual(payload["summary"]["now"], 2)
        self.assertEqual(payload["summary"]["today"], 1)
        self.assertEqual(payload["summary"]["optional"], 1)
        self.assertEqual(payload["primary_action"]["id"], "critical")

    def test_low_only_plan_is_maintenance_not_false_urgency(self):
        payload = compose_today_execution(
            company={"id": "c1", "name": "Empresa"},
            action_center={"queue": [action("low", 80, "LOW", source="SETUP")]},
            cockpit=cockpit(),
        )
        self.assertEqual(payload["status"]["state"], "MAINTENANCE")
        self.assertEqual(payload["summary"]["optional"], 1)
        self.assertEqual(payload["summary"]["now"], 0)
        self.assertEqual(payload["summary"]["today"], 0)

    def test_empty_action_center_is_clear(self):
        payload = compose_today_execution(
            company={"id": "c1", "name": "Empresa"},
            action_center={"queue": []},
            cockpit=cockpit(),
        )
        self.assertEqual(payload["status"]["state"], "CLEAR")
        self.assertIsNone(payload["primary_action"])
        self.assertEqual(payload["summary"]["planned"], 0)
        self.assertEqual(payload["summary"]["remaining_queue"], 0)

    def test_limit_is_bounded_and_does_not_change_canonical_queue(self):
        queue = [action(str(index), index, "MEDIUM") for index in range(6)]
        payload = compose_today_execution(
            company={"id": "c1", "name": "Empresa"},
            action_center={"queue": queue},
            cockpit=cockpit(),
            limit=3,
        )
        self.assertEqual([row["id"] for row in payload["plan"]], ["0", "1", "2"])
        self.assertEqual(len(queue), 6)
        with self.assertRaises(ValueError):
            compose_today_execution(company={"id": "c1"}, action_center={"queue": queue}, cockpit=cockpit(), limit=0)
        with self.assertRaises(ValueError):
            compose_today_execution(company={"id": "c1"}, action_center={"queue": queue}, cockpit=cockpit(), limit=6)
        with self.assertRaises(ValueError):
            compose_today_execution(company={"id": "c1"}, action_center={"queue": queue}, cockpit=cockpit(), limit=True)


class TodayRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company_a = self.runtime.create_company({"name": "Empresa A"})
        self.company_b = self.runtime.create_company({"name": "Empresa B"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_terminal_runtime_preserves_portfolio_cockpit_and_today(self):
        portfolio = self.runtime.portfolio_control_tower()
        cockpit_payload = self.runtime.executive_cockpit(self.company_a["id"])
        today = self.runtime.today_execution(self.company_a["id"])
        self.assertEqual(portfolio["schema"], "binario.marketing.portfolio-control-tower.v1")
        self.assertEqual(cockpit_payload["schema"], "binario.marketing.executive-cockpit.v1")
        self.assertEqual(today["schema"], "binario.marketing.today-execution.v1")
        self.assertEqual(today["company"]["id"], self.company_a["id"])
        self.assertNotEqual(today["company"]["id"], self.company_b["id"])
        canonical = self.runtime.action_center(self.company_a["id"])["queue"]
        self.assertEqual([row["id"] for row in today["plan"]], [row["id"] for row in canonical[:5]])

    def test_http_bootstrap_chain_reaches_today_and_all_endpoints_coexist(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/decision-review.js", timeout=5) as response:
                self.assertIn("portfolio-control-tower.js", response.read().decode("utf-8"))
            with urlopen(base + "/portfolio-control-tower.js", timeout=5) as response:
                self.assertIn("executive-cockpit.js", response.read().decode("utf-8"))
            with urlopen(base + "/executive-cockpit.js", timeout=5) as response:
                executive_bootstrap = response.read().decode("utf-8")
            self.assertIn("today-execution.js", executive_bootstrap)
            self.assertIn("data-post-w99-today-execution", executive_bootstrap)

            with urlopen(base + "/api/portfolio-control-tower", timeout=5) as response:
                portfolio = json.loads(response.read().decode("utf-8"))
            with urlopen(base + f"/api/companies/{self.company_a['id']}/executive-cockpit", timeout=5) as response:
                executive = json.loads(response.read().decode("utf-8"))
            with urlopen(base + f"/api/companies/{self.company_a['id']}/today-execution", timeout=5) as response:
                today = json.loads(response.read().decode("utf-8"))
            self.assertEqual(portfolio["schema"], "binario.marketing.portfolio-control-tower.v1")
            self.assertEqual(executive["schema"], "binario.marketing.executive-cockpit.v1")
            self.assertEqual(today["schema"], "binario.marketing.today-execution.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_today_layer_remains_get_only_and_ui_has_no_mutation_transport(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_today_execution_app.py").read_text(encoding="utf-8")
        ui = (ROOT / "web" / "today-execution.js").read_text(encoding="utf-8")
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertIn("service_post_w99_integrated_cockpit_app as base", service)
        self.assertNotIn("method:'POST'", ui)
        self.assertNotIn('method:"POST"', ui)
        self.assertNotIn("sendBeacon", ui)
        self.assertIn("Actualizar plan", ui)
        self.assertIn("actionCenterOpen", ui)


if __name__ == "__main__":
    unittest.main()
