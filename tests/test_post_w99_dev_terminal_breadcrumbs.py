import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostW99DevTerminalBreadcrumbTests(unittest.TestCase):
    def test_terminal_keeps_cumulative_historical_breadcrumbs_without_importing_old_terminal(self):
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "service_post_w99_campaign_execution_owner_cardinality_hardening_app",
            entrypoint,
        )
        self.assertIn("service_post_w99_planned_only_actionability_app", entrypoint)
        self.assertIn("service_post_w99_setup_shadow_action_deduplication_app", entrypoint)
        self.assertNotIn(
            "from .service_post_w99_campaign_execution_owner_cardinality_hardening_app import",
            entrypoint,
        )
        self.assertNotIn(
            "from .service_post_w99_planned_only_actionability_app import",
            entrypoint,
        )
        self.assertEqual(
            entrypoint.count("from .service_post_w99_setup_shadow_action_deduplication_app import"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
