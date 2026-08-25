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
            self.assertEqual(runtime.action_center(company_id)["schema"], "binario.marketing.action-center.v1")
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

    def test_docs_preserve_w99_release_boundary(self):
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text()
        doc = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text()
        self.assertIn("service_post_w99_campaign_execution_candidate_selector_app", entrypoint)
        self.assertIn("serve-dev", doc)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No debe interpretarse como W100", doc)
        for label in (
            "Decision Review",
            "Portfolio Control Tower",
            "Executive Marketing Cockpit",
            "Today / Operator Execution",
            "Execution Return Flow",
            "Contextual Deep Linking",
            "Evidence Observability",
            "Portfolio Cadence",
            "Contextual Control Handoff",
            "Opportunity Follow-up Control",
            "Existing Activity Reschedule Control",
            "Campaign Results Owner Handoff",
            "Campaign Execution Owner Relay",
            "Campaign Execution Candidate Selector",
        ):
            self.assertIn(label, doc)
        for module in (
            "service_post_w99_portfolio_cadence_app",
            "service_post_w99_contextual_control_handoff_app",
            "service_post_w99_opportunity_followup_control_app",
            "service_post_w99_existing_activity_reschedule_control_app",
            "service_post_w99_campaign_results_owner_handoff_app",
            "service_post_w99_campaign_execution_owner_relay_app",
            "service_post_w99_campaign_execution_candidate_selector_app",
        ):
            self.assertIn(module, doc)
        self.assertIn(
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector",
            doc,
        )


if __name__ == "__main__":
    unittest.main()
