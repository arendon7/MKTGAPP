import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing import cli
from binario_marketing.service_post_w99_dev_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class PostW99DevEntrypointTests(unittest.TestCase):
    def test_cli_keeps_canonical_serve_and_adds_explicit_serve_dev(self):
        source = (ROOT / "src" / "binario_marketing" / "cli.py").read_text()
        self.assertIn('sub.add_parser("serve"', source)
        self.assertIn("from .service import serve", source)
        self.assertIn('sub.add_parser("serve-dev"', source)
        self.assertIn("from .service_post_w99_dev_app import serve", source)
        self.assertIn("default=8766", source)

    def test_serve_dev_dispatches_only_when_explicitly_selected(self):
        with patch("binario_marketing.service_post_w99_dev_app.serve") as dev_serve:
            rc = cli.main(["serve-dev", "--host", "127.0.0.1", "--port", "9988"])
        self.assertEqual(rc, 0)
        dev_serve.assert_called_once_with("127.0.0.1", 9988, allow_network=False, open_browser=False)

    def test_dev_runtime_contains_full_post_w99_chain(self):
        runtime = AppRuntime.create(ROOT, ROOT / "tmp-test-dev-entrypoint")
        try:
            company = runtime.create_company({"name": "Dev Company"})
            company_id = company["id"]
            action_center = runtime.action_center(company_id)
            self.assertEqual(action_center["schema"], "binario.marketing.action-center.v1")
            self.assertIn("observations", action_center)
            self.assertIn("shadowed_actions", action_center)
            self.assertTrue(action_center["contracts"]["planned_only_is_observational"])
            self.assertTrue(action_center["contracts"]["planned_only_excluded_from_action_queue"])
            self.assertTrue(action_center["contracts"]["planned_only_excluded_from_today"])
            self.assertTrue(action_center["contracts"]["setup_shadow_deduplication_fail_closed"])
            self.assertTrue(action_center["contracts"]["setup_shadow_requires_full_canonical_coverage"])
            self.assertTrue(action_center["contracts"]["specific_canonical_actions_are_never_removed"])
            with self.assertRaises(ValueError):
                runtime.navigator(company_id, "x")
            self.assertTrue(callable(runtime.commercial_pipeline))
            self.assertEqual(runtime.commercial_outcomes(company_id)["schema"], "binario.marketing.commercial-outcomes.v1")
            self.assertEqual(runtime.decision_review(company_id)["schema"], "binario.marketing.decision-review.v1")
            self.assertEqual(runtime.portfolio_control_tower()["schema"], "binario.marketing.portfolio-control-tower.v1")
            self.assertEqual(runtime.executive_cockpit(company_id)["schema"], "binario.marketing.executive-cockpit.v1")
            self.assertEqual(runtime.today_execution(company_id)["schema"], "binario.marketing.today-execution.v1")
            self.assertEqual(runtime.evidence_observability(company_id)["schema"], "binario.marketing.evidence-observability.v1")
            self.assertEqual(runtime.portfolio_cadence()["schema"], "binario.marketing.portfolio-cadence.v2")
            self.assertTrue(callable(runtime.update_opportunity))
            self.assertTrue(callable(runtime.create_activity))
            self.assertTrue(callable(runtime.reschedule_activity))
            self.assertTrue(callable(runtime.campaign_results_owner_context))
            self.assertTrue(callable(runtime.campaign_execution_owner_context))
            self.assertTrue(callable(runtime.campaign_coordinate_state))
            self.assertTrue(callable(runtime.campaign_coordinate_recovery_guidance))
        finally:
            if runtime.social_scheduler is not None:
                runtime.social_scheduler.shutdown()
            runtime.proxies.shutdown()
            runtime.transcriptions.shutdown()
            runtime.renders.shutdown()
            import shutil
            shutil.rmtree(ROOT / "tmp-test-dev-entrypoint", ignore_errors=True)

    def test_dev_http_server_is_loopback_capable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Dev HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            try:
                self.assertEqual(server.server_address[0], "127.0.0.1")
            finally:
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown()
                runtime.transcriptions.shutdown()
                runtime.renders.shutdown()
                server.server_close()

    def test_docs_preserve_w99_release_boundary_and_accumulated_composition(self):
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text()
        doc = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text()
        self.assertIn("service_post_w99_campaign_media_candidate_selection_handoff_app", entrypoint)
        for breadcrumb in (
            "service_post_w99_setup_shadow_action_deduplication_app",
            "service_post_w99_planned_only_actionability_app",
            "service_post_w99_campaign_execution_owner_cardinality_hardening_app",
        ):
            self.assertIn(breadcrumb, entrypoint)
        self.assertNotIn("from .service_post_w99_setup_shadow_action_deduplication_app import", entrypoint)
        self.assertNotIn("from .service_post_w99_planned_only_actionability_app import", entrypoint)
        self.assertNotIn("from .service_post_w99_campaign_execution_owner_cardinality_hardening_app import", entrypoint)
        self.assertIn("serve-dev", doc)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No debe interpretarse como W100", doc)
        for label in (
            "Campaign Execution Owner Relay",
            "Campaign Execution Candidate Selector",
            "Campaign Creative Creation Intent Handoff",
            "Campaign Coordinate State Decomposition",
            "Campaign Coordinate Recovery Guidance",
            "Campaign Execution Owner Cardinality Hardening",
            "Planned-Only Actionability Preservation",
            "Setup Shadow Action Deduplication",
            "Campaign MEDIA Candidate Selection Handoff",
        ):
            self.assertIn(label, doc)
        for module in (
            "service_post_w99_campaign_execution_owner_relay_app",
            "service_post_w99_campaign_execution_candidate_selector_app",
            "service_post_w99_campaign_creative_creation_intent_handoff_app",
            "service_post_w99_campaign_coordinate_state_decomposition_app",
            "service_post_w99_campaign_coordinate_recovery_guidance_app",
            "service_post_w99_campaign_execution_owner_cardinality_hardening_app",
            "service_post_w99_planned_only_actionability_app",
            "service_post_w99_setup_shadow_action_deduplication_app",
            "service_post_w99_campaign_media_candidate_selection_handoff_app",
        ):
            self.assertIn(module, doc)
        browser_chain = (
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → "
            "Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → "
            "Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → "
            "Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance → "
            "Campaign Execution Owner Cardinality Hardening → Planned-Only Actionability Preservation → "
            "Campaign MEDIA Candidate Selection Handoff"
        )
        self.assertIn(browser_chain, doc)

    def test_planned_only_adapter_is_bootstrapped_after_cardinality_hardening(self):
        service = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_planned_only_actionability_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('path == "/campaign-execution-owner-cardinality-hardening.js"', service)
        self.assertIn("loadPostW99PlannedOnlyActionabilityPreservation", service)
        self.assertIn("script.src='/planned-only-actionability.js'", service)
        self.assertIn("data-post-w99-planned-only-actionability", service)

    def test_setup_shadow_remains_backend_only_parent(self):
        service = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_setup_shadow_action_deduplication_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("service_post_w99_planned_only_actionability_app", service)
        self.assertIn("deduplicate_setup_shadow_actions", service)
        self.assertNotIn("def _static", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)

    def test_media_selection_adapter_is_terminal_after_setup_shadow(self):
        service = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_campaign_media_candidate_selection_handoff_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("service_post_w99_setup_shadow_action_deduplication_app", service)
        self.assertIn('path == "/planned-only-actionability.js"', service)
        self.assertIn("loadPostW99CampaignMediaCandidateSelectionHandoff", service)
        self.assertIn("script.src='/campaign-media-candidate-selection-handoff.js'", service)
        self.assertIn("data-post-w99-campaign-media-candidate-selection-handoff", service)


if __name__ == "__main__":
    unittest.main()
