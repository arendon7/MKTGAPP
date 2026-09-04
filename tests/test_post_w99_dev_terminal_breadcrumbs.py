import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PostW99DevTerminalBreadcrumbTests(unittest.TestCase):
    def test_terminal_keeps_cumulative_historical_breadcrumbs_without_importing_old_terminals(self):
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")

        historical = (
            "service_post_w99_campaign_execution_owner_cardinality_hardening_app",
            "service_post_w99_planned_only_actionability_app",
            "service_post_w99_setup_shadow_action_deduplication_app",
            "service_post_w99_campaign_media_candidate_selection_handoff_app",
            "service_post_w99_campaign_coordinate_actionability_app",
            "service_post_w99_campaign_attention_actionability_app",
        )
        for breadcrumb in historical:
            self.assertIn(breadcrumb, entrypoint)
        for old_terminal in historical:
            self.assertNotIn(f"from .{old_terminal} import", entrypoint)

        compatibility_imports = (
            "service_post_w99_setup_readiness_owner_handoff_app",
            "service_post_w99_campaign_execution_owner_drift_guard_app",
            "service_post_w99_operator_session_progress_app",
            "service_post_w99_operator_current_priority_continuity_app",
            "service_post_w99_operator_return_evidence_delta_app",
        )
        for module in compatibility_imports:
            self.assertEqual(entrypoint.count(f"from .{module} import"), 1)

        self.assertIn("AppRuntime as _OwnerDriftAppRuntime", entrypoint)
        self.assertIn("AppRuntime as _OperatorSessionProgressAppRuntime", entrypoint)
        self.assertIn("AppRuntime as _OperatorCurrentPriorityContinuityAppRuntime", entrypoint)
        self.assertIn("AppRuntime as _OperatorReturnEvidenceDeltaAppRuntime", entrypoint)
        self.assertEqual(
            entrypoint.count(
                "from .service_post_w99_operator_session_evidence_integration_app import"
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
