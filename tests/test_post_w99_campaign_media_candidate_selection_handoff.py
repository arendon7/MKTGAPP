import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_campaign_execution_owner_cardinality_hardening_app as cardinality_base
from binario_marketing.service_post_w99_campaign_media_candidate_selection_handoff_app import (
    AppRuntime,
    create_server,
)

ROOT = Path(__file__).resolve().parents[1]


class PostW99CampaignMediaCandidateSelectionHandoffTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()

    def _runtime_with_two_drafts(self, tmp):
        runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
        company = runtime.create_company({"name": "MEDIA Selection Co"})
        campaign = runtime.campaigns.create(company["id"], {
            "name": "Dos creativos", "objective": "LEADS", "status": "IN_PROGRESS",
            "channels": ["facebook_page"],
        })
        for index in range(2):
            payload = b"\x89PNG\r\n\x1a\nmedia-selector" + bytes([index])
            media = runtime.upload_company_media(
                company["id"], f"draft-{index}.png", "image", io.BytesIO(payload), len(payload)
            )
            runtime.upsert_company_creative(company["id"], media["id"], {
                "title": f"Draft {index}", "stage": "DRAFT", "purpose": "LEADS",
                "campaign_id": campaign.id, "channels": ["facebook_page"],
            })
        return runtime, company, campaign

    def test_terminal_inherits_cardinality_hardening(self):
        self.assertTrue(issubclass(AppRuntime, cardinality_base.AppRuntime))

    def test_backend_truth_remains_ambiguous_media_and_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, company, campaign = self._runtime_with_two_drafts(tmp)
            try:
                context = runtime.campaign_execution_owner_context(company["id"], campaign.id)
                self.assertEqual(context["execution"]["next_action"]["code"], "FINISH_CREATIVE")
                self.assertEqual(context["resolution"]["state"], "AMBIGUOUS_TARGET")
                self.assertEqual(context["resolution"]["target_kind"], "MEDIA")
                self.assertEqual(context["resolution"]["candidate_count"], 2)
                self.assertIsNone(context["resolution"]["target_id"])
                rows = [row for row in runtime.action_center(company["id"])["queue"] if row.get("kind") == "finish_creative"]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["owner_resolution"]["state"], "AMBIGUOUS_TARGET")
                self.assertEqual(rows[0]["owner_resolution"]["target_kind"], "MEDIA")
            finally:
                self._shutdown_runtime(runtime)

    def test_media_selector_is_separate_from_historical_publication_paid_selector(self):
        historical = (ROOT / "web" / "campaign-execution-candidate-selector.js").read_text(encoding="utf-8")
        current = (ROOT / "web" / "campaign-media-candidate-selection-handoff.js").read_text(encoding="utf-8")
        self.assertIn("['PUBLICATION','PAID_DRAFT']", historical)
        self.assertNotIn("['PUBLICATION','PAID_DRAFT','MEDIA']", historical)
        self.assertIn("target_kind).toUpperCase(),state", current)
        self.assertIn("kind!=='MEDIA'", current)
        self.assertIn("['FINISH_CREATIVE','PREPARE_DISTRIBUTION']", current)

    def test_browser_contract_requires_human_click_and_ephemeral_navigation_resolution(self):
        source = (ROOT / "web" / "campaign-media-candidate-selection-handoff.js").read_text(encoding="utf-8")
        for required in (
            "HUMAN_CLICK", "persisted:false", "priority_inferred:false", "recommendation_made:false",
            "navigation_only:true", "source_owner_resolution", "source_resolution_state:'AMBIGUOUS_TARGET'",
            "action.media_id=targetId", "Elegir este creativo", "executionReturnForget", "executionReturnCapture",
            "La empresa cambió", "candidate_count", "unique.size!==ids.length",
        ):
            self.assertIn(required, source)
        self.assertNotIn(".sort(", source)
        for forbidden in (
            "opsApi(", "fetch(", ".click(", "dispatchEvent(", "setInterval(", "sendBeacon(",
            "localStorage", "sessionStorage", "method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, source)

    def test_selection_copy_preserves_ambiguous_source_and_marks_navigation_only(self):
        source = (ROOT / "web" / "campaign-media-candidate-selection-handoff.js").read_text(encoding="utf-8")
        self.assertIn("const sourceResolution={...(item?.owner_resolution||{})}", source)
        self.assertIn("source_owner_resolution:sourceResolution", source)
        self.assertIn("state:'EXACT_TARGET'", source)
        self.assertIn("navigation_only:true", source)
        self.assertIn("no cambia la resolución backend", source)

    def test_http_bootstrap_is_after_cardinality_and_parent_runtime_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, company, campaign = self._runtime_with_two_drafts(tmp)
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent = urlopen(root + "/campaign-execution-owner-cardinality-hardening.js", timeout=5).read().decode("utf-8")
                child = urlopen(root + "/campaign-media-candidate-selection-handoff.js", timeout=5).read().decode("utf-8")
                context = json.loads(urlopen(
                    root + f"/api/companies/{company['id']}/campaigns/{campaign.id}/execution-owner-context", timeout=5
                ).read().decode("utf-8"))
                self.assertIn("/campaign-media-candidate-selection-handoff.js", parent)
                self.assertIn("data-post-w99-campaign-media-candidate-selection-handoff", parent)
                self.assertIn("Elegir este creativo", child)
                self.assertEqual(context["resolution"]["state"], "AMBIGUOUS_TARGET")
                self.assertTrue(callable(runtime.campaign_coordinate_recovery_guidance))
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close(); self._shutdown_runtime(runtime)

    def test_refresh_pagehide_escape_and_company_scope_fail_safe(self):
        source = (ROOT / "web" / "campaign-media-candidate-selection-handoff.js").read_text(encoding="utf-8")
        for required in ("marketing-ops-refreshed", "pagehide", "event.key==='Escape'", "company.id", "active.companyId"):
            self.assertIn(required, source)

    def test_service_and_docs_preserve_frozen_release_boundary(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_media_candidate_selection_handoff_app.py").read_text(encoding="utf-8")
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_MEDIA_CANDIDATE_SELECTION_HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_campaign_execution_owner_cardinality_hardening_app", service)
        self.assertIn("service_post_w99_campaign_media_candidate_selection_handoff_app", entrypoint)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No constituye W100", doc)
        self.assertIn("physical UAT", doc)


if __name__ == "__main__":
    unittest.main()
