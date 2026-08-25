import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_contextual_action_handoff_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class PostW99ContextualActionHandoffTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_runtime_preserves_portfolio_cadence_evidence_and_prior_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Handoff Integrated"})
                company_id = company["id"]
                self.assertEqual(runtime.action_center(company_id)["schema"], "binario.marketing.action-center.v1")
                self.assertEqual(runtime.today_execution(company_id)["schema"], "binario.marketing.today-execution.v1")
                self.assertEqual(runtime.evidence_observability(company_id)["schema"], "binario.marketing.evidence-observability.v1")
                self.assertEqual(runtime.portfolio_cadence()["schema"], "binario.marketing.portfolio-cadence.v2")
            finally:
                self._shutdown_runtime(runtime)

    def test_browser_bootstrap_is_appended_after_portfolio_cadence(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Handoff HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                today = urlopen(root + "/today-execution.js", timeout=5).read().decode("utf-8")
                self.assertIn("/execution-return.js", today)
                execution = urlopen(root + "/execution-return.js", timeout=5).read().decode("utf-8")
                self.assertIn("/contextual-deep-linking.js", execution)
                contextual = urlopen(root + "/contextual-deep-linking.js", timeout=5).read().decode("utf-8")
                self.assertIn("/evidence-observability.js", contextual)
                evidence = urlopen(root + "/evidence-observability.js", timeout=5).read().decode("utf-8")
                self.assertIn("postW99EvidenceState", evidence)
                self.assertIn("/portfolio-cadence.js", evidence)
                cadence = urlopen(root + "/portfolio-cadence.js", timeout=5).read().decode("utf-8")
                self.assertIn("postW99CadenceState", cadence)
                self.assertIn("/contextual-action-handoff.js", cadence)
                handoff = urlopen(root + "/contextual-action-handoff.js", timeout=5).read().decode("utf-8")
                self.assertIn("POST_W99_CONTEXTUAL_ACTION_HANDOFF_SCHEMA", handoff)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_portfolio_cadence_endpoint_survives_terminal_composition(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Cadence Through Handoff"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                payload = json.loads(urlopen(root + "/api/portfolio-cadence", timeout=5).read())
                self.assertEqual(payload["schema"], "binario.marketing.portfolio-cadence.v2")
                self.assertTrue(payload["contracts"]["exact_parent_queue_order_preserved"])
                self.assertTrue(payload["contracts"]["timing_never_reprioritizes"])
                self.assertFalse(payload["safety"]["business_mutation_performed"])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_activity_mapping_uses_existing_complete_and_fails_closed_for_unscheduled(self):
        source = (ROOT / "web" / "contextual-action-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='ACTIVITY'", source)
        self.assertIn("kind==='crm_unscheduled'", source)
        self.assertIn("exact:['Reprogramar']", source)
        self.assertIn("exact:['Completar']", source)
        self.assertIn("“Completar” no se usa como sustituto", source)
        self.assertIn("La ausencia del botón no significa que la tarea esté completada", source)

    def test_pipeline_attention_never_substitutes_stage_change_for_followup(self):
        source = (ROOT / "web" / "contextual-action-handoff.js").read_text(encoding="utf-8")
        self.assertIn("reason.startsWith('PIPELINE_')", source)
        self.assertIn("El selector de etapa visible en la oportunidad no resuelve ese motivo", source)
        self.assertIn("NO_ACTION_MAPPING", source)

    def test_lead_handoff_publication_and_campaign_controls_are_owner_controls(self):
        source = (ROOT / "web" / "contextual-action-handoff.js").read_text(encoding="utf-8")
        for marker in (
            "Resolver conflicto exacto",
            "Crear contacto",
            "Vincular · ",
            "Crear oportunidad",
            "Programar seguimiento",
            "Guardar nueva versión",
            "Guardar cambios",
        ):
            self.assertIn(marker, source)
        self.assertIn("target.querySelector('form.w61-form')", source)
        self.assertIn("document.querySelector('.editorial-panel')", source)
        self.assertIn("document.querySelector('.campaign-form')", source)

    def test_execution_and_intelligence_handoff_remain_navigation_or_explicit_ai(self):
        source = (ROOT / "web" / "contextual-action-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='CAMPAIGN_EXECUTION'", source)
        self.assertIn("mode:'NAVIGATION'", source)
        self.assertIn("reason==='CAMPAIGN_OPTIONAL_AI'", source)
        self.assertIn("mode:'EXPLICIT_AI_REQUEST'", source)
        self.assertIn("confirmation:true", source)

    def test_media_delete_is_never_promoted_as_default_action(self):
        source = (ROOT / "web" / "contextual-action-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='MEDIA'", source)
        self.assertIn("“Eliminar” nunca se recomienda", source)
        self.assertNotIn("exact:['Eliminar']", source)

    def test_handoff_layer_owns_no_business_transport_or_synthetic_execution(self):
        source = (ROOT / "web" / "contextual-action-handoff.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_contextual_action_handoff_app.py").read_text(encoding="utf-8")
        self.assertNotIn("opsApi(", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn(".click(", source)
        self.assertNotIn("do_POST", service)
        self.assertNotIn("do_PATCH", service)
        self.assertNotIn("do_PUT", service)
        self.assertNotIn("do_DELETE", service)
        self.assertIn("service_post_w99_portfolio_cadence_app as base", service)

    def test_dev_entrypoint_and_docs_preserve_cadence_and_release_boundaries(self):
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "POST_W99_CONTEXTUAL_ACTION_HANDOFF.md").read_text(encoding="utf-8")
        dev_docs = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_contextual_action_handoff_app", entrypoint)
        self.assertIn("service_post_w99_portfolio_cadence_app", entrypoint)
        self.assertIn("service_post_w99_evidence_observability_integrated_app", entrypoint)
        self.assertIn("control_absence_is_not_completion", docs)
        self.assertIn("portfolio_cadence_never_reprioritizes", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)
        self.assertIn("Evidence Observability → Portfolio Cadence → Contextual Action Handoff", dev_docs)
        self.assertIn("service_post_w99_portfolio_cadence_app", dev_docs)
        self.assertIn("service_post_w99_evidence_observability_integrated_app", dev_docs)


if __name__ == "__main__":
    unittest.main()
