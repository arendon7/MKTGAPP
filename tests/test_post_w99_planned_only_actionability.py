import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_campaign_execution_owner_cardinality_hardening_app as parent
from binario_marketing.service_post_w99_planned_only_actionability_app import (
    AppRuntime,
    create_server,
    preserve_planned_only_actionability,
)

ROOT = Path(__file__).resolve().parents[1]


def action_row(action_id: str, kind: str, rank: int, urgency: str, source: str = "CAMPAIGN") -> dict:
    return {
        "id": action_id,
        "rank": rank,
        "urgency": urgency,
        "source": source,
        "kind": kind,
        "title": f"{kind} · Campaign",
        "detail": f"detail {action_id}",
        "action": {"label": "Abrir", "view": "campaigns", "campaign_id": "campaign-1"},
        "reason": {"code": f"{source}_{kind}".upper(), "explanation": "canonical reason"},
        "due_at": None,
        "blocking": False,
        "requires_human_action": True,
        "read_only_recommendation": True,
    }


def action_center_payload(queue: list[dict]) -> dict:
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": "company-1", "name": "Company"},
        "next_action": queue[0] if queue else None,
        "summary": {
            "queue_total": len(queue),
            "blocking": sum(1 for row in queue if row.get("blocking")),
            "critical": sum(1 for row in queue if row["urgency"] == "CRITICAL"),
            "high": sum(1 for row in queue if row["urgency"] == "HIGH"),
            "medium": sum(1 for row in queue if row["urgency"] == "MEDIUM"),
            "low": sum(1 for row in queue if row["urgency"] == "LOW"),
            "by_source": {"OPERATIONS": 0, "COMMERCIAL": 0, "CAMPAIGN": len(queue), "SETUP": 0},
            "active_campaigns": 2,
            "campaign_actions": len(queue),
        },
        "focus": {"now": [], "next": [], "later": list(queue)},
        "queue": list(queue),
        "contracts": {"human_execution_required": True},
        "safety": {"read_only_projection": True, "business_mutation_performed": False},
    }


class PlannedOnlyProjectionTests(unittest.TestCase):
    def test_planned_only_becomes_observation_without_reordering_actions(self):
        planned = action_row("planned", "planned_only", 90, "LOW")
        high = action_row("high", "capture_results", 44, "HIGH")
        medium = action_row("medium", "record_decision", 48, "MEDIUM")
        source = action_center_payload([planned, high, medium])

        payload = preserve_planned_only_actionability(source)

        self.assertEqual([row["id"] for row in payload["queue"]], ["high", "medium"])
        self.assertEqual(payload["next_action"]["id"], "high")
        self.assertEqual([row["id"] for row in payload["focus"]["now"]], ["high"])
        self.assertEqual([row["id"] for row in payload["focus"]["next"]], ["medium"])
        self.assertEqual(payload["focus"]["later"], [])
        self.assertEqual(payload["summary"]["queue_total"], 2)
        self.assertEqual(payload["summary"]["campaign_actions"], 2)
        self.assertEqual(payload["summary"]["campaign_observations"], 1)

        observation = payload["observations"][0]
        self.assertEqual(observation["id"], "planned")
        self.assertFalse(observation["requires_human_action"])
        self.assertFalse(observation["blocking"])
        self.assertEqual(observation["actionability"]["state"], "NON_ACTIONABLE")
        self.assertFalse(observation["actionability"]["today_eligible"])
        self.assertTrue(observation["actionability"]["owner_navigation_allowed"])

        self.assertEqual([row["id"] for row in source["queue"]], ["planned", "high", "medium"])
        self.assertTrue(source["queue"][0]["requires_human_action"])

    def test_planned_only_only_queue_has_no_fake_next_action(self):
        payload = preserve_planned_only_actionability(
            action_center_payload([action_row("planned", "planned_only", 90, "LOW")])
        )
        self.assertEqual(payload["queue"], [])
        self.assertIsNone(payload["next_action"])
        self.assertEqual(payload["focus"], {"now": [], "next": [], "later": []})
        self.assertEqual(payload["summary"]["queue_total"], 0)
        self.assertEqual(payload["summary"]["campaign_actions"], 0)
        self.assertEqual(payload["summary"]["campaign_observations"], 1)
        self.assertTrue(payload["contracts"]["planned_only_excluded_from_today"])
        self.assertTrue(payload["contracts"]["no_provider_capability_invented"])

    def test_non_planned_campaign_actions_are_not_generalized_away(self):
        queue = [
            action_row("calendar", "calendar", 73, "LOW"),
            action_row("review", "review_results", 72, "LOW"),
            action_row("coordinate", "coordinate", 74, "LOW"),
            action_row("ai", "optional_ai", 88, "LOW"),
        ]
        payload = preserve_planned_only_actionability(action_center_payload(queue))
        self.assertEqual([row["id"] for row in payload["queue"]], ["calendar", "review", "coordinate", "ai"])
        self.assertEqual(payload["observations"], [])
        self.assertEqual(payload["summary"]["campaign_actions"], 4)

    def test_projection_is_idempotent_and_preserves_existing_metadata(self):
        row = action_row("planned", "planned_only", 90, "LOW")
        row["owner_resolution"] = {"state": "EXACT_TARGET", "target_kind": "CAMPAIGN", "target_id": "campaign-1"}
        once = preserve_planned_only_actionability(action_center_payload([row]))
        twice = preserve_planned_only_actionability(once)
        self.assertEqual(len(twice["observations"]), 1)
        self.assertEqual(
            twice["observations"][0]["owner_resolution"],
            {"state": "EXACT_TARGET", "target_kind": "CAMPAIGN", "target_id": "campaign-1"},
        )


class PlannedOnlyRuntimeTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()

    def test_terminal_inherits_cardinality_hardening(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_email_only_campaign_stays_visible_but_never_enters_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Planned Only Co"})
                campaign = runtime.campaigns.create(company["id"], {
                    "name": "Email plan", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["email"]
                })
                raw = b"\x89PNG\r\n\x1a\nplanned-only"
                media = runtime.upload_company_media(
                    company["id"], "ready.png", "image", io.BytesIO(raw), len(raw)
                )
                runtime.upsert_company_creative(company["id"], media["id"], {
                    "title": "Ready", "stage": "READY", "purpose": "LEADS",
                    "campaign_id": campaign.id, "channels": ["email"],
                })

                execution = runtime.campaign_execution_workspace(company["id"])
                execution_row = next(row for row in execution["campaigns"] if row["campaign"]["id"] == campaign.id)
                self.assertEqual(execution_row["next_action"]["code"], "PLANNED_ONLY")
                self.assertFalse(execution_row["requires_action"])
                self.assertEqual(execution_row["planned_only_channels"], ["email"])

                action_center = runtime.action_center(company["id"])
                self.assertNotIn("planned_only", {row["kind"] for row in action_center["queue"]})
                observation = next(
                    row for row in action_center["observations"]
                    if row.get("kind") == "planned_only" and row.get("action", {}).get("campaign_id") == campaign.id
                )
                self.assertFalse(observation["requires_human_action"])
                self.assertEqual(observation["actionability"]["state"], "NON_ACTIONABLE")
                self.assertEqual(observation["owner_resolution"]["state"], "EXACT_TARGET")

                today = runtime.today_execution(company["id"])
                self.assertNotIn("planned_only", {row["kind"] for row in today["plan"]})
                self.assertTrue(action_center["contracts"]["planned_only_excluded_from_today"])
            finally:
                self._shutdown(runtime)

    def test_http_bootstrap_and_projection_are_get_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company = runtime.create_company({"name": "HTTP Planned Only"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(
                    root + "/campaign-execution-owner-cardinality-hardening.js", timeout=5
                ).read().decode("utf-8")
                adapter = urlopen(root + "/planned-only-actionability.js", timeout=5).read().decode("utf-8")
                payload = json.loads(urlopen(
                    root + f"/api/companies/{company['id']}/action-center", timeout=5
                ).read().decode("utf-8"))
                self.assertIn("/planned-only-actionability.js", parent_js)
                self.assertIn("data-post-w99-planned-only-actionability", parent_js)
                self.assertIn("OBSERVACIONES · NO EJECUTABLES", adapter)
                self.assertEqual(payload["schema"], "binario.marketing.action-center.v1")
                self.assertIn("observations", payload)
                self.assertTrue(payload["contracts"]["planned_only_is_observational"])
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close(); self._shutdown(runtime)

    def test_service_browser_and_docs_preserve_safety_and_frozen_boundary(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_planned_only_actionability_app.py").read_text(encoding="utf-8")
        browser = (ROOT / "web" / "planned-only-actionability.js").read_text(encoding="utf-8")
        doc = (ROOT / "docs" / "POST_W99_PLANNED_ONLY_ACTIONABILITY.md").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_campaign_execution_owner_cardinality_hardening_app", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)
        for forbidden in (
            "opsApi(", "fetch(", ".click(", "dispatchEvent(", "setInterval(", "sendBeacon(",
            "method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, browser)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No constituye W100", doc)
        self.assertIn("physical uat", doc.lower())


if __name__ == "__main__":
    unittest.main()
