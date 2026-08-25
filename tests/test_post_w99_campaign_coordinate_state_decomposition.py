import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from binario_marketing import service_post_w99_campaign_creative_creation_intent_handoff_app as parent
from binario_marketing.service_post_w99_campaign_coordinate_state_decomposition_app import (
    AppRuntime,
    _coordinate_state_from_card,
)

ROOT = Path(__file__).resolve().parents[1]


def coordinate_card(*, publication_counts=None, publication_total=None, paid_counts=None, paid_total=None, channels=None, planned_only=None):
    publication_counts = dict(publication_counts or {})
    paid_counts = dict(paid_counts or {})
    if publication_total is None:
        publication_total = sum(publication_counts.values())
    if paid_total is None:
        paid_total = sum(paid_counts.values())
    return {
        "campaign": {
            "id": "campaign_1234567890abcdef12345678",
            "name": "Coordinate campaign",
            "status": "ACTIVE",
            "channels": list(channels or ["facebook_page"]),
        },
        "creative": {"total": 1, "ready": 1, "counts": {"READY": 1}, "items": []},
        "organic": {
            "selected": bool(set(channels or ["facebook_page"]) & {"facebook_page", "instagram"}),
            "counts": publication_counts,
            "publications": publication_total,
            "failed": publication_counts.get("FAILED", 0),
        },
        "paid": {
            "plans": paid_total,
            "counts": paid_counts,
            "remote_paused": paid_counts.get("REMOTE_PAUSED", 0),
        },
        "planned_only_channels": list(planned_only or []),
        "next_action": {"code": "COORDINATE", "label": "Coordinar distribución", "view": "content"},
        "priority": 4,
        "requires_action": False,
    }


