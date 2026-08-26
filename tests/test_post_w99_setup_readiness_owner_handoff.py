import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_campaign_attention_actionability_app as parent
from binario_marketing.service_post_w99_setup_readiness_owner_handoff_app import (
    AppRuntime,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


class SetupReadinessOwnerHandoffTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_campaign_attention_parent(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_http_bootstrap_appends_setup_handoff_after_campaign_attention(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Setup Handoff HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(
                    root + "/campaign-attention-actionability.js", timeout=5
                ).read().decode("utf-8")
                adapter = urlopen(
                    root + "/setup-readiness-owner-handoff.js", timeout=5
                ).read().decode("utf-8")
                self.assertIn("/setup-readiness-owner-handoff.js", parent_js)
                self.assertIn(
                    "data-post-w99-setup-readiness-owner-handoff",
                    parent_js,
                )
                self.assertIn(
                    "binario.marketing.setup-readiness-owner-handoff.v1",
                    adapter,
                )
                self.assertIn("PLAN DE HOY · SETUP OWNER HANDOFF", adapter)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_supported_readiness_kinds_are_exact_and_non_readiness_setup_is_not_intercepted(self):
        browser = (
            ROOT / "web" / "setup-readiness-owner-handoff.js"
        ).read_text(encoding="utf-8")
        for kind in (
            "setup_workspace",
            "setup_meta",
            "setup_facebook",
            "setup_instagram",
            "setup_ads",
            "setup_campaign",
            "setup_creative",
            "setup_crm",
        ):
            self.assertIn(f"'{kind}'", browser)
        for forbidden_kind in (
            "creative_unprofiled",
            "creative_campaign",
            "campaign_media",
            "paid_draft",
        ):
            self.assertNotIn(f"'{forbidden_kind}'", browser)
        self.assertIn("row?.source).toUpperCase()==='SETUP'", browser)

    def test_meta_handoff_uses_existing_controls_and_prerequisites_only(self):
        browser = (
            ROOT / "web" / "setup-readiness-owner-handoff.js"
        ).read_text(encoding="utf-8")
        for marker in (
            "Conectar Meta",
            "Actualizar activos",
            "Guardar asociaciones",
            "Página de Facebook / Instagram",
            "Cuenta publicitaria",
            "PREREQUISITE_CONTROL_RESOLVED",
        ):
            self.assertIn(marker, browser)
        self.assertIn("includes('@')", browser)
        self.assertIn("company?.[field]", browser)
        self.assertIn("metaStatus?.configured", browser)

    def test_workspace_campaign_and_crm_handoffs_use_canonical_owner_controls(self):
        browser = (
            ROOT / "web" / "setup-readiness-owner-handoff.js"
        ).read_text(encoding="utf-8")
        self.assertIn("Abrir Video Studio", browser)
        self.assertIn("Crear campaña", browser)
        self.assertIn("form.campaign-form", browser)
        self.assertIn("Guardar contacto", browser)
        self.assertIn("form.crm-form", browser)
        self.assertIn("crmState.tab='contacts'", browser)
        self.assertIn("campaignState.rows", browser)
        self.assertIn("crmState.contacts", browser)

    def test_creative_readiness_requires_real_human_media_choice_before_profile_save(self):
        browser = (
            ROOT / "web" / "setup-readiness-owner-handoff.js"
        ).read_text(encoding="utf-8")
        for marker in (
            "+ Importar",
            "Agregar a biblioteca",
            "Pipeline creativo",
            "HUMAN_SELECTION_REQUIRED",
            "humanMediaId",
            ".w49-item",
            "Guardar ficha creativa",
            "form.w49-form",
            "wave49CreativeState.selectedId",
            "wave49CreativeState.tab='pipeline'",
        ):
            self.assertIn(marker, browser)
        self.assertIn("button.addEventListener('click'", browser)
        self.assertNotIn("wave49CreativeState.selectedId=", browser)
        self.assertNotIn("select.value=", browser)

    def test_adapter_has_no_business_or_provider_execution_authority(self):
        service = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_setup_readiness_owner_handoff_app.py"
        ).read_text(encoding="utf-8")
        browser = (
            ROOT / "web" / "setup-readiness-owner-handoff.js"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "def do_POST",
            "def do_PATCH",
            "def do_PUT",
            "def do_DELETE",
        ):
            self.assertNotIn(forbidden, service)
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "opsApi(",
            "dispatchEvent",
            "requestSubmit",
            ".click(",
            "setInterval(",
            "sendBeacon",
        ):
            self.assertNotIn(forbidden, browser)
        self.assertIn("service_post_w99_campaign_attention_actionability_app", service)
        self.assertIn(
            'path == "/campaign-attention-actionability.js"',
            service,
        )

    def test_stale_loading_and_cardinality_states_fail_closed(self):
        browser = (
            ROOT / "web" / "setup-readiness-owner-handoff.js"
        ).read_text(encoding="utf-8")
        for marker in (
            "STALE_ACTION_CONTEXT",
            "OWNER_LOADING",
            "CONTROL_NOT_AVAILABLE",
            "CONTROL_AMBIGUOUS",
            "OWNER_NOT_OPEN",
            "ACTION_CONTEXT_NOT_RESOLVED",
        ):
            self.assertIn(marker, browser)
        self.assertIn("matches.length!==1", browser)
        self.assertIn("submits.length!==1", browser)
        self.assertIn("forms.length!==1", browser)

    def test_docs_and_dev_entrypoint_preserve_w99_boundary(self):
        docs = (
            ROOT / "docs" / "POST_W99_SETUP_READINESS_OWNER_HANDOFF.md"
        ).read_text(encoding="utf-8")
        entry_docs = (
            ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md"
        ).read_text(encoding="utf-8")
        entrypoint = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No es W100", docs)
        self.assertIn("Setup Readiness Owner Handoff", entry_docs)
        self.assertIn("service_post_w99_setup_readiness_owner_handoff_app", entry_docs)
        self.assertIn(
            "from .service_post_w99_setup_readiness_owner_handoff_app import",
            entrypoint,
        )
        self.assertIn(
            "service_post_w99_campaign_attention_actionability_app",
            entrypoint,
        )


if __name__ == "__main__":
    unittest.main()
