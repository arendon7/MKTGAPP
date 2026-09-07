from __future__ import annotations

import unittest

from binario_marketing.ai_human_feedback_context import project_ai_human_feedback_context
from binario_marketing.ai_recommendation_review import RecommendationReview, current_recommendations


COMPANY_ID = "company_" + "b" * 24
CAMPAIGN_ID = "campaign_" + "a" * 24


def _session(session_id: str, created_at: str, title: str) -> dict:
    return {
        "id": session_id,
        "task": "CAMPAIGN",
        "campaign_id": CAMPAIGN_ID,
        "creative_media_id": None,
        "created_at": created_at,
        "context": {"selected_campaign": {"name": "Campaña"}},
        "output": {"recommendations": [{
            "title": title,
            "why": "Histórico",
            "priority": "MEDIUM",
            "area": "CAMPAIGN",
            "next_step": "Revisar",
        }]},
    }


def _review(session: dict) -> RecommendationReview:
    rec = current_recommendations([session])[0]
    return RecommendationReview(
        schema="binario.marketing.ai-recommendation-review.v1",
        company_id=COMPANY_ID,
        recommendation_id=rec["recommendation_id"],
        session_id=rec["session_id"],
        recommendation_sha256=rec["recommendation_sha256"],
        decision="DISMISSED",
        decided_at="2026-09-07T13:00:00+00:00",
    )


class AIHumanFeedbackOrderTests(unittest.TestCase):
    def test_history_is_newest_first_even_when_caller_input_is_oldest_first(self):
        old = _session("ai_" + "1" * 24, "2026-09-07T10:00:00+00:00", "Vieja")
        new = _session("ai_" + "2" * 24, "2026-09-07T12:00:00+00:00", "Nueva")
        projection = project_ai_human_feedback_context(
            COMPANY_ID,
            task="CAMPAIGN",
            campaign_id=CAMPAIGN_ID,
            creative_media_id=None,
            sessions=[old, new],
            reviews=[_review(old), _review(new)],
            resolutions=[],
            evidence={},
        )
        self.assertEqual(
            [row["historical_proposal"]["title"] for row in projection["items"]],
            ["Nueva", "Vieja"],
        )
        self.assertEqual(projection["contracts"]["history_order"], "SESSION_CREATED_AT_DESC")


if __name__ == "__main__":
    unittest.main()
