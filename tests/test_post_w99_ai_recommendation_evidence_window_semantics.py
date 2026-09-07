from __future__ import annotations

import unittest
from datetime import datetime, timezone

from binario_marketing.ai_recommendation_evidence import project_recommendation_evidence
from binario_marketing.ai_recommendation_handoff import RecommendationHandoffResolution
from binario_marketing.ai_recommendation_review import current_recommendations


COMPANY_ID = "company_" + "b" * 24
CAMPAIGN_ID = "campaign_" + "a" * 24


class AIRecommendationEvidenceWindowSemanticsTests(unittest.TestCase):
    def test_later_snapshot_does_not_claim_metric_window_is_strictly_post_application(self):
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
        self.assertTrue(observed["snapshot_captured_after_application"])
        self.assertFalse(observed["metric_window_strictly_post_application"])
        self.assertEqual(observed["date_preset"], "last_7d")
        self.assertTrue(projection["contracts"]["snapshot_capture_after_applied_does_not_bound_metric_event_time"])
        self.assertFalse(row["causal_attribution"])


if __name__ == "__main__":
    unittest.main()
