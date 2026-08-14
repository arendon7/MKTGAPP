import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave36 import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class AudienceStaticHttpTests(unittest.TestCase):
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

    def test_audience_bundle_is_served(self):
        with urlopen(self.base + "/audiences.js", timeout=5) as response:
            js = response.read().decode("utf-8")
        self.assertIn("Audiencias CRM", js)
        self.assertIn("CSV → CRM", js)
        self.assertIn("Audiencia guardada (opcional)", js)


class AudienceUiContractTests(unittest.TestCase):
    def test_audience_ui_supports_csv_lists_and_campaign_snapshot(self):
        js = (ROOT / "web" / "audiences.js").read_text(encoding="utf-8")
        loader = (ROOT / "web" / "instagram-local-reel.js").read_text(encoding="utf-8")
        for required in (
            "Audiencias CRM",
            "CSV → CRM",
            "Omitir duplicado",
            "Actualizar campos no vacíos",
            "/contacts/import?strategy=",
            "/audiences",
            "Audiencia guardada (opcional)",
            "La campaña guarda los contactos seleccionados, no una referencia viva a la audiencia",
            "audience-campaign-picker",
        ):
            self.assertIn(required, js)
        self.assertIn("script.src='/audiences.js'", loader)
        self.assertIn("data-audiences-wave36", loader)

    def test_audience_ui_never_sends_provider_messages(self):
        js = (ROOT / "web" / "audiences.js").read_text(encoding="utf-8")
        self.assertIn("No envían mensajes", js)
        for forbidden in (
            "sendWhatsApp(",
            "sendEmail(",
            "publish-now",
            "MetaGraphClient",
            "fetch('https://",
            "setInterval(()=>",
            "MutationObserver(()=>",
        ):
            self.assertNotIn(forbidden, js)

    def test_campaign_model_keeps_contact_snapshot_not_live_audience_reference(self):
        campaign = (ROOT / "src" / "binario_marketing" / "campaign_store.py").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave36.py").read_text(encoding="utf-8")
        self.assertIn("audience_contact_ids", campaign)
        self.assertNotIn("audience_id", campaign)
        self.assertNotIn("/send", service)
        self.assertNotIn("MetaGraphClient", service)

    def test_full_mac_launches_wave36_and_audits_import_without_side_effects(self):
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertTrue(
            "from binario_marketing.service_wave36 import serve" in build
            or "from binario_marketing.service_wave37_app import serve" in build
            or "from binario_marketing.service_wave38_app import serve" in build
        )
        self.assertTrue(
            "from binario_marketing.service_wave36 import AppRuntime" in audit
            or "from binario_marketing.service_wave37_app import AppRuntime" in audit
            or "from binario_marketing.service_wave38_app import AppRuntime" in audit
        )
        self.assertIn("audiences.js", audit)
        self.assertIn("audience_store.py", audit)
        self.assertIn("crm_import.py", audit)
        self.assertTrue(
            "Wave 36 Imported Audience" in audit
            or "Wave 37 Imported Audience" in audit
            or "Wave 38 Imported Audience" in audit
        )
        self.assertIn("runtime.import_contacts_csv", audit)
        self.assertIn("runtime.social.list(company['id']) == []", audit)
        self.assertNotIn("service_wave33", build)
        self.assertNotIn("background-scheduling", audit)


if __name__ == "__main__":
    unittest.main()