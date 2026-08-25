import unittest

from binario_marketing.service_post_w99_executive_cockpit_app import compose_executive_cockpit


class PostW99ExecutiveCockpitMediumPriorityTests(unittest.TestCase):
    def test_medium_campaign_action_is_attention_not_stable(self):
        payload = compose_executive_cockpit(
            company={"id": "company_demo", "name": "Demo"},
            action_center={
                "summary": {"queue_total": 1, "blocking": 0, "critical": 0, "high": 0},
                "next_action": {
                    "id": "campaign-medium", "source": "CAMPAIGN", "urgency": "MEDIUM",
                    "blocking": False, "title": "Capturar resultados", "detail": "Falta evidencia",
                    "action": {"view": "analytics", "label": "Capturar"},
                },
                "queue": [{
                    "id": "campaign-medium", "source": "CAMPAIGN", "urgency": "MEDIUM",
                    "blocking": False, "title": "Capturar resultados", "detail": "Falta evidencia",
                    "action": {"view": "analytics", "label": "Capturar"},
                }],
            },
            pipeline={"summary": {"opportunities": 0, "open_opportunities": 0, "requires_attention": 0, "proposals": 0, "won": 0, "lost": 0, "amounts_by_currency": []}},
            outcomes={"summary": {"attention": 0, "captured_leads": 0, "converted_leads": 0, "attributed_opportunities": 0, "attributed_won": 0, "value_by_currency": {}}},
            results={"summary": {"active_campaigns": 1, "requires_attention": 0, "with_observed_evidence": 0, "with_attributed_opportunities": 0, "with_human_decision": 0}, "latest_snapshot": None},
            review={"summary": {"campaigns_with_decision": 0, "ready_for_review": 0, "follow_through_required": 0, "awaiting_evidence": 0}},
        )
        campaign_lane = next(row for row in payload["lanes"] if row["key"] == "CAMPAIGNS")
        self.assertEqual(campaign_lane["state"], "ATTENTION")
        self.assertEqual(payload["status"]["state"], "ATTENTION")
        self.assertTrue(payload["contracts"]["medium_priority_is_attention"])


if __name__ == "__main__":
    unittest.main()
