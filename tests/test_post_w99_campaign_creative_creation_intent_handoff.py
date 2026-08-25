import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_campaign_creative_creation_intent_handoff_app import AppRuntime, create_server
from binario_marketing.service_post_w99_campaign_execution_owner_relay_app import _owner_resolution, _rewrite_action_from_resolution
from binario_marketing.service_post_w99_today_execution_app import compose_today_execution

ROOT = Path(__file__).resolve().parents[1]


class PostW99CampaignCreativeCreationIntentHandoffTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_create_creative_owner_only_preserves_campaign_identity_into_today(self):
        row = {
            "id": "campaign:create_creative:campaign-1",
            "kind": "create_creative",
            "source": "CAMPAIGN",
            "urgency": "MEDIUM",
            "blocking": False,
            "rank": 50,
            "title": "Crear o vincular creativo · Campaign",
            "detail": "Sin piezas vinculadas",
            "reason": {"code": "CAMPAIGN_CREATE_CREATIVE", "explanation": "Wave 64"},
            "action": {"view": "content", "campaign_id": "campaign-1", "label": "Crear o vincular creativo"},
        }
        resolution = _owner_resolution(
            campaign_id="campaign-1",
            next_action={"code": "CREATE_CREATIVE", "view": "content"},
            linked_creatives=[],
            publications=[],
            linked_paid=[],
        )
        self.assertEqual(resolution["state"], "OWNER_ONLY")
        self.assertEqual(resolution["source_code"], "CREATE_CREATIVE")
        self.assertIsNone(resolution["target_kind"])
        self.assertIsNone(resolution["target_id"])
        self.assertEqual(resolution["candidate_count"], 0)
        self.assertEqual(resolution["candidates"], [])
        routed = _rewrite_action_from_resolution(row, resolution)
        self.assertEqual(routed["action"], row["action"])
        self.assertEqual(routed["action"]["campaign_id"], "campaign-1")
        today = compose_today_execution(
            company={"id": "company-1", "name": "Company"},
            action_center={"queue": [routed]},
            cockpit={"status": {}, "commercial": {}, "campaigns": {}},
        )
        selected = today["plan"][0]
        self.assertEqual(selected["kind"], "create_creative")
        self.assertEqual(selected["action"]["campaign_id"], "campaign-1")
        self.assertEqual(selected["owner_resolution"]["state"], "OWNER_ONLY")

    def test_terminal_only_adds_creation_intent_static_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                selector = urlopen(root + "/campaign-execution-candidate-selector.js", timeout=5).read().decode("utf-8")
                intent = urlopen(root + "/campaign-creative-creation-intent-handoff.js", timeout=5).read().decode("utf-8")
                self.assertIn("/campaign-creative-creation-intent-handoff.js", selector)
                self.assertIn("campaign-creative-creation-intent.v1", intent)
                self.assertIn("CREATE_CREATIVE", intent)
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close(); self._shutdown_runtime(runtime)

    def test_adapter_requires_exact_create_creative_owner_only_contract(self):
        source = (ROOT / "web" / "campaign-creative-creation-intent-handoff.js").read_text(encoding="utf-8")
        for required in (
            "creativeIntentActionKind(item)==='create_creative'",
            "resolution.state)==='OWNER_ONLY'",
            "resolution.source_code).toUpperCase()==='CREATE_CREATIVE'",
            "resolution.owner_view)==='content'",
            "!creativeIntentText(resolution.target_kind)",
            "!creativeIntentText(resolution.target_id)",
            "Number(resolution.candidate_count)===0",
            "candidates.length===0",
            "action.view)==='content'",
            "action.campaign_id",
        ):
            self.assertIn(required, source)
        self.assertNotIn("COORDINATE", source)

    def test_existing_piece_requires_human_item_click_not_default_w49_selection(self):
        source = (ROOT / "web" / "campaign-creative-creation-intent-handoff.js").read_text(encoding="utf-8")
        self.assertIn("creativeIntentBaseItemCard", source)
        self.assertIn("node.addEventListener('click'", source)
        self.assertIn("selection_source='EXISTING_ITEM_HUMAN_CLICK'", source)
        self.assertIn("Ninguna pieza actualmente seleccionada por defecto", source)
        self.assertNotIn("active.media_id=wave49CreativeState.selectedId", source)

    def test_import_uses_exact_upload_return_and_requires_second_human_continue(self):
        source = (ROOT / "web" / "campaign-creative-creation-intent-handoff.js").read_text(encoding="utf-8")
        for required in (
            "creativeIntentBaseUpload",
            "result?.id",
            "active.imported_media_id=id",
            "import_source='CANONICAL_UPLOAD_RETURN'",
            "Continuar con este archivo",
            "creativeIntentContinueImported",
            "selection_source='IMPORTED_MEDIA_HUMAN_CONTINUE'",
            "wave49CreativeState.selectedId=id",
            "wave49CreativeState.context=null",
        ):
            self.assertIn(required, source)
        self.assertNotIn("original_name", source)
        self.assertNotIn("sha256", source)

    def test_campaign_select_is_observed_but_never_auto_assigned_or_submitted(self):
        source = (ROOT / "web" / "campaign-creative-creation-intent-handoff.js").read_text(encoding="utf-8")
        self.assertIn("String(select.value||'')===String(active.campaign_id||'')", source)
        self.assertIn("select.addEventListener('change'", source)
        self.assertIn("Guardar ficha creativa", source)
        self.assertIn("El handoff no asigna select.value", source)
        self.assertNotIn("select.value=", source)
        self.assertNotIn("wave49SaveCreative(", source)
        self.assertNotIn("requestSubmit(", source)
        self.assertNotIn(".submit(", source)

    def test_adapter_has_no_own_business_or_provider_io_and_no_automatic_click(self):
        source = (ROOT / "web" / "campaign-creative-creation-intent-handoff.js").read_text(encoding="utf-8")
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
        self.assertIn("persisted:false", source)
        self.assertIn("Vincular pieza existente", source)
        self.assertIn("Importar archivo", source)

    def test_service_adds_no_business_endpoint_or_write_handler(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_creative_creation_intent_handoff_app.py").read_text(encoding="utf-8")
        self.assertIn("campaign-creative-creation-intent-handoff.js", source)
        self.assertNotIn("/api/companies", source)
        self.assertNotIn("def do_POST", source)
        self.assertNotIn("def do_PATCH", source)
        self.assertNotIn("def do_PUT", source)
        self.assertNotIn("def do_DELETE", source)

    def test_docs_preserve_authority_split_and_frozen_w99_boundary(self):
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_CREATIVE_CREATION_INTENT_HANDOFF.md").read_text(encoding="utf-8")
        entry = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        for required in (
            "CREATE_CREATIVE",
            "OWNER_ONLY",
            "COORDINATE",
            "no cambia `select.value`",
            "Continuar con este archivo",
            "Video Studio is outside v1",
            "Action Center conserva prioridad y orden",
            "main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",
        ):
            self.assertIn(required, doc)
        expected = "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff"
        self.assertIn(expected, entry)
        self.assertIn("No debe interpretarse como W100", entry)


if __name__ == "__main__":
    unittest.main()
