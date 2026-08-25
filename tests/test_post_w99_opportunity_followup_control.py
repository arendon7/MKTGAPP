import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_opportunity_followup_control_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class PostW99OpportunityFollowupControlTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_control_handoff_without_new_business_route(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_opportunity_followup_control_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_contextual_control_handoff_app as base", source)
        self.assertIn("/opportunity-followup-control.js", source)
        self.assertIn("already-existing CRM opportunity PATCH and activity POST routes", source)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, source)

    def test_browser_mutations_are_explicit_and_semantically_separate(self):
        source = (ROOT / "web" / "opportunity-followup-control.js").read_text(encoding="utf-8")
        self.assertIn("crm-opportunity-next-action-form", source)
        self.assertIn("crm-opportunity-followup-form", source)
        self.assertIn("method:'PATCH'", source)
        self.assertIn("/opportunities/${encodeURIComponent(row.id)}", source)
        self.assertIn("body:{next_action:nextAction,next_action_at:nextActionAt}", source)
        self.assertIn("method:'POST'", source)
        self.assertIn("/activities`,{method:'POST'", source)
        self.assertIn("opportunity_id:row.id", source)
        self.assertGreaterEqual(source.count("addEventListener('submit'"), 2)
        for forbidden in (".click(", "dispatchEvent(", "setInterval(", "sendBeacon(", "XMLHttpRequest"):
            self.assertNotIn(forbidden, source)

    def test_wave63_exact_target_bridge_replaces_legacy_only_assumption(self):
        source = (ROOT / "web" / "opportunity-followup-control.js").read_text(encoding="utf-8")
        for required in (
            ".w63-board .w63-lane",
            ".w63-card",
            "wave63State.attentionOnly",
            "dataset.deepOpportunityId",
            "contextualDeepLinkAnnotateCrm",
            "contextualDeepLinkOwnerReady",
            "wave63State.data",
            "wave63Draw",
        ):
            self.assertIn(required, source)
        self.assertIn("matches.length===1", source)
        self.assertNotIn("includes(row.title)", source)
        self.assertNotIn("textContent.includes", source)

    def test_pipeline_control_mapping_is_fail_closed_by_owner_semantics(self):
        source = (ROOT / "web" / "opportunity-followup-control.js").read_text(encoding="utf-8")
        for required in (
            "pipeline_overdue_next_action",
            "pipeline_unscheduled_next_action",
            "pipeline_no_followup",
            "pipeline_due_soon",
            "pipeline_overdue_followup",
            "pipeline_unscheduled_followup",
            "EDIT_OPPORTUNITY_NEXT_ACTION",
            "CHOOSE_OPPORTUNITY_NEXT_STEP",
            "OPEN_OPPORTUNITY_FOLLOWUP_CONTROL",
        ):
            self.assertIn(required, source)
        self.assertIn("no crea una actividad sustituta", source)
        self.assertIn("activityMatches.length===0", source)
        self.assertIn("No se adivina cuál control corresponde", source)
        self.assertNotIn("Guardar etapa", source)

    def test_runtime_reuses_canonical_crm_mutations_and_pipeline_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Opportunity Owner"})
                company_id = company["id"]
                contact = runtime.create_contact(company_id, {"name": "Lead exacto"})
                opportunity = runtime.create_opportunity(company_id, {
                    "title": "Propuesta exacta",
                    "contact_id": contact["id"],
                    "stage": "PROPOSAL",
                    "next_action": "Enviar versión",
                    "next_action_at": None,
                })
                updated = runtime.update_opportunity(company_id, opportunity["id"], {
                    "next_action": "Revisar propuesta",
                    "next_action_at": "2030-01-02T15:00:00+00:00",
                })
                self.assertEqual(updated["next_action"], "Revisar propuesta")
                activity = runtime.create_activity(company_id, {
                    "opportunity_id": opportunity["id"],
                    "kind": "CALL",
                    "summary": "Confirmar recepción",
                    "due_at": "2030-01-03T15:00:00+00:00",
                })
                self.assertEqual(activity["opportunity_id"], opportunity["id"])
                pipeline = runtime.commercial_pipeline(company_id)
                rows = [row for lane in pipeline["lanes"] for row in lane["opportunities"] if row["id"] == opportunity["id"]]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["next_action"], "Revisar propuesta")
                self.assertEqual(rows[0]["followup"]["pending_activities"], 1)
            finally:
                self._shutdown_runtime(runtime)

    def test_browser_bootstrap_is_appended_after_control_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Opportunity HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                cadence = urlopen(root + "/portfolio-cadence.js", timeout=5).read().decode("utf-8")
                handoff = urlopen(root + "/contextual-control-handoff.js", timeout=5).read().decode("utf-8")
                owner = urlopen(root + "/opportunity-followup-control.js", timeout=5).read().decode("utf-8")
                self.assertIn("/contextual-control-handoff.js", cadence)
                self.assertIn("/opportunity-followup-control.js", handoff)
                self.assertIn("POST_W99_OPPORTUNITY_FOLLOWUP_CONTROL_SCHEMA", owner)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_docs_preserve_exactness_safety_and_frozen_release_boundary(self):
        docs = (ROOT / "docs" / "POST_W99_OPPORTUNITY_FOLLOWUP_CONTROL.md").read_text(encoding="utf-8")
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("`.w63-card`", docs)
        self.assertIn("`pipeline_due_soon`", docs)
        self.assertIn("permanecen `OWNER_CONTROL_GAP`", docs)
        self.assertIn("toda mutación requiere `submit` humano explícito", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)
        self.assertIn("Opportunity Follow-up Control", dev)
        self.assertIn("service_post_w99_opportunity_followup_control_app", dev)
        self.assertIn(
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control",
            dev,
        )


if __name__ == "__main__":
    unittest.main()
