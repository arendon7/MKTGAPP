import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_contextual_control_handoff_app import AppRuntime, create_server
from binario_marketing.service_post_w99_opportunity_followup_control_app import (
    AppRuntime as OpportunityRuntime,
    create_server as create_opportunity_server,
)

ROOT = Path(__file__).resolve().parents[1]


class PostW99ContextualControlHandoffTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_service_is_static_only_and_inherits_portfolio_cadence(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_contextual_control_handoff_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_cadence_app as base", service)
        self.assertIn("/contextual-control-handoff.js", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)

    def test_browser_adapter_has_no_transport_or_synthetic_execution(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        for forbidden in (
            "opsApi(",
            "fetch(",
            "XMLHttpRequest",
            "method:'POST'",
            "method:'PATCH'",
            "method:'PUT'",
            "method:'DELETE'",
            ".click(",
            "dispatchEvent(",
            "setInterval(",
            "sendBeacon(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("queueMicrotask", source)
        self.assertIn("CONTROL_RESOLVED", source)
        self.assertIn("OWNER_CONTROL_GAP", source)
        self.assertIn("CONTROL_AMBIGUOUS", source)
        self.assertIn("TARGET_NOT_EXACT", source)
        self.assertIn("ACTION_CONTEXT_NOT_RESOLVED", source)

    def test_control_mapping_is_explicit_and_base_pipeline_fallback_is_not_stage_substitution(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        for value in (
            "crm_overdue",
            "crm_today",
            "crm_unscheduled",
            "publication_failed",
            "publication_overdue",
            "publication_today",
            "lead_conflict",
            "lead_matched",
            "lead_new",
            "lead_unidentified",
            "needs_opportunity",
            "needs_followup",
            "define_channels",
            "CAMPAIGN_EXECUTION",
            "CAMPAIGN_INTELLIGENCE",
            "optional_ai",
            "MEDIA",
        ):
            self.assertIn(value, source)
        self.assertIn("kind.startsWith('pipeline_')", source)
        self.assertIn("No se sustituye por el selector de etapa", source)
        self.assertNotIn("querySelector('select')", source)

    def test_control_groups_require_one_available_canonical_submit(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        self.assertIn("function controlHandoffSingleGroup", source)
        self.assertIn("controls.length===0", source)
        self.assertIn("controls.length>1", source)
        self.assertIn("controls[0].disabled", source)
        self.assertIn("El submit canónico está deshabilitado en el owner", source)
        for label in ("Resolver conflicto exacto", "Crear oportunidad", "Programar seguimiento", "Guardar cambios"):
            self.assertIn(label, source)

    def test_unscheduled_activity_never_substitutes_complete_or_cross_owner_reschedule(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='ACTIVITY'&&kind==='crm_unscheduled'", source)
        self.assertIn("esa card no expone Reprogramar", source)
        self.assertIn("no se sustituye por Completar ni se cruza a otro owner", source)
        reschedule = (ROOT / "web" / "followup-reschedule.js").read_text(encoding="utf-8")
        self.assertIn("dailyActionButtons", reschedule)
        self.assertIn("Reprogramar", reschedule)
        crm = (ROOT / "web" / "crm.js").read_text(encoding="utf-8")
        self.assertIn("crmRenderFollowups", crm)
        self.assertIn("opsEl('button','','Completar')", crm)

    def test_define_channels_requires_exact_selected_campaign_form(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='CAMPAIGN'&&kind==='define_channels'", source)
        self.assertIn("campaignState.selectedId", source)
        self.assertIn("String(deep.target_id||'')", source)
        self.assertIn("#marketing-ops-view form.campaign-form", source)
        self.assertIn("DEFINE_CAMPAIGN_CHANNELS", source)
        self.assertIn("Seleccionar canales + guardar cambios", source)
        campaigns = (ROOT / "web" / "campaigns.js").read_text(encoding="utf-8")
        self.assertIn("Guardar cambios", campaigns)
        self.assertIn("Cambiar una campaña a “En curso” sólo organiza el trabajo", campaigns)

    def test_optional_ai_maps_to_explicit_confirmed_ai_not_self_navigation(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='CAMPAIGN_INTELLIGENCE'&&kind==='optional_ai'", source)
        self.assertIn("REQUEST_OPTIONAL_AI_ANALYSIS", source)
        self.assertIn("Analizar con IA", source)
        self.assertIn("confirmación", source)
        self.assertIn("No se usa el botón Ir como sustituto", source)
        self.assertNotIn("OPEN_INTELLIGENCE_NEXT_OWNER", source)
        intelligence = (ROOT / "web" / "results-intelligence.js").read_text(encoding="utf-8")
        self.assertIn("function wave65Analyze", intelligence)
        self.assertIn("if(!confirm(", intelligence)
        self.assertIn("Analizar con IA", intelligence)

    def test_media_action_never_promotes_delete_or_channel_specific_reel(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='MEDIA'", source)
        self.assertIn("Usar como Reel y Eliminar no equivalen", source)
        self.assertIn("No se promueve un control destructivo", source)
        self.assertNotIn("control_key:'DELETE", source)
        media = (ROOT / "web" / "company-content.js").read_text(encoding="utf-8")
        self.assertIn("Usar como Reel", media)
        self.assertIn("Eliminar", media)

    def test_publication_mapping_requires_exact_selected_editorial_panel(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        self.assertIn("MANAGE_PUBLICATION_PANEL", source)
        self.assertIn("editorialState.selectedId", source)
        self.assertIn("String(deep.target_id||'')", source)
        self.assertIn("#marketing-ops-view .editorial-panel", source)
        self.assertIn("Editar, reprogramar o cancelar publicación", source)
        self.assertNotIn("meta('MANAGE_PUBLICATION','Gestionar publicación'", source)

    def test_opportunity_extension_precedes_base_pipeline_fallback_and_preserves_ambiguity(self):
        owner = (ROOT / "web" / "opportunity-followup-control.js").read_text(encoding="utf-8")
        self.assertIn("const opportunityControlBaseResolveControl=globalThis.controlHandoffResolveControl", owner)
        self.assertIn("globalThis.controlHandoffResolveControl=function", owner)
        self.assertIn("targetKind==='OPPORTUNITY'&&kind.startsWith('pipeline_')", owner)
        self.assertIn("return opportunityControlBaseResolveControl.apply(this,arguments)", owner)
        for marker in (
            "pipeline_overdue_next_action",
            "pipeline_unscheduled_next_action",
            "pipeline_no_followup",
            "pipeline_due_soon",
            "pipeline_overdue_followup",
            "pipeline_unscheduled_followup",
            "OPEN_OPPORTUNITY_FOLLOWUP_CONTROL",
            "EDIT_OPPORTUNITY_NEXT_ACTION",
            "CHOOSE_OPPORTUNITY_NEXT_STEP",
        ):
            self.assertIn(marker, owner)
        self.assertIn("no crea una actividad sustituta", owner)
        self.assertIn("No se adivina cuál control corresponde", owner)

    def test_runtime_preserves_cadence_evidence_and_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Control Handoff"})
                company_id = company["id"]
                self.assertEqual(runtime.today_execution(company_id)["schema"], "binario.marketing.today-execution.v1")
                self.assertEqual(runtime.evidence_observability(company_id)["schema"], "binario.marketing.evidence-observability.v1")
                self.assertEqual(runtime.portfolio_cadence()["schema"], "binario.marketing.portfolio-cadence.v2")
            finally:
                self._shutdown_runtime(runtime)

    def test_terminal_browser_bootstrap_appends_opportunity_owner_after_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = OpportunityRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Control HTTP"})
            server = create_opportunity_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                evidence = urlopen(root + "/evidence-observability.js", timeout=5).read().decode("utf-8")
                cadence = urlopen(root + "/portfolio-cadence.js", timeout=5).read().decode("utf-8")
                handoff = urlopen(root + "/contextual-control-handoff.js", timeout=5).read().decode("utf-8")
                opportunity = urlopen(root + "/opportunity-followup-control.js", timeout=5).read().decode("utf-8")
                self.assertIn("/portfolio-cadence.js", evidence)
                self.assertIn("/contextual-control-handoff.js", cadence)
                self.assertIn("/opportunity-followup-control.js", handoff)
                self.assertIn("POST_W99_OPPORTUNITY_FOLLOWUP_CONTROL_SCHEMA", opportunity)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_docs_preserve_fail_closed_opportunity_extension_and_frozen_release_contracts(self):
        docs = (ROOT / "docs" / "POST_W99_CONTEXTUAL_CONTROL_HANDOFF.md").read_text(encoding="utf-8")
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("OWNER_CONTROL_GAP", docs)
        self.assertIn("CONTROL_AMBIGUOUS", docs)
        self.assertIn("nunca dispara `.click()`", docs)
        self.assertIn("editorialState.selectedId", docs)
        self.assertIn("panel editorial exacto", docs)
        self.assertIn("crm_unscheduled", docs)
        self.assertIn("DEFINE_CHANNELS", docs)
        self.assertIn("OPTIONAL_AI", docs)
        self.assertIn("MEDIA", docs)
        self.assertIn("Opportunity Follow-up Control extension", docs)
        self.assertIn("pipeline_overdue_next_action", docs)
        self.assertIn("pipeline_overdue_followup", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)
        self.assertIn("Contextual Control Handoff", dev)
        self.assertIn("Opportunity Follow-up Control", dev)
        self.assertIn("service_post_w99_opportunity_followup_control_app", dev)
        self.assertIn(
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control",
            dev,
        )


if __name__ == "__main__":
    unittest.main()
