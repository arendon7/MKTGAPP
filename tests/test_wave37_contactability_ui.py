import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave37_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class ContactabilityStaticHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_wave37_serves_ordered_audiences_then_contactability(self):
        with urlopen(self.base + "/audiences.js", timeout=5) as response:
            loader = response.read().decode("utf-8")
        with urlopen(self.base + "/audiences-base.js", timeout=5) as response:
            audience = response.read().decode("utf-8")
        with urlopen(self.base + "/contactability.js", timeout=5) as response:
            contactability = response.read().decode("utf-8")
        self.assertIn("audiences-base.js", loader)
        self.assertIn("contactability.js", loader)
        self.assertIn("Audiencias CRM", audience)
        self.assertIn("Estado por canal", contactability)


class ContactabilityUiContractTests(unittest.TestCase):
    def test_contactability_ui_exposes_evidence_and_explicit_states(self):
        js = (ROOT / "web" / "contactability.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "web" / "audiences-wave37-loader.js").read_text(encoding="utf-8")
        for required in (
            "CONTACTABILIDAD",
            "Estado por canal",
            "UNKNOWN",
            "OPTED_IN",
            "OPTED_OUT",
            "Fuente / evidencia",
            "Fecha de captura",
            "Restablecer a UNKNOWN",
            "Sólo OPTED_IN será elegible",
            "Gate futuro: OPTED_IN",
        ):
            self.assertIn(required, js)
        self.assertIn("/audiences-base.js", bootstrap)
        self.assertIn("/contactability.js", bootstrap)

    def test_contactability_ui_and_runtime_have_no_send_capability(self):
        js = (ROOT / "web" / "contactability.js").read_text(encoding="utf-8")
        runtime = (ROOT / "src" / "binario_marketing" / "service_wave37.py").read_text(encoding="utf-8")
        for forbidden in (
            "sendWhatsApp(",
            "sendEmail(",
            "publish-now",
            "MetaGraphClient",
            "fetch('https://",
            "/send",
        ):
            self.assertNotIn(forbidden, js)
            self.assertNotIn(forbidden, runtime)
        self.assertIn('"send_gate"] = "OPTED_IN_REQUIRED"', runtime)
        self.assertIn('"provider_configured"] = False', runtime)

    def test_campaign_readiness_is_current_while_campaign_membership_stays_snapshot(self):
        campaign_store = (ROOT / "src" / "binario_marketing" / "campaign_store.py").read_text(encoding="utf-8")
        runtime = (ROOT / "src" / "binario_marketing" / "service_wave37.py").read_text(encoding="utf-8")
        self.assertIn("audience_contact_ids", campaign_store)
        self.assertNotIn("contactability", campaign_store)
        self.assertIn("self.contactability.get", runtime)
        self.assertIn("OPTED_IN_REQUIRED", runtime)


if __name__ == "__main__":
    unittest.main()
