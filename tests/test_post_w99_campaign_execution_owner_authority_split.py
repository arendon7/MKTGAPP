import unittest

from binario_marketing.service_post_w99_campaign_execution_owner_relay_app import (
    _EXECUTION_OWNER_ACTION_KINDS,
    _owner_resolution,
)


class PostW99CampaignExecutionOwnerAuthoritySplitTests(unittest.TestCase):
    def test_w65_review_results_is_not_rewritten_by_w64_action_center_relay(self):
        self.assertNotIn("review_results", _EXECUTION_OWNER_ACTION_KINDS)
        self.assertIn("fix_execution", _EXECUTION_OWNER_ACTION_KINDS)
        self.assertIn("review_paid", _EXECUTION_OWNER_ACTION_KINDS)

    def test_w64_context_can_still_describe_review_results_without_claiming_action_center_authority(self):
        resolution = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "REVIEW_RESULTS", "view": "analytics"},
            linked_creatives=[],
            publications=[],
            linked_paid=[],
        )
        self.assertEqual(resolution["state"], "EXACT_TARGET")
        self.assertEqual(resolution["target_kind"], "CAMPAIGN_RESULTS")
        self.assertEqual(resolution["target_id"], "campaign_exact")


if __name__ == "__main__":
    unittest.main()
