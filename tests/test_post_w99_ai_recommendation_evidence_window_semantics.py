from __future__ import annotations

import unittest
from datetime import datetime, timezone

from binario_marketing.ai_recommendation_evidence import extend_action_center, project_recommendation_evidence
from binario_marketing.ai_recommendation_handoff import RecommendationHandoffResolution
from binario_marketing.ai_recommendation_review import current_recommendations


COMPANY_ID = "company_" + "b" * 24
CAMPAIGN_ID = "campaign_" + "a" * 24


def _session_and_resolution():
    session = {
        "id": "ai_" + "1" * 24,
        "task": "CAMPAIGN",
        "campaign_id": CAMPAIGN_ID,
        "creative_media_id": None,
        "created_at": "2026-09-07T12:00:00+00:00",
        "context": {"selected_campaign": {"name": "Campaña exacta"}},
        "output": {"recommendations": [{
            "title": "Probar CTA",
            "why": "Hipótesis",
            "priority": "HIGH",
            "area": "CAMPAIGN",
            "next_step": "Aplicar manualmente",
        }]},
    }
    recommendation = current_recommendations([session])[0]
    resolution = RecommendationHandoffResolution(
        schema="binario.marketing.ai-recommendation-handoff-resolution.v1",
        company_id=COMPANY_ID,
        recommendation_id=recommendation["recommendation_id"],
        session_id=recommendation["session_id"],
        recommendation_sha256=recommendation["recommendation_sha256"],
        outcome="APPLIED",
        resolved_at="2026-09-07T13:00:00+00:00",
    )
    return session, resolution


def _empty_action_center():
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": COMPANY_ID, "name": "Empresa"},
        "queue": [],
        "next_action": None,
        "focus": {"now": [], "next": [], "later": []},
        "summary": {"queue_total": 0, "blocking": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "by_source": {}},
        "contracts": {},
        "safety": {},
    }


class AIRecommendationEvidenceWindowSemanticsTests(unittest.TestCase):
    def test_later_snapshot_does_not_claim_metric_window_is_strictly_post_application(self):
        session, resolution = _session_and_resolution()
        snapshot = {
            "id": "learning_" + "2" * 24,
            "company_id": COMPANY_ID,
            "date_preset": "last_7d",
            "created_at": "2026-09-07T14:00:00+00:00",
            "social": {"observations": [{
                "publication_id": "pub_1",
                "channel": "instagram",
                "campaign_id": CAMPAIGN_ID,
                "creative_media_id": None,
                "metrics": {"reach": 100},
            }]},
            "paid_media": {"observations": []},
            "crm": {},
            "coverage": {},
        }

        projection = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[resolution],
            snapshots=[snapshot],
            now=datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc),
        )
        row = projection["recommendations"][0]
        observed = row["post_application_snapshot"]
        self.assertEqual(row["state"], "EVIDENCE_AVAILABLE")
        self.assertEqual(row["followup_due_at"], "2026-09-08T13:00:00+00:00")
        self.assertTrue(observed["snapshot_captured_after_application"])
        self.assertFalse(observed["metric_window_strictly_post_application"])
        self.assertEqual(observed["date_preset"], "last_7d")
        self.assertTrue(projection["contracts"]["snapshot_capture_after_applied_does_not_bound_metric_event_time"])
        self.assertFalse(row["causal_attribution"])

    def test_capture_due_action_uses_applied_plus_24h_not_applied_time(self):
        session, resolution = _session_and_resolution()
        projection = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[resolution],
            snapshots=[],
            now=datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(projection["recommendations"][0]["state"], "CAPTURE_DUE")
        result = extend_action_center(_empty_action_center(), projection)
        row = next(item for item in result["queue"] if item.get("source") == "AI_EVIDENCE")
        self.assertEqual(row["due_at"], "2026-09-08T13:00:00+00:00")
        self.assertNotEqual(row["due_at"], resolution.resolved_at)


if __name__ == "__main__":
    unittest.main()
