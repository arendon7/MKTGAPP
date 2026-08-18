import base64
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave49_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z5mEAAAAASUVORK5CYII=")


class Wave49CreativeStudioHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        workspace = self.runtime.ensure_company_workspace(self.company["id"])
        self.project_id = workspace["project_id"]
        self.asset = self.runtime.projects.add_uploaded_asset(self.project_id, "creative.png", "image", io.BytesIO(PNG), len(PNG))
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start(); self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def request_json(self, path, *, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.base + path, method=method, data=data, headers={"Content-Type":"application/json"})
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_creative_studio_bundle_and_summary_are_served(self):
        with urlopen(self.base + "/creative-studio-center.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        self.assertIn("Guardar en biblioteca", ui)
        self.assertIn("Usar en campaña", ui)
        self.assertIn("Usar en Pauta", ui)
        status, summary = self.request_json(f"/api/companies/{self.company['id']}/creative-studio")
        self.assertEqual(status, 200)
        self.assertEqual(summary["workspace"]["project_id"], self.project_id)
        self.assertEqual(summary["assets"][0]["id"], self.asset.id)

    def test_promote_endpoint_is_idempotent(self):
        path = f"/api/companies/{self.company['id']}/creative-studio/promote"
        body = {"source_type":"project_asset","source_id":self.asset.id}
        status, first = self.request_json(path, method="POST", body=body)
        self.assertEqual(status, 201)
        _, second = self.request_json(path, method="POST", body=body)
        self.assertEqual(first["media"]["id"], second["media"]["id"])
        self.assertTrue(second["reused"])

    def test_attach_campaign_endpoint(self):
        _, promoted = self.request_json(
            f"/api/companies/{self.company['id']}/creative-studio/promote",
            method="POST", body={"source_type":"project_asset","source_id":self.asset.id},
        )
        campaign = self.runtime.create_campaign(self.company["id"], {"name":"Campaña", "objective":"LEADS"})
        status, result = self.request_json(
            f"/api/companies/{self.company['id']}/creative-studio/media/{promoted['media']['id']}/campaigns/{campaign['id']}",
            method="POST", body={},
        )
        self.assertEqual(status, 200)
        self.assertIn(promoted["media"]["id"], result["campaign"]["media_ids"])

    def test_loader_and_current_build_include_wave49(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        build = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("paid.src='/paid-media-center.js'", loader)
        self.assertIn("creative.src='/creative-studio-center.js'", loader)
        self.assertIn("paid.addEventListener('load',loadCreativeStudioCenter", loader)
        self.assertIn("service_wave49_app", build)
        self.assertIn("audit_wave49_creative_studio.sh", build)

    def test_ui_does_not_add_background_or_activation_behavior(self):
        ui = (ROOT / "web" / "creative-studio-center.js").read_text(encoding="utf-8")
        for forbidden in ("setInterval(", "/activate", "autoPublish", "autoSpend"):
            self.assertNotIn(forbidden, ui)


if __name__ == "__main__": unittest.main()
