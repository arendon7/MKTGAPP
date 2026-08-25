import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_evidence_observability_integrated_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class PostW99EvidenceObservabilityIntegrationTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_runtime_preserves_current_chain_and_adds_evidence_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Evidence Integrated"})
                company_id = company["id"]
                self.assertEqual(runtime.today_execution(company_id)["schema"], "binario.marketing.today-execution.v1")
                self.assertEqual(runtime.executive_cockpit(company_id)["schema"], "binario.marketing.executive-cockpit.v1")
                self.assertEqual(runtime.evidence_observability(company_id)["schema"], "binario.marketing.evidence-observability.v1")
            finally:
                self._shutdown_runtime(runtime)

    def test_browser_bootstrap_chain_is_cumulative_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Evidence HTTP"})
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
                evidence_js = urlopen(root + "/evidence-observability.js", timeout=5).read().decode("utf-8")
                self.assertIn("postW99EvidenceState", evidence_js)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_integrated_endpoint_is_company_scoped_and_get_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company = runtime.create_company({"name": "Evidence API"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                payload = json.loads(urlopen(root + f"/api/companies/{company['id']}/evidence-observability", timeout=5).read())
                self.assertEqual(payload["schema"], "binario.marketing.evidence-observability.v1")
                self.assertTrue(payload["safety"]["read_only_projection"])
                self.assertFalse(payload["safety"]["provider_read_performed"])
                self.assertFalse(payload["safety"]["business_mutation_performed"])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_docs_and_entrypoint_preserve_frozen_release_boundary(self):
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        cadence_terminal = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_cadence_app.py").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        evidence_docs = (ROOT / "docs" / "POST_W99_EVIDENCE_OBSERVABILITY.md").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_cadence_app", entrypoint)
        self.assertIn("service_post_w99_evidence_observability_integrated_app as base", cadence_terminal)
        self.assertIn("service_post_w99_evidence_observability_integrated_app", docs)
        self.assertIn("Today → Execution Return → Contextual Deep Linking → Evidence Observability", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", evidence_docs)
        self.assertIn("No constituye W100", evidence_docs)


if __name__ == "__main__":
    unittest.main()
