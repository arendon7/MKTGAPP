import copy
import unittest
from pathlib import Path

from binario_marketing import service_post_w99_campaign_attention_actionability_app as parent
from binario_marketing.service_post_w99_campaign_execution_owner_drift_guard_app import (
    AppRuntime,
    annotate_campaign_execution_owner_drift,
)

ROOT = Path(__file__).resolve().parents[1]


def drift_row(
    source_code: str,
    owner_view: str,
    *,
    action_id: str = "action-1",
    state: str = "NO_TARGET",
    target_id=None,
    candidate_count=0,
    candidates=None,
    campaign_id: str = "campaign-1",
):
    return {
        "id": action_id,
        "rank": 42,
        "urgency": "HIGH",
        "source": "CAMPAIGN",
        "kind": source_code.lower(),
        "title": "Action",
        "detail": "Detail",
        "action": {
            "label": "Abrir owner",
            "view": owner_view,
            "campaign_id": campaign_id,
        },
        "blocking": False,
        "owner_resolution": {
            "state": state,
            "source_code": source_code,
            "owner_view": owner_view,
            "target_kind": None,
            "target_id": target_id,
            "candidate_count": candidate_count,
            "candidates": [] if candidates is None else candidates,
            "reason": "El objeto esperado ya no está presente.",
        },
    }


def payload(row):
    passive = {
        "id": "passive-calendar",
        "source": "CAMPAIGN",
        "kind": "calendar",
        "actionability": {"state": "NON_REQUIRED_CAMPAIGN_ATTENTION"},
    }
    return {
        "schema": "binario.marketing.action-center.v1",
        "queue": [copy.deepcopy(row)],
        "next_action": copy.deepcopy(row),
        "focus": {"now": [copy.deepcopy(row)], "next": [], "later": []},
        "observations": [copy.deepcopy(passive)],
        "contracts": {
            "setup_shadow_deduplication_fail_closed": True,
            "campaign_passive_attention_uses_exact_source_lineage": True,
            "passive_campaign_states_excluded_from_today": True,
        },
    }


