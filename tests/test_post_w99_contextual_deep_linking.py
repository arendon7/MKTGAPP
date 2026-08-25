import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_contextual_deep_linking_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PostW99ContextualDeepLinkingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Contextual Deep Link Co"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_terminal_runtime_preserves_execution_return_today_and_cockpits(self):
        company_id = self.company["id"]
        self.assertEqual(self.runtime.today_execution(company_id)["schema"], "binario.marketing.today-execution.v1")
        self.assertEqual(self.runtime.executive_cockpit(company_id)["schema"], "binario.marketing.executive-cockpit.v1")
        self.assertEqual(self.runtime.portfolio_control_tower()["schema"], "binario.marketing.portfolio-control-tower.v1")
        self.assertEqual(self.runtime.action_center(company_id)["schema"], "binario.marketing.action-center.v1")

    def test_http_bootstrap_loads_contextual_layer_after_execution_return(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/today-execution.js", timeout=5) as response:
                today_source = response.read().decode("utf-8")
            self.assertIn("execution-return.js", today_source)

            with urlopen(base + "/execution-return.js", timeout=5) as response:
                return_source = response.read().decode("utf-8")
            self.assertIn("contextual-deep-linking.js", return_source)
            self.assertIn("data-post-w99-contextual-deep-linking", return_source)

            with urlopen(base + "/contextual-deep-linking.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("binario.marketing.contextual-deep-link.v1", source)
            self.assertIn("contextualDeepLinkDescriptor", source)
            self.assertIn("FOUND_EXACT", source)
            self.assertIn("TARGET_NOT_FOUND", source)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_target_resolution_is_id_based_and_fail_closed(self):
        source = (ROOT / "web" / "contextual-deep-linking.js").read_text(encoding="utf-8")
        for marker in (
            "target_kind='ACTIVITY'",
            "target_kind='OPPORTUNITY'",
            "target_kind='CONTACT'",
            "target_kind='PUBLICATION'",
            "target_kind=base.contact_id?'HANDOFF':'LEAD'",
            "target_kind='CAMPAIGN'",
            "target_kind='CAMPAIGN_EXECUTION'",
            "target_kind='CAMPAIGN_INTELLIGENCE'",
            "target_kind='MEDIA'",
            "target_kind:'OWNER_ONLY'",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("includes(context.title", source)
        self.assertNotIn("localeCompare(context.title", source)
        self.assertNotIn("fuzzy", source.lower())

    def test_existing_owner_state_is_used_only_for_presentation(self):
        source = (ROOT / "web" / "contextual-deep-linking.js").read_text(encoding="utf-8")
        self.assertIn("crmState.tab='followups'", source)
        self.assertIn("crmState.tab='pipeline'", source)
        self.assertIn("crmState.tab='contacts'", source)
        self.assertIn("editorialState.selectedId=context.target_id", source)
        self.assertIn("campaignState.selectedId=context.target_id", source)
        self.assertIn("wave64ExecutionState.onlyAction=false", source)
        self.assertIn("wave65ResultsState.onlyAttention=false", source)
        self.assertNotIn("companyContentState.pickId=context.target_id", source)

    def test_exact_dom_anchors_are_transient_and_cover_owner_surfaces(self):
        source = (ROOT / "web" / "contextual-deep-linking.js").read_text(encoding="utf-8")
        for marker in (
            "deepActivityId", "deepOpportunityId", "deepContactId", "deepPublicationId",
            "deepLeadId", "deepHandoffLeadId", "deepCampaignId",
            "deepExecutionCampaignId", "deepIntelligenceCampaignId", "deepMediaId",
        ):
            self.assertIn(marker, source)
        self.assertIn("contextual-deep-link-highlight", source)
        self.assertIn("scrollIntoView", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)

    def test_adapter_has_no_business_transport_polling_or_synthetic_execution(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_contextual_deep_linking_app.py").read_text(encoding="utf-8")
        source = (ROOT / "web" / "contextual-deep-linking.js").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_execution_return_app as base", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", "fetch(", "opsApi(", "setInterval", "sendBeacon", ".click(", "dispatchEvent("):
            self.assertNotIn(forbidden, source)

    def test_docs_preserve_navigation_and_release_boundaries(self):
        doc = (ROOT / "docs" / "POST_W99_CONTEXTUAL_DEEP_LINKING.md").read_text(encoding="utf-8")
        self.assertIn("Action Center priority", doc)
        self.assertIn("does not determine completion", doc)
        self.assertIn("OWNER_ONLY", doc)
        self.assertIn("TARGET_NOT_FOUND", doc)
        self.assertIn("never calls `.click()`", doc)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("Contextual Deep Linking", dev)
        self.assertIn("service_post_w99_contextual_deep_linking_app", dev)
        self.assertIn("service_post_w99_execution_return_app", dev)


if __name__ == "__main__":
    unittest.main()
