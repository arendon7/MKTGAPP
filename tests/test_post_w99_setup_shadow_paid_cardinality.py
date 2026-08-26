import unittest

from binario_marketing.service_post_w99_setup_shadow_action_deduplication_app import (
    deduplicate_setup_shadow_actions,
)


def _row(action_id, source, kind, owner_resolution=None):
    row = {
        "id": action_id,
        "rank": 50,
        "urgency": "MEDIUM",
        "source": source,
        "kind": kind,
        "title": kind,
        "detail": "detail",
        "action": {"label": "Abrir", "view": "pauta" if source == "CAMPAIGN" else "companies"},
        "reason": {"code": kind.upper(), "explanation": "reason"},
        "due_at": None,
        "blocking": False,
        "requires_human_action": True,
        "read_only_recommendation": True,
    }
    if owner_resolution is not None:
        row["owner_resolution"] = owner_resolution
    return row


def _payload(resolution):
    queue = [
        _row("setup-paid", "SETUP", "paid_draft"),
        _row("review-paid", "CAMPAIGN", "review_paid", resolution),
    ]
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": "company-1", "name": "Company"},
        "next_action": queue[0],
        "summary": {
            "queue_total": 2,
            "blocking": 0,
            "critical": 0,
            "high": 0,
            "medium": 2,
            "low": 0,
            "by_source": {"OPERATIONS": 0, "COMMERCIAL": 0, "CAMPAIGN": 1, "SETUP": 1},
            "campaign_actions": 1,
        },
        "focus": {"now": [], "next": list(queue), "later": []},
        "queue": queue,
        "observations": [],
        "contracts": {"planned_only_is_observational": True},
        "safety": {"read_only_projection": True},
    }


def _resolution(*ids, state=None, target_id=None):
    state = state or ("EXACT_TARGET" if len(ids) == 1 else "AMBIGUOUS_TARGET")
    if target_id is None and state == "EXACT_TARGET" and len(ids) == 1:
        target_id = ids[0]
    return {
        "state": state,
        "source_code": "REVIEW_PAID",
        "owner_view": "pauta",
        "target_kind": "PAID_DRAFT",
        "target_id": target_id,
        "candidate_count": len(ids),
        "candidates": [{"id": item, "status": "DRAFT"} for item in ids],
    }


def _project(resolution, paid_ids):
    return deduplicate_setup_shadow_actions(
        _payload(resolution),
        active_campaigns_without_media=set(),
        paid_draft_ids=set(paid_ids),
        creative_profile_exists=False,
    )


class SetupShadowPaidCardinalityRegressionTests(unittest.TestCase):
    def assert_setup_remains(self, resolution, paid_ids=("draft-a",)):
        result = _project(resolution, paid_ids)
        self.assertIn("setup-paid", [row["id"] for row in result["queue"]])
        self.assertEqual(result["shadowed_actions"], [])

    def test_exact_target_requires_exactly_one_candidate_and_matching_target_id(self):
        malformed_many = _resolution("draft-a", "draft-b", state="EXACT_TARGET", target_id="draft-a")
        self.assert_setup_remains(malformed_many)

        mismatched = _resolution("draft-a", state="EXACT_TARGET", target_id="draft-other")
        self.assert_setup_remains(mismatched)

    def test_ambiguous_target_requires_multiple_candidates_and_no_target_id(self):
        malformed_one = _resolution("draft-a", state="AMBIGUOUS_TARGET", target_id=None)
        self.assert_setup_remains(malformed_one)

        selected_while_ambiguous = _resolution(
            "draft-a", "draft-b", state="AMBIGUOUS_TARGET", target_id="draft-a"
        )
        self.assert_setup_remains(selected_while_ambiguous)

    def test_candidate_shape_and_draft_status_are_fail_closed(self):
        malformed_shape = _resolution("draft-a")
        malformed_shape["candidates"].append("not-a-dict")
        malformed_shape["candidate_count"] = 2
        self.assert_setup_remains(malformed_shape)

        wrong_status = _resolution("draft-a")
        wrong_status["candidates"][0]["status"] = "READY"
        self.assert_setup_remains(wrong_status)

    def test_resolution_source_and_owner_are_part_of_canonical_identity(self):
        wrong_source = _resolution("draft-a")
        wrong_source["source_code"] = "OTHER"
        self.assert_setup_remains(wrong_source)

        wrong_owner = _resolution("draft-a")
        wrong_owner["owner_view"] = "campaigns"
        self.assert_setup_remains(wrong_owner)

    def test_valid_exact_and_ambiguous_review_paid_still_cover_setup(self):
        exact = _project(_resolution("draft-a"), {"draft-a"})
        self.assertNotIn("setup-paid", [row["id"] for row in exact["queue"]])
        self.assertEqual(exact["shadowed_actions"][0]["id"], "setup-paid")

        ambiguous = _project(
            _resolution("draft-a", "draft-b", state="AMBIGUOUS_TARGET", target_id=None),
            {"draft-a", "draft-b"},
        )
        self.assertNotIn("setup-paid", [row["id"] for row in ambiguous["queue"]])
        self.assertEqual(ambiguous["shadowed_actions"][0]["id"], "setup-paid")


if __name__ == "__main__":
    unittest.main()
