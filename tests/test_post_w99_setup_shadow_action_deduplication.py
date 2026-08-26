import tempfile
import unittest
from pathlib import Path

from binario_marketing import service_post_w99_planned_only_actionability_app as parent
from binario_marketing.service_post_w99_setup_shadow_action_deduplication_app import (
    AppRuntime,
    deduplicate_setup_shadow_actions,
)

ROOT = Path(__file__).resolve().parents[1]


def row(
    action_id: str,
    source: str,
    kind: str,
    *,
    rank: int = 50,
    urgency: str = "MEDIUM",
    campaign_id: str | None = None,
    owner_resolution: dict | None = None,
) -> dict:
    result = {
        "id": action_id,
        "rank": rank,
        "urgency": urgency,
        "source": source,
        "kind": kind,
        "title": kind,
        "detail": "detail",
        "action": {
            "label": "Abrir",
            "view": "campaigns" if source == "CAMPAIGN" else "companies",
            "campaign_id": campaign_id,
        },
        "reason": {"code": kind.upper(), "explanation": "reason"},
        "due_at": None,
        "blocking": False,
        "requires_human_action": True,
        "read_only_recommendation": True,
    }
    if owner_resolution is not None:
        result["owner_resolution"] = owner_resolution
    return result


def payload(queue: list[dict]) -> dict:
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": "company-1", "name": "Company"},
        "next_action": queue[0] if queue else None,
        "summary": {
            "queue_total": len(queue),
            "blocking": 0,
            "critical": 0,
            "high": 0,
            "medium": len(queue),
            "low": 0,
            "by_source": {
                "OPERATIONS": 0,
                "COMMERCIAL": 0,
                "CAMPAIGN": sum(1 for item in queue if item["source"] == "CAMPAIGN"),
                "SETUP": sum(1 for item in queue if item["source"] == "SETUP"),
            },
            "campaign_actions": sum(1 for item in queue if item["source"] == "CAMPAIGN"),
        },
        "focus": {"now": [], "next": list(queue), "later": []},
        "queue": list(queue),
        "observations": [],
        "contracts": {"planned_only_is_observational": True},
        "safety": {"read_only_projection": True},
    }


def paid_resolution(*ids: str) -> dict:
    state = "EXACT_TARGET" if len(ids) == 1 else "AMBIGUOUS_TARGET"
    return {
        "state": state,
        "source_code": "REVIEW_PAID",
        "owner_view": "pauta",
        "target_kind": "PAID_DRAFT",
        "target_id": ids[0] if len(ids) == 1 else None,
        "candidate_count": len(ids),
        "candidates": [{"id": item, "status": "DRAFT"} for item in ids],
    }