class PostW99CampaignCoordinateStateDecompositionTests(unittest.TestCase):
    def test_publication_in_flight_is_observed_without_inventing_control(self):
        payload = _coordinate_state_from_card(coordinate_card(publication_counts={"PUBLISHING": 1}))
        self.assertEqual(payload["schema"], "binario.marketing.campaign-coordinate-state.v1")
        self.assertEqual(payload["state"], "PUBLICATION_IN_FLIGHT")
        self.assertEqual(payload["route_scope"], "ORGANIC")
        self.assertEqual(payload["invariant_violations"], [])
        self.assertEqual(payload["unknown_statuses"], {"publications": [], "paid": []})
        self.assertTrue(payload["contracts"]["w64_remains_next_action_authority"])
        self.assertTrue(payload["contracts"]["diagnostic_does_not_authorize_control_handoff"])

    def test_publication_in_flight_can_coexist_with_cancelled_paid_route(self):
        payload = _coordinate_state_from_card(coordinate_card(
            publication_counts={"PUBLISHING": 1},
            paid_counts={"CANCELLED": 1},
        ))
        self.assertEqual(payload["state"], "PUBLICATION_IN_FLIGHT")
        self.assertEqual(payload["route_scope"], "MIXED")

    def test_only_cancelled_organic_distribution_is_distinct(self):
        payload = _coordinate_state_from_card(coordinate_card(publication_counts={"CANCELLED": 2}))
        self.assertEqual(payload["state"], "ONLY_CANCELLED_DISTRIBUTION_REMAINS")
        self.assertEqual(payload["route_scope"], "ORGANIC")

    def test_only_cancelled_paid_distribution_is_distinct(self):
        payload = _coordinate_state_from_card(coordinate_card(
            publication_counts={},
            paid_counts={"CANCELLED": 1},
            channels=["paid_media"],
            planned_only=["paid_media"],
        ))
        self.assertEqual(payload["state"], "ONLY_CANCELLED_DISTRIBUTION_REMAINS")
        self.assertEqual(payload["route_scope"], "PAID")
        self.assertEqual(payload["invariant_violations"], [])

    def test_cancelled_organic_and_paid_routes_report_mixed_scope(self):
        payload = _coordinate_state_from_card(coordinate_card(
            publication_counts={"CANCELLED": 1},
            paid_counts={"CANCELLED": 1},
        ))
        self.assertEqual(payload["state"], "ONLY_CANCELLED_DISTRIBUTION_REMAINS")
        self.assertEqual(payload["route_scope"], "MIXED")

    def test_unknown_lifecycle_status_fails_closed(self):
        payload = _coordinate_state_from_card(coordinate_card(publication_counts={"FUTURE_REMOTE_WAIT": 1}))
        self.assertEqual(payload["state"], "UNCLASSIFIED_COORDINATION_STATE")
        self.assertEqual(payload["unknown_statuses"]["publications"], ["FUTURE_REMOTE_WAIT"])
        self.assertEqual(payload["invariant_violations"], [])

    def test_an_earlier_w64_predicate_beats_leftover_classification(self):
        payload = _coordinate_state_from_card(coordinate_card(publication_counts={"DRAFT": 1}))
        self.assertEqual(payload["state"], "COORDINATE_INVARIANT_DRIFT")
        self.assertIn("DRAFT_PUBLICATION_SHOULD_SCHEDULE_OR_PUBLISH", payload["invariant_violations"])

    def test_histogram_mismatch_is_invariant_drift(self):
        payload = _coordinate_state_from_card(coordinate_card(
            publication_counts={"CANCELLED": 1},
            publication_total=2,
        ))
        self.assertEqual(payload["state"], "COORDINATE_INVARIANT_DRIFT")
        self.assertIn("PUBLICATION_COUNT_HISTOGRAM_MISMATCH", payload["invariant_violations"])

    def test_non_coordinate_cards_are_rejected_not_relabelled(self):
        card = coordinate_card(publication_counts={"PUBLISHING": 1})
        card["next_action"] = {"code": "CALENDAR", "view": "calendar"}
        with self.assertRaisesRegex(ValueError, "not COORDINATE"):
            _coordinate_state_from_card(card)

    def test_action_center_annotation_preserves_action_priority_and_order(self):
        coordinate = {
            "id": "campaign:coordinate:one",
            "kind": "coordinate",
            "rank": 74,
            "urgency": "LOW",
            "blocking": False,
            "due_at": None,
            "reason": {"code": "CAMPAIGN_COORDINATE", "explanation": "W64 fallback"},
            "action": {
                "label": "Coordinar distribución",
                "view": "content",
                "campaign_id": "campaign_1234567890abcdef12345678",
                "media_id": None,
            },
        }
        other = {
            "id": "operations:first",
            "kind": "crm_today",
            "rank": 35,
            "urgency": "HIGH",
            "action": {"label": "Abrir", "view": "crm"},
        }
        original_coordinate = deepcopy(coordinate)
        parent_payload = {
            "schema": "binario.marketing.action-center.v1",
            "queue": [other, coordinate],
            "next_action": other,
            "focus": {"now": [other], "next": [], "later": [coordinate]},
            "contracts": {"existing": True},
        }
        diagnostic = _coordinate_state_from_card(coordinate_card(publication_counts={"PUBLISHING": 1}))
        runtime = AppRuntime.__new__(AppRuntime)
        with patch.object(parent.AppRuntime, "action_center", return_value=deepcopy(parent_payload)), patch.object(
            AppRuntime, "campaign_coordinate_state", return_value=diagnostic
        ):
            result = runtime.action_center("company-1")
        self.assertEqual([row["id"] for row in result["queue"]], ["operations:first", "campaign:coordinate:one"])
        annotated = result["queue"][1]
        self.assertEqual(annotated["action"], original_coordinate["action"])
        self.assertEqual(annotated["rank"], original_coordinate["rank"])
        self.assertEqual(annotated["urgency"], original_coordinate["urgency"])
        self.assertEqual(annotated["blocking"], original_coordinate["blocking"])
        self.assertEqual(annotated["reason"], original_coordinate["reason"])
        self.assertEqual(annotated["coordinate_state"]["state"], "PUBLICATION_IN_FLIGHT")
        self.assertEqual(result["focus"]["later"][0]["coordinate_state"]["state"], "PUBLICATION_IN_FLIGHT")
        self.assertNotIn("coordinate_state", result["next_action"])

    def test_service_is_get_only_and_contains_no_provider_or_business_mutation(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_coordinate_state_decomposition_app.py").read_text(encoding="utf-8")
        self.assertIn('parts[5] == "coordinate-state"', source)
        self.assertIn("def do_GET", source)
        for forbidden in (
            "def do_POST",
            "def do_PATCH",
            "def do_PUT",
            "def do_DELETE",
            "MetaGraphClient",
            "create_company_publication",
            "create_company_paid_media",
            "wave49SaveCreative",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"provider_read_performed": False', source)
        self.assertIn('"business_mutation_performed": False', source)

    def test_docs_preserve_diagnostic_only_scope_and_w99_boundary(self):
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_COORDINATE_STATE_DECOMPOSITION.md").read_text(encoding="utf-8")
        for required in (
            "PUBLICATION_IN_FLIGHT",
            "ONLY_CANCELLED_DISTRIBUTION_REMAINS",
            "COORDINATE_INVARIANT_DRIFT",
            "UNCLASSIFIED_COORDINATION_STATE",
            "W64 remains the next-action authority",
            "does not authorize Control Handoff",
            "main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",
        ):
            self.assertIn(required, doc)


if __name__ == "__main__":
    unittest.main()
