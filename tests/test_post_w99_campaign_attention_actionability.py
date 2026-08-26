import copy
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_campaign_coordinate_actionability_app as parent
from binario_marketing.service_post_w99_campaign_attention_actionability_app import (
    AppRuntime,
    _campaign_passive_lineage,
    create_server,
    preserve_campaign_attention_actionability,
)


ROOT = Path(__file__).resolve().parents[1]


def _row(action_id: str, *, kind: str, source: str = "CAMPAIGN", urgency: str = "LOW") -> dict:
    return {
        "id": action_id,
        "rank": 70,
        "urgency": urgency,
        "source": source,
        "kind": kind,
        "title": f"{kind} · Campaign",
        "detail": f"detail {action_id}",
        "action": {
            "label": kind,
            "view": "analytics" if kind != "calendar" else "calendar",
            "campaign_id": "campaign-1",
            "media_id": None,
        },
        "reason": {"code": f"CAMPAIGN_{kind}".upper(), "explanation": "canonical"},
        "due_at": None,
        "blocking": False,
        "requires_human_action": True,
        "read_only_recommendation": True,
    }


def _payload(queue: list[dict], observations: list[dict] | None = None) -> dict:
    observations = list(observations or [])
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": "company-1", "name": "Company"},
        "next_action": queue[0] if queue else None,
        "summary": {
            "queue_total": len(queue),
            "blocking": sum(1 for row in queue if row.get("blocking")),
            "critical": sum(1 for row in queue if row.get("urgency") == "CRITICAL"),
            "high": sum(1 for row in queue if row.get("urgency") == "HIGH"),
            "medium": sum(1 for row in queue if row.get("urgency") == "MEDIUM"),
            "low": sum(1 for row in queue if row.get("urgency") == "LOW"),
            "by_source": {
                "OPERATIONS": 0,
                "COMMERCIAL": 0,
                "CAMPAIGN": sum(1 for row in queue if row.get("source") == "CAMPAIGN"),
                "SETUP": 0,
            },
            "campaign_actions": sum(1 for row in queue if row.get("source") == "CAMPAIGN"),
            "observations_total": len(observations),
            "campaign_observations": 1 if observations else 0,
            "coordinate_observations": 1 if observations else 0,
            "coordinate_exact_recovery_actions": 2,
        },
        "focus": {
            "now": [row for row in queue if row.get("urgency") in {"CRITICAL", "HIGH"}][:8],
            "next": [row for row in queue if row.get("urgency") == "MEDIUM"][:8],
            "later": [row for row in queue if row.get("urgency") == "LOW"][:8],
        },
        "queue": list(queue),
        "observations": observations,
        "contracts": {"coordinate_observations_excluded_from_today": True},
        "safety": {"read_only_projection": True},
    }


def _intel_card(code: str, *, requires_attention: object = False, execution_requires_action: object = False) -> dict:
    card = {
        "campaign": {"id": "campaign-1", "name": "Campaign", "status": "ACTIVE"},
        "next_action": {"code": code, "label": code, "view": "analytics"},
        "requires_attention": requires_attention,
        "execution": {
            "requires_action": execution_requires_action,
            "next_action": {"code": code, "label": code, "view": "calendar"},
        },
    }
    return card


def _intelligence(*cards: dict) -> dict:
    return {"schema": "binario.marketing.results-intelligence.v1", "campaigns": list(cards)}