class SetupShadowProjectionTests(unittest.TestCase):
    def project(
        self,
        queue,
        *,
        missing_media=None,
        paid_drafts=None,
        creative_profile_exists=False,
    ):
        return deduplicate_setup_shadow_actions(
            payload(queue),
            active_campaigns_without_media=set(missing_media or []),
            paid_draft_ids=set(paid_drafts or []),
            creative_profile_exists=creative_profile_exists,
        )

    def test_campaign_media_is_shadowed_only_with_full_exact_campaign_coverage(self):
        queue = [
            row("setup-media", "SETUP", "campaign_media", rank=82, urgency="LOW"),
            row("create-a", "CAMPAIGN", "create_creative", campaign_id="campaign-a"),
            row("create-b", "CAMPAIGN", "create_creative", campaign_id="campaign-b"),
        ]
        result = self.project(queue, missing_media={"campaign-a", "campaign-b"})

        self.assertEqual([item["id"] for item in result["queue"]], ["create-a", "create-b"])
        self.assertEqual(result["shadowed_actions"][0]["id"], "setup-media")
        self.assertEqual(
            result["shadowed_actions"][0]["shadowing"]["reason_code"],
            "CAMPAIGN_MEDIA_FULLY_COVERED",
        )
        self.assertFalse(result["shadowed_actions"][0]["requires_human_action"])
        self.assertFalse(result["shadowed_actions"][0]["shadowing"]["today_eligible"])
        self.assertEqual(result["summary"]["shadowed_setup_actions"], 1)

    def test_campaign_media_partial_coverage_fails_closed(self):
        queue = [
            row("setup-media", "SETUP", "campaign_media", rank=82, urgency="LOW"),
            row("create-a", "CAMPAIGN", "create_creative", campaign_id="campaign-a"),
        ]
        result = self.project(queue, missing_media={"campaign-a", "campaign-b"})
        self.assertEqual([item["id"] for item in result["queue"]], ["setup-media", "create-a"])
        self.assertEqual(result["shadowed_actions"], [])
        self.assertTrue(result["contracts"]["partial_setup_coverage_remains_actionable"])

    def test_setup_creative_is_shadowed_only_when_create_flow_exists(self):
        setup = row("setup-creative", "SETUP", "setup_creative", rank=82, urgency="LOW")
        create = row("create", "CAMPAIGN", "create_creative", campaign_id="campaign-a")

        covered = self.project([setup, create], creative_profile_exists=False)
        self.assertEqual([item["id"] for item in covered["queue"]], ["create"])
        self.assertEqual(
            covered["shadowed_actions"][0]["shadowing"]["reason_code"],
            "CREATIVE_READINESS_COVERED_BY_CREATE_FLOW",
        )

        uncovered = self.project([setup], creative_profile_exists=False)
        self.assertEqual([item["id"] for item in uncovered["queue"]], ["setup-creative"])

        inconsistent = self.project([setup, create], creative_profile_exists=True)
        self.assertEqual([item["id"] for item in inconsistent["queue"]], ["setup-creative", "create"])

    def test_paid_draft_aggregate_requires_complete_candidate_identity_coverage(self):
        queue = [
            row("setup-paid", "SETUP", "paid_draft", rank=82, urgency="LOW"),
            row(
                "review-a",
                "CAMPAIGN",
                "review_paid",
                campaign_id="campaign-a",
                owner_resolution=paid_resolution("draft-a"),
            ),
            row(
                "review-b",
                "CAMPAIGN",
                "review_paid",
                campaign_id="campaign-b",
                owner_resolution=paid_resolution("draft-b", "draft-c"),
            ),
        ]
        covered = self.project(queue, paid_drafts={"draft-a", "draft-b", "draft-c"})
        self.assertNotIn("setup-paid", [item["id"] for item in covered["queue"]])
        self.assertEqual(
            covered["shadowed_actions"][0]["shadowing"]["reason_code"],
            "PAID_DRAFTS_FULLY_COVERED",
        )

        partial = self.project(queue, paid_drafts={"draft-a", "draft-b", "draft-c", "orphan"})
        self.assertIn("setup-paid", [item["id"] for item in partial["queue"]])
        self.assertEqual(partial["shadowed_actions"], [])

    def test_malformed_paid_resolution_never_suppresses_setup(self):
        malformed = paid_resolution("draft-a")
        malformed["candidate_count"] = 2
        queue = [
            row("setup-paid", "SETUP", "paid_draft"),
            row(
                "review",
                "CAMPAIGN",
                "review_paid",
                campaign_id="campaign-a",
                owner_resolution=malformed,
            ),
        ]
        result = self.project(queue, paid_drafts={"draft-a"})
        self.assertIn("setup-paid", [item["id"] for item in result["queue"]])

    def test_unrelated_setup_and_specific_actions_are_never_removed(self):
        queue = [
            row("meta", "SETUP", "setup_meta", rank=82, urgency="LOW"),
            row("crm", "SETUP", "setup_crm", rank=82, urgency="LOW"),
            row("capture", "CAMPAIGN", "capture_results", campaign_id="campaign-a"),
        ]
        result = self.project(queue)
        self.assertEqual([item["id"] for item in result["queue"]], ["meta", "crm", "capture"])
        self.assertEqual(result["shadowed_actions"], [])
        self.assertTrue(result["contracts"]["specific_canonical_actions_are_never_removed"])

    def test_projection_is_idempotent(self):
        queue = [
            row("setup-media", "SETUP", "campaign_media"),
            row("create", "CAMPAIGN", "create_creative", campaign_id="campaign-a"),
        ]
        once = self.project(queue, missing_media={"campaign-a"})
        twice = deduplicate_setup_shadow_actions(
            once,
            active_campaigns_without_media={"campaign-a"},
            paid_draft_ids=set(),
            creative_profile_exists=False,
        )
        self.assertEqual([item["id"] for item in twice["queue"]], ["create"])
        self.assertEqual(len(twice["shadowed_actions"]), 1)


class SetupShadowRuntimeTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_planned_only_preservation(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_empty_creative_setup_is_not_repeated_when_campaign_create_actions_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Shadow Co"})
                first = runtime.campaigns.create(company["id"], {
                    "name": "Campaign A",
                    "objective": "LEADS",
                    "status": "IN_PROGRESS",
                    "channels": ["instagram"],
                })
                second = runtime.campaigns.create(company["id"], {
                    "name": "Campaign B",
                    "objective": "LEADS",
                    "status": "READY",
                    "channels": ["facebook_page"],
                })

                action_center = runtime.action_center(company["id"])
                queue = action_center["queue"]
                create_ids = {
                    (item.get("action") or {}).get("campaign_id")
                    for item in queue
                    if item.get("source") == "CAMPAIGN" and item.get("kind") == "create_creative"
                }
                self.assertEqual(create_ids, {first.id, second.id})
                self.assertNotIn("campaign_media", {item.get("kind") for item in queue})
                self.assertNotIn("setup_creative", {item.get("kind") for item in queue})

                shadowed_kinds = {item.get("kind") for item in action_center["shadowed_actions"]}
                self.assertIn("campaign_media", shadowed_kinds)
                self.assertIn("setup_creative", shadowed_kinds)
                self.assertTrue(action_center["contracts"]["setup_shadow_deduplication_fail_closed"])

                today = runtime.today_execution(company["id"])
                self.assertNotIn("campaign_media", {item.get("kind") for item in today["plan"]})
                self.assertNotIn("setup_creative", {item.get("kind") for item in today["plan"]})
                self.assertTrue({first.id, second.id}.issubset({
                    (item.get("action") or {}).get("campaign_id")
                    for item in today["plan"]
                    if item.get("kind") == "create_creative"
                }))
            finally:
                self._shutdown(runtime)

    def test_service_is_read_only_and_docs_preserve_w99_boundary(self):
        service = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_setup_shadow_action_deduplication_app.py"
        ).read_text(encoding="utf-8")
        doc = (
            ROOT / "docs" / "POST_W99_SETUP_SHADOW_ACTION_DEDUPLICATION.md"
        ).read_text(encoding="utf-8")

        self.assertIn("service_post_w99_planned_only_actionability_app", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No constituye W100", doc)
        self.assertIn("physical UAT", doc)


if __name__ == "__main__":
    unittest.main()
