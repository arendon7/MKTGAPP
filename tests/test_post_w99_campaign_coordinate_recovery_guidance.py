import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from binario_marketing import service_post_w99_campaign_coordinate_state_decomposition_app as parent
from binario_marketing.service_post_w99_campaign_coordinate_recovery_guidance_app import (
    AppRuntime,
    _coordinate_recovery_from_observed,
    _rewrite_coordinate_navigation,
)

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_ID = "campaign_1234567890abcdef12345678"
PUB1 = "1" * 32
PUB2 = "2" * 32
PAID1 = "3" * 32
MEDIA1 = "media_1234567890abcdef12345678"
MEDIA2 = "media_abcdef1234567890abcdef12"


def diagnostic(state, *, publication_total=0, paid_total=0, scope="NONE"):
    return {
        "schema": "binario.marketing.campaign-coordinate-state.v1",
        "campaign": {"id": CAMPAIGN_ID, "name": "Coordinate", "status": "ACTIVE", "channels": ["facebook_page"]},
        "state": state,
        "route_scope": scope,
        "observed": {
            "publications": {"total": publication_total, "counts": {}},
            "paid": {"total": paid_total, "counts": {}},
        },
    }


def creative(media_id=MEDIA1, *, kind="image", stage="READY"):
    return {
        "media": {"id": media_id, "kind": kind, "original_name": f"{media_id}.jpg"},
        "creative": {"title": "Creative", "campaign_id": CAMPAIGN_ID},
        "effective_stage": stage,
    }


def coordinate_row():
    return {
        "id": "campaign:coordinate:one",
        "kind": "coordinate",
        "rank": 74,
        "urgency": "LOW",
        "blocking": False,
        "reason": {"code": "CAMPAIGN_COORDINATE", "explanation": "W64 fallback"},
        "action": {
            "label": "Coordinar distribución",
            "view": "content",
            "campaign_id": CAMPAIGN_ID,
            "media_id": None,
            "entity_id": None,
        },
    }


