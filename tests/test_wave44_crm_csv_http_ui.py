import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave44_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


def post_csv(url, text):
    data = text.encode("utf-8")
    request = Request(url, data=data, method="POST", headers={"Content-Type": "text/csv; charset=utf-8", "Accept": "application/json"})
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class Wave44CrmCsvHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics SAS"})
        self.other = self.runtime.create_company({"name": "Otra Empresa"})
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

    def test_preview_does_not_write_import_is_explicit_and_repeat_safe(self):
        csv_text = "nombre;email;whatsapp\nAna;ana@example.com;+573001112233\n"
        prefix = f"{self.base}/api/companies/{self.company['id']}/crm/contacts"
        status, preview = post_csv(prefix + "/import-preview", csv_text)
        self.assertEqual(status, 200)
        self.assertEqual(preview["valid"], 1)
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)
        status, imported = post_csv(prefix + "/import", csv_text)
        self.assertEqual(status, 201)
        self.assertEqual(imported["created"], 1)
        _, repeated = post_csv(prefix + "/import", csv_text)
        self.assertEqual(repeated["created"], 0)
        self.assertEqual(repeated["duplicates"], 1)
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 1)

    def test_export_is_csv_attachment_and_company_scoped(self):
        self.runtime.create_contact(self.company["id"], {"name": "Contacto Greenatics", "email": "greenatics@example.com"})
        self.runtime.create_contact(self.other["id"], {"name": "Contacto Privado Otra", "email": "otra@example.com"})
        url = f"{self.base}/api/companies/{self.company['id']}/crm/contacts/export"
        with urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type")
            disposition = response.headers.get("Content-Disposition")
        self.assertEqual(content_type, "text/csv; charset=utf-8")
        self.assertIn("attachment;", disposition)
        self.assertIn("contactos-Greenatics-SAS.csv", disposition)
        self.assertIn("Contacto Greenatics", body)
        self.assertNotIn("Contacto Privado Otra", body)

    def test_crm_csv_bundle_is_served_and_import_requires_preview_click(self):
        with urlopen(self.base + "/crm-csv.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        for required in ("PORTABILIDAD CRM", "Previsualizar", "Importar contactos", "Exportar CSV", "import-preview", "file.text()"):
            self.assertIn(required, ui)
        self.assertIn("previewButton.addEventListener('click'", ui)
        self.assertIn("importButton.addEventListener('click'", ui)
        self.assertIn("file.addEventListener('change'", ui)
        self.assertNotIn("file.addEventListener('change',()=>crmCsvImport", ui)
        for forbidden in ("fetch('https://", 'fetch("https://', "/api/meta/", "setInterval(", "MutationObserver("):
            self.assertNotIn(forbidden, ui)

    def test_loader_and_mac_build_chain_wave44_after_wave43(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("#daily-ops-wave43-style", loader)
        self.assertIn("csv.src='/crm-csv.js'", loader)
        self.assertIn("daily.addEventListener('load',loadCrmCsv", loader)
        self.assertIn("service_wave43_app import serve", build)
        self.assertIn("service_wave44_app import serve", build)
        self.assertLess(build.index("service_wave43_app import serve"), build.index("service_wave44_app import serve"))
        self.assertIn("audit_wave44_crm_csv.sh", build)


if __name__ == "__main__":
    unittest.main()
