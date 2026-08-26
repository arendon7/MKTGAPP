import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostW99DevTerminalBreadcrumbTests(unittest.TestCase):
    def test_terminal_keeps_cumulative_historical_breadcrumbs_without_importing_old_terminals(self):
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")

        for breadcrumb in (
            "service_post_w99_campaign_execution_owner_cardinality_hardening_app",
            "service_post_w99_planned_only_actionability_app",
            "service_post_w99_setup_shadow_action_deduplication_app",
            "service_post_w99_campaign_media_candidate_selection_handoff_app",
        ):
            self.assertIn(breadcrumb, entrypoint)

        for old_terminal in (
            "service_post_w99_campaign_execution_owner_cardinality_hardening_app",
            "service_post_w99_planned_only_actionability_app",
            "service_post_w99_setup_shadow_action_deduplication_app",
        ):
            self.assertNotIn(f"from .{old_terminal} import", entrypoint)

        self.assertEqual(
            entrypoint.count(
                "from .service_post_w99_campaign_media_candidate_selection_handoff_app import"
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