class PostW99CampaignCoordinateRecoveryGuidanceTests(unittest.TestCase):
    def test_unique_publishing_publication_refines_to_exact_observation_owner(self):
        payload = _coordinate_recovery_from_observed(
            diagnostic("PUBLICATION_IN_FLIGHT", publication_total=1, scope="ORGANIC"),
            [{"id": PUB1, "status": "PUBLISHING", "channel": "facebook_page", "scheduled_for": None}],
            [], [], {}, {},
        )
        self.assertEqual(payload["schema"], "binario.marketing.campaign-coordinate-recovery-guidance.v1")
        self.assertEqual(payload["state"], "EXACT_EXISTING_OWNER")
        self.assertEqual(payload["intent"], "OBSERVE_PUBLICATION_IN_FLIGHT")
        self.assertEqual(payload["owner_view"], "calendar")
        self.assertEqual(payload["target_kind"], "PUBLICATION")
        self.assertEqual(payload["target_id"], PUB1)
        self.assertEqual(payload["recovery_controls"], [])
        self.assertFalse(payload["safety"]["automatic_retry"])
        self.assertFalse(payload["safety"]["business_mutation_performed"])

    def test_multiple_publishing_publications_fail_closed_without_selecting_one(self):
        payload = _coordinate_recovery_from_observed(
            diagnostic("PUBLICATION_IN_FLIGHT", publication_total=2, scope="ORGANIC"),
            [
                {"id": PUB1, "status": "PUBLISHING", "channel": "facebook_page"},
                {"id": PUB2, "status": "PUBLISHING", "channel": "instagram"},
            ],
            [], [], {}, {},
        )
        self.assertEqual(payload["state"], "AMBIGUOUS_EXISTING_OWNER")
        self.assertIsNone(payload["target_id"])
        self.assertEqual([row["id"] for row in payload["candidates"]["publishing_publications"]], [PUB1, PUB2])

    def test_cancelled_organic_lineage_to_one_ready_media_resolves_new_route_only(self):
        payload = _coordinate_recovery_from_observed(
            diagnostic("ONLY_CANCELLED_DISTRIBUTION_REMAINS", publication_total=1, scope="ORGANIC"),
            [{"id": PUB1, "status": "CANCELLED", "channel": "facebook_page"}],
            [], [creative()], {PUB1: [MEDIA1]}, {},
        )
        self.assertEqual(payload["state"], "EXACT_RECOVERY_OWNER")
        self.assertEqual(payload["intent"], "CREATE_NEW_DISTRIBUTION_FROM_CANCELLED_LINEAGE")
        self.assertEqual(payload["target_kind"], "MEDIA")
        self.assertEqual(payload["target_id"], MEDIA1)
        self.assertEqual(payload["recovery_controls"], ["PREPARE_FACEBOOK"])
        self.assertTrue(payload["contracts"]["cancelled_objects_are_never_resurrected"])
        self.assertFalse(payload["safety"]["automatic_recreation"])

    def test_cancelled_paid_lineage_requires_image_for_w49_paid_owner(self):
        payload = _coordinate_recovery_from_observed(
            diagnostic("ONLY_CANCELLED_DISTRIBUTION_REMAINS", paid_total=1, scope="PAID"),
            [], [{"id": PAID1, "status": "CANCELLED", "campaign_name": "Paid"}],
            [creative(kind="video")], {}, {PAID1: [MEDIA1]},
        )
        self.assertEqual(payload["state"], "RECOVERY_OWNER_GAP")
        self.assertIsNone(payload["target_id"])
        self.assertIn("non-image", payload["explanation"])

    def test_cancelled_objects_from_multiple_media_are_ambiguous(self):
        payload = _coordinate_recovery_from_observed(
            diagnostic("ONLY_CANCELLED_DISTRIBUTION_REMAINS", publication_total=2, scope="ORGANIC"),
            [
                {"id": PUB1, "status": "CANCELLED", "channel": "facebook_page"},
                {"id": PUB2, "status": "CANCELLED", "channel": "instagram"},
            ],
            [], [creative(MEDIA1), creative(MEDIA2)], {PUB1: [MEDIA1], PUB2: [MEDIA2]}, {},
        )
        self.assertEqual(payload["state"], "AMBIGUOUS_RECOVERY_OWNER")
        self.assertIsNone(payload["target_id"])
        self.assertEqual({row["id"] for row in payload["candidates"]["source_media"]}, {MEDIA1, MEDIA2})

    def test_missing_lineage_and_non_ready_media_fail_closed(self):
        missing = _coordinate_recovery_from_observed(
            diagnostic("ONLY_CANCELLED_DISTRIBUTION_REMAINS", publication_total=1, scope="ORGANIC"),
            [{"id": PUB1, "status": "CANCELLED", "channel": "facebook_page"}],
            [], [creative()], {}, {},
        )
        self.assertEqual(missing["state"], "RECOVERY_OWNER_GAP")
        stale = _coordinate_recovery_from_observed(
            diagnostic("ONLY_CANCELLED_DISTRIBUTION_REMAINS", publication_total=1, scope="ORGANIC"),
            [{"id": PUB1, "status": "CANCELLED", "channel": "facebook_page"}],
            [], [creative(stage="DRAFT")], {PUB1: [MEDIA1]}, {},
        )
        self.assertEqual(stale["state"], "RECOVERY_OWNER_GAP")
        self.assertIn("W64-ready", stale["explanation"])

    def test_cancelled_histogram_drift_disables_recovery(self):
        payload = _coordinate_recovery_from_observed(
            diagnostic("ONLY_CANCELLED_DISTRIBUTION_REMAINS", publication_total=2, scope="ORGANIC"),
            [{"id": PUB1, "status": "CANCELLED", "channel": "facebook_page"}],
            [], [creative()], {PUB1: [MEDIA1]}, {},
        )
        self.assertEqual(payload["state"], "RECOVERY_INVARIANT_GAP")
        self.assertIsNone(payload["target_id"])

    def test_navigation_rewrite_changes_only_exact_owner_fields(self):
        row = coordinate_row()
        original = deepcopy(row)
        guidance = _coordinate_recovery_from_observed(
            diagnostic("PUBLICATION_IN_FLIGHT", publication_total=1, scope="ORGANIC"),
            [{"id": PUB1, "status": "PUBLISHING", "channel": "facebook_page"}], [], [], {}, {},
        )
        result = _rewrite_coordinate_navigation(row, guidance)
        self.assertEqual(result["id"], original["id"])
        self.assertEqual(result["kind"], original["kind"])
        self.assertEqual(result["rank"], original["rank"])
        self.assertEqual(result["urgency"], original["urgency"])
        self.assertEqual(result["blocking"], original["blocking"])
        self.assertEqual(result["reason"], original["reason"])
        self.assertEqual(result["action"]["campaign_id"], CAMPAIGN_ID)
        self.assertEqual(result["action"]["view"], "calendar")
        self.assertEqual(result["action"]["entity_id"], PUB1)
        self.assertEqual(result["coordinate_recovery"], guidance)

    def test_action_center_preserves_order_priority_and_coordinate_diagnostic(self):
        row = coordinate_row()
        row["coordinate_state"] = diagnostic("PUBLICATION_IN_FLIGHT", publication_total=1, scope="ORGANIC")
        other = {"id": "operations:first", "kind": "crm_today", "rank": 35, "urgency": "HIGH", "action": {"view": "crm"}}
        parent_payload = {
            "schema": "binario.marketing.action-center.v1",
            "queue": [other, row],
            "next_action": other,
            "focus": {"now": [other], "next": [], "later": [row]},
            "contracts": {"existing": True},
        }
        guidance = _coordinate_recovery_from_observed(
            row["coordinate_state"], [{"id": PUB1, "status": "PUBLISHING", "channel": "facebook_page"}], [], [], {}, {},
        )
        runtime = AppRuntime.__new__(AppRuntime)
        with patch.object(parent.AppRuntime, "action_center", return_value=deepcopy(parent_payload)), patch.object(
            AppRuntime, "campaign_coordinate_recovery_guidance", return_value=guidance
        ):
            result = runtime.action_center("company-1")
        self.assertEqual([item["id"] for item in result["queue"]], ["operations:first", "campaign:coordinate:one"])
        guided = result["queue"][1]
        self.assertEqual(guided["rank"], 74)
        self.assertEqual(guided["urgency"], "LOW")
        self.assertEqual(guided["coordinate_state"], row["coordinate_state"])
        self.assertEqual(guided["coordinate_recovery"]["target_id"], PUB1)
        self.assertEqual(result["focus"]["later"][0]["coordinate_recovery"]["target_id"], PUB1)
        self.assertNotIn("coordinate_recovery", result["next_action"])

    def test_service_is_get_only_and_browser_adapter_has_zero_transport_or_synthetic_clicks(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_coordinate_recovery_guidance_app.py").read_text(encoding="utf-8")
        browser = (ROOT / "web" / "campaign-coordinate-recovery-guidance.js").read_text(encoding="utf-8")
        self.assertIn('parts[5] == "coordinate-recovery-guidance"', service)
        self.assertIn("def do_GET", service)
        self.assertIn("publication_lineage", service)
        self.assertIn("paid_lineage", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE", "MetaGraphClient"):
            self.assertNotIn(forbidden, service)
        for forbidden in ("opsApi(", "fetch(", ".click(", "dispatchEvent(", "setInterval(", "sendBeacon(", "method:'POST'", 'method:"POST"'):
            self.assertNotIn(forbidden, browser)
        self.assertIn("PREPARE_FACEBOOK", browser)
        self.assertIn("PREPARE_INSTAGRAM", browser)
        self.assertIn("SEND_TO_PAID", browser)
        self.assertIn("OBSERVE_PUBLICATION_IN_FLIGHT", browser)

    def test_docs_preserve_owner_authority_and_frozen_w99_boundary(self):
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_COORDINATE_RECOVERY_GUIDANCE.md").read_text(encoding="utf-8")
        for required in (
            "PUBLICATION_IN_FLIGHT",
            "ONLY_CANCELLED_DISTRIBUTION_REMAINS",
            "cancelled objects stay terminal",
            "canonical lineage",
            "W64 remains the next-action authority",
            "zero-transport",
            "main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",
        ):
            self.assertIn(required, doc)


if __name__ == "__main__":
    unittest.main()
