from __future__ import annotations

import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.results_freshness import (
    ACTIVE_RESULTS_MAX_AGE_SECONDS,
    apply_results_decision_freshness,
    snapshot_decision_freshness,
)
from binario_marketing.service_post_w99_action_center_app import compose_action_center
from binario_marketing.service_post_w99_results_freshness_guard_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 6, 18, 0, tzinfo=timezone.utc)


def _results(*, age_hours=25, status="IN_PROGRESS", distributed=True, next_code="RECORD_DECISION") -> dict:
    created_at = (NOW - timedelta(hours=age_hours)).isoformat()
    return {
        "schema": "binario.marketing.results-intelligence.v1",
        "latest_snapshot": {"id": "learning_" + "a" * 24, "created_at": created_at, "date_preset": "last_7d", "coverage": {}},
        "summary": {"campaigns": 1, "active_campaigns": 1, "requires_attention": 1},
        "campaigns": [{
            "campaign": {"id": "campaign_" + "b" * 24, "name": "Campaña", "status": status},
            "execution": {
                "organic": {"counts": {"PUBLISHED": 1 if distributed else 0}, "failed": 0},
                "paid": {"remote_paused": False},
            },
            "evidence": {"level": "OBSERVED", "has_signal": True, "observed": True, "summary": "100 de alcance"},
            "decision": None,
            "next_action": {"code": next_code, "label": "Registrar decisión humana", "view": "analytics"},
            "priority": 3,
            "requires_attention": True,
        }],
        "ai": {"configured": True},
    }


class ResultsFreshnessPureTests(unittest.TestCase):
    def test_exact_24h_is_current_and_one_second_later_requires_refresh(self):
        snapshot = {"created_at": (NOW - timedelta(seconds=ACTIVE_RESULTS_MAX_AGE_SECONDS)).isoformat()}
        current = snapshot_decision_freshness(snapshot, now=NOW)
        self.assertEqual(current["state"], "CURRENT")
        self.assertFalse(current["decision_refresh_required"])
        snapshot["created_at"] = (NOW - timedelta(seconds=ACTIVE_RESULTS_MAX_AGE_SECONDS + 1)).isoformat()
        due = snapshot_decision_freshness(snapshot, now=NOW)
        self.assertEqual(due["state"], "REFRESH_DUE")
        self.assertTrue(due["decision_refresh_required"])

    def test_old_active_distributed_snapshot_returns_to_existing_capture_results_owner(self):
        original = _results(age_hours=25)
        guarded = apply_results_decision_freshness(original, now=NOW)
        row = guarded["campaigns"][0]
        self.assertEqual(row["next_action"], {
            "code": "CAPTURE_RESULTS", "label": "Actualizar resultados antes de decidir", "view": "analytics"
        })
        self.assertEqual(row["priority"], 1)
        self.assertTrue(row["requires_attention"])
        self.assertEqual(row["evidence"]["level"], "OBSERVED")
        self.assertTrue(row["evidence"]["has_signal"])
        self.assertIn("Evidencia histórica: 100 de alcance", row["evidence"]["summary"])
        self.assertEqual(guarded["summary"]["decision_refresh_due"], 1)
        self.assertFalse(guarded["freshness_policy"]["generic_business_staleness_judgment"])
        self.assertEqual(original["campaigns"][0]["next_action"]["code"], "RECORD_DECISION")

    def test_no_distribution_and_terminal_campaigns_are_not_guarded(self):
        no_distribution = apply_results_decision_freshness(_results(distributed=False), now=NOW)
        terminal = apply_results_decision_freshness(_results(status="COMPLETED"), now=NOW)
        self.assertEqual(no_distribution["campaigns"][0]["next_action"]["code"], "RECORD_DECISION")
        self.assertFalse(no_distribution["campaigns"][0]["evidence"]["operational_freshness"]["guard_applies"])
        self.assertEqual(terminal["campaigns"][0]["next_action"]["code"], "RECORD_DECISION")
        self.assertFalse(terminal["campaigns"][0]["evidence"]["operational_freshness"]["guard_applies"])

    def test_execution_blocker_keeps_precedence_but_freshness_remains_visible(self):
        guarded = apply_results_decision_freshness(_results(next_code="FIX_EXECUTION"), now=NOW)
        row = guarded["campaigns"][0]
        self.assertEqual(row["next_action"]["code"], "FIX_EXECUTION")
        freshness = row["evidence"]["operational_freshness"]
        self.assertTrue(freshness["decision_refresh_required"])
        self.assertTrue(freshness["deferred_by_execution_blocker"])

    def test_invalid_and_future_snapshot_dates_fail_closed_for_new_decisions(self):
        invalid = _results()
        invalid["latest_snapshot"]["created_at"] = "not-a-date"
        future = _results()
        future["latest_snapshot"]["created_at"] = (NOW + timedelta(minutes=1)).isoformat()
        self.assertEqual(apply_results_decision_freshness(invalid, now=NOW)["campaigns"][0]["next_action"]["code"], "CAPTURE_RESULTS")
        future_guarded = apply_results_decision_freshness(future, now=NOW)
        self.assertEqual(future_guarded["campaigns"][0]["evidence"]["operational_freshness"]["state"], "FUTURE_OBSERVATION")
        self.assertEqual(future_guarded["campaigns"][0]["next_action"]["code"], "CAPTURE_RESULTS")

    def test_action_center_reuses_existing_capture_results_rank_and_campaign_identity(self):
        guarded = apply_results_decision_freshness(_results(), now=NOW)
        payload = compose_action_center(
            company={"id": "company_" + "c" * 24, "name": "Empresa"},
            workdesk={"queue": [], "product_gaps": []},
            commercial={"lead_queue": [], "handoffs": []},
            execution={"campaigns": []},
            results=guarded,
            command={"priorities": []},
            generated_at=NOW.isoformat(),
        )
        row = next(item for item in payload["queue"] if item["source"] == "CAMPAIGN")
        self.assertEqual(row["kind"], "capture_results")
        self.assertEqual(row["rank"], 44)
        self.assertEqual(row["action"]["campaign_id"], "campaign_" + "b" * 24)
        self.assertEqual(row["action"]["view"], "analytics")


class ResultsFreshnessRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Freshness Guard"})
        self.campaign = self.runtime.campaigns.create(self.company["id"], {
            "name": "Campaña protegida", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]
        })

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _stale_payload(self):
        payload = _results()
        payload["campaigns"][0]["campaign"]["id"] = self.campaign.id
        return apply_results_decision_freshness(payload, now=NOW)

    def test_backend_blocks_direct_campaign_decision_before_store_mutation(self):
        stale = self._stale_payload()
        with patch.object(self.runtime, "results_intelligence_workspace", return_value=stale):
            with self.assertRaisesRegex(ValueError, "actualiza los resultados"):
                self.runtime.record_learning_decision(self.company["id"], {
                    "entity_kind": "CAMPAIGN", "entity_id": self.campaign.id, "action": "HOLD", "rationale": "Esperar", "snapshot_id": None,
                })
        self.assertEqual(self.runtime.learning.list_decisions(self.company["id"]), [])

    def test_backend_blocks_direct_campaign_ai_before_provider_resolution(self):
        stale = self._stale_payload()
        with patch.object(self.runtime, "results_intelligence_workspace", return_value=stale):
            with patch.object(self.runtime.ai_credentials, "status", side_effect=AssertionError("provider resolution must not run")):
                with self.assertRaisesRegex(ValueError, "actualiza los resultados"):
                    self.runtime.generate_ai_copilot(self.company["id"], {"task": "CAMPAIGN", "campaign_id": self.campaign.id})
        self.assertEqual(self.runtime.ai_sessions.list(self.company["id"]), [])

    def test_results_endpoint_exposes_policy_without_provider_read(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + f"/api/companies/{self.company['id']}/results-intelligence", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["freshness_policy"]["max_age_hours"], 24)
            self.assertFalse(payload["freshness_policy"]["provider_refresh_automatic"])
            self.assertFalse(payload["safety"]["provider_read_performed"])
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_source_contract_keeps_three_workflows_and_frozen_main(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_results_freshness_guard_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_results_freshness_guard_app", dev)
        self.assertIn("service_post_w99_inbox_crm_identity_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("setInterval", service)
        self.assertNotIn("background", service.lower())
        docs = (ROOT / "docs" / "POST_W99_RESULTS_FRESHNESS_GUARD.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)


if __name__ == "__main__":
    unittest.main()
