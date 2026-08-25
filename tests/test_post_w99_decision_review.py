import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_decision_review_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PostW99DecisionReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.other = self.runtime.create_company({"name": "Otra Empresa"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _campaign(self, name="Campaña decisión", company=None):
        company = company or self.company
        return self.runtime.create_campaign(company["id"], {
            "name": name,
            "objective": "LEADS",
            "status": "IN_PROGRESS",
            "channels": ["instagram"],
        })

    def _decision(self, campaign, action="ITERATE", snapshot_id=None, rationale="Ajustar propuesta y volver a medir"):
        payload = {
            "entity_kind": "CAMPAIGN",
            "entity_id": campaign["id"],
            "action": action,
            "rationale": rationale,
        }
        if snapshot_id:
            payload["snapshot_id"] = snapshot_id
        return self.runtime.record_learning_decision(self.company["id"], payload)

    def _observed_snapshot(self, campaign, reach=100):
        row = self.runtime.learning.create_snapshot(self.company["id"], {
            "date_preset": "last_7d",
            "social": {
                "coverage": {},
                "totals": {"reach": reach},
                "observations": [{
                    "publication_id": "synthetic_local_observation",
                    "channel": "instagram",
                    "kind": "image",
                    "remote_state": "PUBLISHED",
                    "creative_media_id": None,
                    "campaign_id": campaign["id"],
                    "metrics": {"reach": reach, "likes": 10},
                    "available": True,
                    "provider_error": False,
                }],
            },
            "paid_media": {
                "coverage": {},
                "currencies": [],
                "spend_aggregated": True,
                "totals": {},
                "totals_by_currency": {},
                "observations": [],
            },
            "crm": {},
            "coverage": {},
        })
        return row

    def _tracking_link(self, campaign):
        return self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": campaign["id"],
            "destination_url": "https://example.com/form",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
        })

    def test_empty_company_is_honest_and_read_only(self):
        payload = self.runtime.decision_review(self.company["id"])
        self.assertEqual(payload["schema"], "binario.marketing.decision-review.v1")
        self.assertEqual(payload["summary"]["campaigns_with_decision"], 0)
        self.assertEqual(payload["campaigns"], [])
        self.assertFalse(payload["model"]["causal_inference"])
        self.assertFalse(payload["model"]["automatic_success_scoring"])
        self.assertTrue(payload["safety"]["read_only_projection"])

    def test_decision_without_later_evidence_waits_instead_of_guessing(self):
        campaign = self._campaign(); decision = self._decision(campaign)
        payload = self.runtime.decision_review(self.company["id"])
        row = payload["campaigns"][0]
        self.assertEqual(row["decision"]["id"], decision["id"])
        self.assertEqual(row["review"]["state"], "AWAITING_EVIDENCE")
        self.assertFalse(row["review"]["requires_attention"])
        self.assertEqual(row["post_decision_evidence"]["basis"], [])
        self.assertFalse(row["review"]["causality_claimed"])

    def test_observed_snapshot_after_decision_opens_human_review(self):
        campaign = self._campaign(); self._decision(campaign, action="SCALE")
        snapshot = self._observed_snapshot(campaign, reach=250)
        payload = self.runtime.decision_review(self.company["id"]); row = payload["campaigns"][0]
        self.assertEqual(row["review"]["state"], "READY_FOR_REVIEW")
        self.assertTrue(row["review"]["requires_attention"])
        self.assertIn("OBSERVED_MARKETING_SNAPSHOT", row["post_decision_evidence"]["basis"])
        self.assertEqual(row["post_decision_evidence"]["observed_marketing"]["snapshot_id"], snapshot.id)
        self.assertEqual(row["post_decision_evidence"]["observed_marketing"]["metrics"]["organic_reach"], 250)
        self.assertFalse(row["review"]["success_or_failure_inferred"])

    def test_snapshot_before_decision_does_not_count_as_post_decision_evidence(self):
        campaign = self._campaign(); snapshot = self._observed_snapshot(campaign, reach=99)
        self._decision(campaign, action="HOLD", snapshot_id=snapshot.id)
        row = self.runtime.decision_review(self.company["id"])["campaigns"][0]
        self.assertEqual(row["review"]["state"], "AWAITING_EVIDENCE")
        self.assertIsNone(row["post_decision_evidence"]["observed_marketing"])
        self.assertEqual(row["decision"]["anchor_snapshot"]["id"], snapshot.id)

    def test_exact_post_decision_crm_update_opens_review_without_currency_mixing(self):
        campaign = self._campaign(); link = self._tracking_link(campaign); self._decision(campaign, action="ITERATE")
        lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "FIRST_PARTY_FORM",
            "name": "Lead atribuido",
            "email": "lead@example.com",
            "attribution_capture": {"bm_tid": link["tracking_code"]},
        })
        self.runtime.convert_lead(self.company["id"], lead["id"], {
            "action": "CREATE_CONTACT",
            "opportunity": {"title": "Venta", "stage": "WON", "value": 700000, "currency": "COP"},
        })
        row = self.runtime.decision_review(self.company["id"])["campaigns"][0]
        self.assertEqual(row["review"]["state"], "READY_FOR_REVIEW")
        self.assertIn("ATTRIBUTED_CRM_UPDATE", row["post_decision_evidence"]["basis"])
        self.assertEqual(row["post_decision_evidence"]["attributed_crm_update_count"], 1)
        self.assertEqual(row["post_decision_evidence"]["attributed_crm_updates"][0]["credit_model"], "LAST_CAPTURED_TOUCH")
        self.assertEqual(row["current_commercial"]["value_by_currency"]["COP"]["won_value"], 700000)
        self.assertTrue(self.runtime.decision_review(self.company["id"])["contracts"]["currencies_remain_separate"])

    def test_retire_requires_follow_through_until_campaign_becomes_terminal(self):
        campaign = self._campaign(); self._decision(campaign, action="RETIRE")
        row = self.runtime.decision_review(self.company["id"])["campaigns"][0]
        self.assertEqual(row["review"]["state"], "FOLLOW_THROUGH_REQUIRED")
        self.assertEqual(row["review"]["next_action"]["code"], "FOLLOW_THROUGH_RETIRE")
        self.runtime.campaigns.update(self.company["id"], campaign["id"], {"status": "ARCHIVED"})
        row = self.runtime.decision_review(self.company["id"])["campaigns"][0]
        self.assertEqual(row["review"]["state"], "READY_FOR_REVIEW")
        self.assertIn("CAMPAIGN_TERMINAL_STATE", row["post_decision_evidence"]["basis"])

    def test_only_latest_campaign_decision_is_reviewed(self):
        campaign = self._campaign(); first = self._decision(campaign, action="ITERATE", rationale="Primera")
        second = self._decision(campaign, action="RETIRE", rationale="Segunda")
        row = self.runtime.decision_review(self.company["id"])["campaigns"][0]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(row["decision"]["id"], second["id"])
        self.assertEqual(row["decision"]["rationale"], "Segunda")
        self.assertEqual(row["review"]["state"], "FOLLOW_THROUGH_REQUIRED")

    def test_company_scope_results_command_and_action_center_are_integrated(self):
        campaign = self._campaign(); self._decision(campaign); self._observed_snapshot(campaign)
        foreign = self._campaign("Ajena", self.other)
        self.runtime.record_learning_decision(self.other["id"], {
            "entity_kind": "CAMPAIGN", "entity_id": foreign["id"], "action": "ITERATE", "rationale": "Ajena"
        })
        review = self.runtime.decision_review(self.company["id"])
        self.assertEqual({row["campaign"]["id"] for row in review["campaigns"]}, {campaign["id"]})
        results = self.runtime.results_intelligence_workspace(self.company["id"])
        result_row = next(row for row in results["campaigns"] if row["campaign"]["id"] == campaign["id"])
        self.assertEqual(result_row["decision_review"]["state"], "READY_FOR_REVIEW")
        self.assertIn("decision_review", results)
        command = self.runtime.marketing_command_center(self.company["id"])
        self.assertEqual(command["decision_review"]["summary"]["ready_for_review"], 1)
        action = self.runtime.action_center(self.company["id"])
        items = [row for row in action["queue"] if row["reason"]["code"] == "DECISION_READY_FOR_REVIEW"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["action"]["campaign_id"], campaign["id"])
        self.assertEqual(action["summary"]["decision_reviews_ready"], 1)
        self.assertTrue(action["contracts"]["decision_review_is_temporal_not_causal"])

    def test_http_bootstrap_and_frontend_are_get_only(self):
        campaign = self._campaign(); self._decision(campaign)
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/commercial-outcomes.js", timeout=5) as response:
                bootstrap = response.read().decode("utf-8")
            self.assertIn("decision-review.js", bootstrap)
            self.assertIn("data-post-w99-decision-review", bootstrap)
            with urlopen(root + "/decision-review.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Revisión de decisiones", ui)
            self.assertIn("no demuestra", ui)
            with urlopen(root + f"/api/companies/{self.company['id']}/decision-review", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.decision-review.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        ui = (ROOT / "web" / "decision-review.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_decision_review_app.py").read_text(encoding="utf-8")
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", "setInterval", "sendBeacon", "fetch('https://"):
            self.assertNotIn(forbidden, ui)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)


if __name__ == "__main__":
    unittest.main()