class OwnerDriftProjectionTests(unittest.TestCase):
    def test_known_no_target_shapes_are_observed(self):
        rules = {
            "FIX_PUBLICATION": ("calendar", "PUBLICATION"),
            "SCHEDULE_OR_PUBLISH": ("calendar", "PUBLICATION"),
            "REVIEW_PAID": ("pauta", "PAID_DRAFT"),
            "FINISH_CREATIVE": ("content", "MEDIA"),
            "PREPARE_DISTRIBUTION": ("content", "MEDIA"),
        }
        for source_code, (owner_view, expected) in rules.items():
            with self.subTest(source_code=source_code):
                row = drift_row(source_code, owner_view)
                result = annotate_campaign_execution_owner_drift(payload(row))
                observed = result["queue"][0]["owner_drift"]
                self.assertEqual(observed["state"], "CANONICAL_TARGET_NOT_PRESENT")
                self.assertEqual(observed["source_code"], source_code)
                self.assertEqual(observed["owner_view"], owner_view)
                self.assertEqual(observed["expected_target_kind"], expected)
                self.assertEqual(observed["campaign_id"], "campaign-1")
                self.assertFalse(observed["target_selected"])
                self.assertFalse(observed["replacement_inferred"])
                self.assertEqual(observed["recovery"]["mode"], "OPEN_OWNER_AND_REVIEW_CURRENT_STATE")
                self.assertTrue(observed["recovery"]["requires_human_review"])
                self.assertEqual(result["owner_drift_observations"][0]["action_id"], "action-1")

    def test_annotation_preserves_priority_action_resolution_and_parent_observations(self):
        row = drift_row("REVIEW_PAID", "pauta")
        source = payload(row)
        original = copy.deepcopy(source)
        result = annotate_campaign_execution_owner_drift(source)
        current = result["queue"][0]
        self.assertEqual(current["rank"], original["queue"][0]["rank"])
        self.assertEqual(current["urgency"], original["queue"][0]["urgency"])
        self.assertEqual(current["blocking"], original["queue"][0]["blocking"])
        self.assertEqual(current["action"], original["queue"][0]["action"])
        self.assertEqual(current["owner_resolution"], original["queue"][0]["owner_resolution"])
        self.assertEqual(result["observations"], original["observations"])
        self.assertTrue(result["contracts"]["campaign_passive_attention_uses_exact_source_lineage"])
        self.assertTrue(result["contracts"]["passive_campaign_states_excluded_from_today"])

    def test_queue_next_action_and_focus_share_same_observation(self):
        row = drift_row("FIX_PUBLICATION", "calendar")
        result = annotate_campaign_execution_owner_drift(payload(row))
        queue_drift = result["queue"][0]["owner_drift"]
        self.assertEqual(result["next_action"]["owner_drift"], queue_drift)
        self.assertEqual(result["focus"]["now"][0]["owner_drift"], queue_drift)

    def test_source_payload_is_not_mutated(self):
        source = payload(drift_row("FINISH_CREATIVE", "content"))
        snapshot = copy.deepcopy(source)
        annotate_campaign_execution_owner_drift(source)
        self.assertEqual(source, snapshot)

    def test_malformed_or_non_drift_shapes_fail_closed(self):
        cases = [
            drift_row("UNKNOWN", "calendar"),
            drift_row("FIX_PUBLICATION", "pauta"),
            drift_row("FIX_PUBLICATION", "calendar", target_id="pub-1"),
            drift_row("FIX_PUBLICATION", "calendar", candidate_count=1),
            drift_row("FIX_PUBLICATION", "calendar", candidate_count=0.5),
            drift_row("FIX_PUBLICATION", "calendar", candidate_count=True),
            drift_row("FIX_PUBLICATION", "calendar", candidates=[{"id": "pub-1"}]),
            drift_row("FIX_PUBLICATION", "calendar", campaign_id=""),
            drift_row("FIX_PUBLICATION", "calendar", action_id=""),
            drift_row("FIX_PUBLICATION", "calendar", state="AMBIGUOUS_TARGET"),
            drift_row("FIX_PUBLICATION", "calendar", state="EXACT_TARGET"),
            drift_row("CALENDAR", "calendar", state="OWNER_ONLY"),
        ]
        for index, row in enumerate(cases):
            with self.subTest(index=index):
                result = annotate_campaign_execution_owner_drift(payload(row))
                self.assertNotIn("owner_drift", result["queue"][0])
                self.assertEqual(result["owner_drift_observations"], [])

    def test_contracts_are_additive_and_fail_closed(self):
        result = annotate_campaign_execution_owner_drift(payload(drift_row("REVIEW_PAID", "pauta")))
        self.assertTrue(result["contracts"]["setup_shadow_deduplication_fail_closed"])
        self.assertTrue(result["contracts"]["campaign_passive_attention_uses_exact_source_lineage"])
        self.assertTrue(result["contracts"]["no_target_is_observable"])
        self.assertTrue(result["contracts"]["no_target_preserves_w64_priority"])
        self.assertTrue(result["contracts"]["no_target_does_not_select_replacement"])
        self.assertTrue(result["contracts"]["no_target_owner_recovery_is_navigation_only"])
        self.assertTrue(result["contracts"]["malformed_no_target_fails_closed"])
        self.assertTrue(result["contracts"]["owner_drift_human_review_required"])
        self.assertTrue(result["contracts"]["owner_drift_runs_after_campaign_actionability_filters"])


class OwnerDriftCompositionTests(unittest.TestCase):
    def test_terminal_inherits_campaign_attention_actionability(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_browser_guard_is_zero_transport_and_non_persistent(self):
        source = (ROOT / "web" / "campaign-execution-owner-drift-guard.js").read_text(encoding="utf-8")
        self.assertIn("OWNER_STATE_DRIFT", source)
        self.assertIn("TARGET_NOT_EXACT", source)
        self.assertIn("actionCenterOpen", source)
        self.assertIn("controlHandoffResolve", source)
        self.assertIn("controlHandoffMessage", source)
        self.assertIn("no se eligió un reemplazo", source)
        for forbidden in (
            "fetch(", "XMLHttpRequest", "sendBeacon", "localStorage", "sessionStorage",
            "setInterval", ".click()", "dispatchEvent(",
        ):
            self.assertNotIn(forbidden, source)

    def test_service_bootstraps_after_attention_actionability_and_is_get_only(self):
        source = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_execution_owner_drift_guard_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("service_post_w99_campaign_attention_actionability_app", source)
        self.assertIn('path == "/campaign-attention-actionability.js"', source)
        self.assertIn("script.src='/campaign-execution-owner-drift-guard.js'", source)
        self.assertIn("data-post-w99-campaign-execution-owner-drift-guard", source)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
