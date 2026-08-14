import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave35 import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class CampaignStaticHttpTests(unittest.TestCase):
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

    def test_campaign_bundle_is_served(self):
        with urlopen(self.base + "/campaigns.js", timeout=5) as response:
            js = response.read().decode("utf-8")
        self.assertIn("Centro de campañas", js)
        self.assertIn("Audiencia CRM", js)
        self.assertIn("Piezas de biblioteca", js)
        self.assertIn("Publicaciones vinculadas", js)


class CampaignUiContractTests(unittest.TestCase):
    def test_campaign_center_joins_existing_operational_surfaces(self):
        js = (ROOT / "web" / "campaigns.js").read_text(encoding="utf-8")
        loader = (ROOT / "web" / "instagram-local-reel.js").read_text(encoding="utf-8")
        for required in (
            "Centro de campañas",
            "Orquestación comercial",
            "Audiencia CRM",
            "Piezas de biblioteca",
            "Publicaciones vinculadas",
            "/contacts",
            "/media",
            "detail?.publications",
            "data-ops-view=\"campaigns\"",
            "provider todavía no habilitado",
        ):
            self.assertIn(required, js)
        self.assertIn("script.src='/campaigns.js'", loader)
        self.assertIn("data-campaigns-wave35", loader)

    def test_campaign_ui_has_no_external_send_or_provider_activation(self):
        js = (ROOT / "web" / "campaigns.js").read_text(encoding="utf-8")
        self.assertIn("No envía email, WhatsApp, publicaciones ni activa pauta automáticamente", js)
        for forbidden in (
            "sendWhatsApp(",
            "sendEmail(",
            "publish-now",
            "activate",
            "method:'DELETE'",
            "fetch('https://",
            "setInterval(()=>",
            "MutationObserver(()=>",
        ):
            self.assertNotIn(forbidden, js)

    def test_campaign_runtime_has_no_send_routes(self):
        service = (ROOT / "src" / "binario_marketing" / "service_wave35.py").read_text(encoding="utf-8")
        self.assertIn("CampaignStore", service)
        self.assertIn("provider_configured\": False", service)
        self.assertNotIn("/send", service)
        self.assertNotIn("publish_company_publication_now(", service)
        self.assertNotIn("MetaGraphClient", service)

    def test_full_mac_preserves_wave35_through_certified_extension(self):
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertTrue(
            "from binario_marketing.service_wave35 import serve" in build
            or "from binario_marketing.service_wave36 import serve" in build
            or "from binario_marketing.service_wave37_app import serve" in build
        )
        self.assertTrue(
            "from binario_marketing.service_wave35 import AppRuntime" in audit
            or "from binario_marketing.service_wave36 import AppRuntime" in audit
            or "from binario_marketing.service_wave37_app import AppRuntime" in audit
        )
        self.assertIn("campaigns.js", audit)
        self.assertIn("campaign_store.py", audit)
        self.assertTrue(
            "Wave 35 Campaign Audit" in audit
            or "Wave 36 Campaign Audit" in audit
            or "Wave 37 Campaign Audit" in audit
        )
        self.assertIn("provider_configured'] is False", audit)
        self.assertIn("runtime.social.list(company['id']) == []", audit)
        self.assertNotIn("service_wave33", build)
        self.assertNotIn("background-scheduling", audit)


if __name__ == "__main__":
    unittest.main()