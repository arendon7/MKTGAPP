import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_campaign_execution_candidate_selector_app import AppRuntime, create_server
from binario_marketing.service_post_w99_campaign_execution_owner_relay_app import _owner_resolution, _rewrite_action_from_resolution
from binario_marketing.service_post_w99_today_execution_app import compose_today_execution

ROOT = Path(__file__).resolve().parents[1]


class PostW99CampaignExecutionCandidateSelectorTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_ambiguous_candidates_survive_action_center_rewrite_and_today_deepcopy(self):
        row = {
            "id": "action-ambiguous",
            "kind": "fix_execution",
            "source": "CAMPAIGN",
            "urgency": "CRITICAL",
            "blocking": True,
            "rank": 1,
            "title": "Corregir publicación",
            "detail": "Dos publicaciones fallaron",
            "reason": {"code": "FIX_EXECUTION", "explanation": "Wave 64"},
            "action": {"view": "execution", "campaign_id": "campaign-1", "label": "Resolver ejecución"},
        }
        resolution = _owner_resolution(
            campaign_id="campaign-1",
            next_action={"code": "FIX_PUBLICATION", "view": "calendar"},
            linked_creatives=[],
            publications=[
                {"id": "pub-a", "status": "FAILED", "channel": "instagram"},
                {"id": "pub-b", "status": "FAILED", "channel": "facebook_page"},
            ],
            linked_paid=[],
        )
        self.assertEqual(resolution["state"], "AMBIGUOUS_TARGET")
        routed = _rewrite_action_from_resolution(row, resolution)
        self.assertEqual(routed["action"], row["action"])
        self.assertEqual([candidate["id"] for candidate in routed["owner_resolution"]["candidates"]], ["pub-a", "pub-b"])
        today = compose_today_execution(
            company={"id": "company-1", "name": "Company"},
            action_center={"queue": [routed]},
            cockpit={"status": {}, "commercial": {}, "campaigns": {}},
        )
        selected = today["plan"][0]
        self.assertEqual(selected["id"], "action-ambiguous")
        self.assertEqual(selected["owner_resolution"]["state"], "AMBIGUOUS_TARGET")
        self.assertEqual([candidate["id"] for candidate in selected["owner_resolution"]["candidates"]], ["pub-a", "pub-b"])
        self.assertIsNot(selected, routed)

    def test_terminal_only_adds_selector_static_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                relay = urlopen(root + "/campaign-execution-owner-relay.js", timeout=5).read().decode("utf-8")
                selector = urlopen(root + "/campaign-execution-candidate-selector.js", timeout=5).read().decode("utf-8")
                self.assertIn("/campaign-execution-candidate-selector.js", relay)
                self.assertIn("AMBIGUOUS_TARGET", selector)
                self.assertIn("HUMAN_CLICK", selector)
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close(); self._shutdown_runtime(runtime)

    def test_selector_validates_cardinality_identity_and_company_before_navigation(self):
        source = (ROOT / "web" / "campaign-execution-candidate-selector.js").read_text(encoding="utf-8")
        for required in (
            "AMBIGUOUS_TARGET",
            "candidate_count",
            "new Set(ids)",
            "unique.size!==ids.length",
            "candidateSelectorSupportedTarget",
            "candidateSelectorCompany",
            "La empresa cambió",
            "explicit_owner_selection",
            "source_resolution_state:'AMBIGUOUS_TARGET'",
            "selected_by:'HUMAN_CLICK'",
            "persisted:false",
            "Los candidatos conservan el orden",
        ):
            self.assertIn(required, source)

    def test_today_provisional_return_is_cleared_and_recaptured_only_after_choice(self):
        source = (ROOT / "web" / "campaign-execution-candidate-selector.js").read_text(encoding="utf-8")
        self.assertIn("candidateSelectorFromToday", source)
        self.assertIn("executionReturnForget()", source)
        self.assertIn("executionReturnCapture(exact)", source)
        self.assertIn("Cancelar sin abrir", source)
        self.assertLess(source.index("executionReturnCapture(exact)"), source.index("candidateSelectorBaseOpen(exact)"))

    def test_selector_has_no_business_or_provider_io_and_no_automatic_control_execution(self):
        source = (ROOT / "web" / "campaign-execution-candidate-selector.js").read_text(encoding="utf-8")
        for forbidden in (
            "opsApi(",
            "fetch(",
            "XMLHttpRequest",
            ".click(",
            "dispatchEvent(",
            "setInterval(",
            "sendBeacon(",
            "method:'POST'",
            "method:'PATCH'",
            "method:'PUT'",
            "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("choose.addEventListener('click'", source)
        self.assertIn("window.addEventListener('marketing-ops-refreshed',candidateSelectorClose)", source)

    def test_service_adds_no_business_endpoint_or_write_handler(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_execution_candidate_selector_app.py").read_text(encoding="utf-8")
        self.assertIn("campaign-execution-candidate-selector.js", source)
        self.assertNotIn("/api/companies", source)
        self.assertNotIn("def do_POST", source)
        self.assertNotIn("def do_PATCH", source)
        self.assertNotIn("def do_PUT", source)
        self.assertNotIn("def do_DELETE", source)

    def test_docs_preserve_authority_and_frozen_w99_boundary(self):
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_EXECUTION_CANDIDATE_SELECTOR.md").read_text(encoding="utf-8")
        entry = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("AMBIGUOUS_TARGET", doc)
        self.assertIn("HUMAN_CLICK", doc)
        self.assertIn("Action Center conserva prioridad y orden", doc)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        expected = "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector"
        self.assertIn(expected, entry)
        self.assertIn("No debe interpretarse como W100", entry)


if __name__ == "__main__":
    unittest.main()
