import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_contextual_control_handoff_app import AppRuntime, create_server

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

    def test_control_mapping_is_explicit_and_pipeline_gap_is_not_stage_substitution(self):
        source = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        for value in (
            "crm_overdue",
            "crm_today",
            "publication_failed",
            "publication_overdue",
            "publication_today",
            "lead_conflict",
            "lead_matched",
            "lead_new",
            "lead_unidentified",
            "needs_opportunity",
            "needs_followup",
            "CAMPAIGN_EXECUTION",
            "CAMPAIGN_INTELLIGENCE",
        ):
            self.assertIn(value, source)
        self.assertIn("kind.startsWith('pipeline_')", source)
        self.assertIn("No se sustituye por el selector de etapa", source)
        self.assertNotIn("querySelector('select')", source)

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

    def test_browser_bootstrap_is_appended_after_portfolio_cadence(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Control HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                evidence = urlopen(root + "/evidence-observability.js", timeout=5).read().decode("utf-8")
                cadence = urlopen(root + "/portfolio-cadence.js", timeout=5).read().decode("utf-8")
                handoff = urlopen(root + "/contextual-control-handoff.js", timeout=5).read().decode("utf-8")
                self.assertIn("/portfolio-cadence.js", evidence)
                self.assertIn("/contextual-control-handoff.js", cadence)
                self.assertIn("POST_W99_CONTROL_HANDOFF_SCHEMA", handoff)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_docs_preserve_fail_closed_and_frozen_release_contracts(self):
        docs = (ROOT / "docs" / "POST_W99_CONTEXTUAL_CONTROL_HANDOFF.md").read_text(encoding="utf-8")
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("OWNER_CONTROL_GAP", docs)
        self.assertIn("CONTROL_AMBIGUOUS", docs)
        self.assertIn("nunca dispara `.click()`", docs)
        self.assertIn("pipeline_*", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)
        self.assertIn("Contextual Control Handoff", dev)
        self.assertIn("service_post_w99_contextual_control_handoff_app", dev)
        self.assertIn(
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff",
            dev,
        )


if __name__ == "__main__":
    unittest.main()