class CampaignAttentionProjectionTests(unittest.TestCase):
    def test_calendar_requires_both_w65_and_w64_false(self):
        row = _row("calendar", kind="calendar")
        lineage = _campaign_passive_lineage(row, _intelligence(_intel_card("CALENDAR")))
        self.assertEqual(lineage["source"], "W65_FALLBACK_TO_W64")
        result = preserve_campaign_attention_actionability(_payload([row]), _intelligence(_intel_card("CALENDAR")))
        self.assertEqual(result["queue"], [])
        observation = result["observations"][0]
        self.assertFalse(observation["requires_human_action"])
        self.assertFalse(observation["actionability"]["today_eligible"])
        self.assertEqual(observation["actionability"]["lineage"]["w64_requires_action"], False)

    def test_review_results_is_observation_only_with_exact_w65_false(self):
        row = _row("review", kind="review_results")
        result = preserve_campaign_attention_actionability(
            _payload([row]), _intelligence(_intel_card("REVIEW_RESULTS"))
        )
        self.assertEqual(result["queue"], [])
        self.assertEqual(result["summary"]["campaign_attention_observations"], 1)
        self.assertEqual(
            result["observations"][0]["actionability"]["lineage"]["source"],
            "W65_RESULTS_INTELLIGENCE",
        )

    def test_optional_ai_is_visible_but_not_today_work(self):
        row = _row("ai", kind="optional_ai")
        result = preserve_campaign_attention_actionability(
            _payload([row]), _intelligence(_intel_card("OPTIONAL_AI"))
        )
        self.assertEqual(result["queue"], [])
        self.assertEqual(result["next_action"], None)
        self.assertEqual(result["focus"], {"now": [], "next": [], "later": []})
        self.assertTrue(result["contracts"]["passive_campaign_states_excluded_from_today"])

    def test_non_passive_fallback_action_is_never_generalized_away(self):
        row = _row("creative", kind="create_creative", urgency="MEDIUM")
        result = preserve_campaign_attention_actionability(
            _payload([row]), _intelligence(_intel_card("CREATE_CREATIVE", requires_attention=False, execution_requires_action=True))
        )
        self.assertEqual([item["id"] for item in result["queue"]], ["creative"])
        self.assertEqual(result["observations"], [])

    def test_calendar_with_w64_true_stays_in_queue(self):
        row = _row("calendar", kind="calendar")
        card = _intel_card("CALENDAR", requires_attention=False, execution_requires_action=True)
        self.assertIsNone(_campaign_passive_lineage(row, _intelligence(card)))
        result = preserve_campaign_attention_actionability(_payload([row]), _intelligence(card))
        self.assertEqual([item["id"] for item in result["queue"]], ["calendar"])

    def test_missing_duplicate_mismatch_or_true_attention_preserves_existing_work(self):
        variants = [
            _intelligence(),
            _intelligence(_intel_card("REVIEW_RESULTS"), _intel_card("REVIEW_RESULTS")),
            _intelligence(_intel_card("OPTIONAL_AI")),
            _intelligence(_intel_card("REVIEW_RESULTS", requires_attention=True)),
            _intelligence(_intel_card("REVIEW_RESULTS", requires_attention=None)),
        ]
        for intelligence in variants:
            with self.subTest(intelligence=intelligence):
                row = _row("review", kind="review_results")
                result = preserve_campaign_attention_actionability(_payload([row]), intelligence)
                self.assertEqual([item["id"] for item in result["queue"]], ["review"])
                self.assertEqual(result["observations"], [])

    def test_non_campaign_row_with_same_kind_is_preserved(self):
        row = _row("operation-calendar", kind="calendar", source="OPERATIONS")
        result = preserve_campaign_attention_actionability(
            _payload([row]), _intelligence(_intel_card("CALENDAR"))
        )
        self.assertEqual([item["id"] for item in result["queue"]], ["operation-calendar"])

    def test_projection_is_idempotent_and_preserves_previous_observation_metrics(self):
        previous = _row("coordinate", kind="coordinate")
        previous["requires_human_action"] = False
        previous["actionability"] = {"state": "NON_ACTIONABLE_COORDINATE", "today_eligible": False}
        source = _payload([_row("review", kind="review_results")], observations=[previous])
        once = preserve_campaign_attention_actionability(source, _intelligence(_intel_card("REVIEW_RESULTS")))
        twice = preserve_campaign_attention_actionability(once, _intelligence(_intel_card("REVIEW_RESULTS")))
        self.assertEqual([row["id"] for row in twice["observations"]], ["coordinate", "review"])
        self.assertEqual(twice["summary"]["campaign_observations"], 1)
        self.assertEqual(twice["summary"]["coordinate_observations"], 1)
        self.assertEqual(twice["summary"]["coordinate_exact_recovery_actions"], 2)
        self.assertEqual(twice["summary"]["campaign_attention_observations"], 1)

    def test_next_focus_summary_and_source_input_are_recomputed_without_mutation(self):
        high = _row("high", kind="record_decision", urgency="HIGH")
        passive = _row("passive", kind="review_results", urgency="LOW")
        medium = _row("medium", kind="review_paid", urgency="MEDIUM")
        source = _payload([high, passive, medium])
        original = copy.deepcopy(source)
        result = preserve_campaign_attention_actionability(
            source, _intelligence(_intel_card("REVIEW_RESULTS"))
        )
        self.assertEqual(source, original)
        self.assertEqual([row["id"] for row in result["queue"]], ["high", "medium"])
        self.assertEqual(result["next_action"]["id"], "high")
        self.assertEqual([row["id"] for row in result["focus"]["now"]], ["high"])
        self.assertEqual([row["id"] for row in result["focus"]["next"]], ["medium"])
        self.assertEqual(result["focus"]["later"], [])
        self.assertEqual(result["summary"]["queue_total"], 2)
        self.assertEqual(result["summary"]["campaign_actions"], 2)
        self.assertTrue(result["contracts"]["passive_lineage_mismatch_preserves_existing_action"])


class CampaignAttentionIntegrationTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_coordinate_actionability_parent(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_http_bootstrap_appends_attention_after_coordinate_actionability(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Campaign Attention HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(root + "/campaign-coordinate-actionability.js", timeout=5).read().decode("utf-8")
                adapter = urlopen(root + "/campaign-attention-actionability.js", timeout=5).read().decode("utf-8")
                self.assertIn("/campaign-attention-actionability.js", parent_js)
                self.assertIn("data-post-w99-campaign-attention-actionability", parent_js)
                self.assertIn("CAMPAÑAS · CONTEXTO NO REQUERIDO", adapter)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_service_browser_docs_and_canonical_sources_preserve_boundary(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_attention_actionability_app.py").read_text(encoding="utf-8")
        browser = (ROOT / "web" / "campaign-attention-actionability.js").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "POST_W99_CAMPAIGN_ATTENTION_ACTIONABILITY.md").read_text(encoding="utf-8")
        w64 = (ROOT / "src" / "binario_marketing" / "service_wave64_app.py").read_text(encoding="utf-8")
        w65 = (ROOT / "src" / "binario_marketing" / "service_wave65_app.py").read_text(encoding="utf-8")

        self.assertIn('"code": "CALENDAR"', w64)
        self.assertIn("requires_action = False", w64)
        self.assertIn('"code": "OPTIONAL_AI"', w65)
        self.assertIn('"code": "REVIEW_RESULTS"', w65)
        self.assertIn("requires_attention = False", w65)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)
        for forbidden in ("fetch(", "XMLHttpRequest", "dispatchEvent", "requestSubmit", ".click(", "setInterval"):
            self.assertNotIn(forbidden, browser)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No es W100", docs)
        self.assertIn("lineage", docs)


if __name__ == "__main__":
    unittest.main()
