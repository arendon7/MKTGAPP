import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.ai_provider import AIGeneration
from binario_marketing.service_wave51_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class FakeAIClient:
    def generate(self, provider, model, *, system, prompt):
        return AIGeneration(provider, model, {
            "summary": "Resumen IA",
            "diagnosis": ["Diagnóstico"],
            "recommendations": [],
            "creative_variants": [],
            "campaign_brief": {"objective": "", "audience": "", "proposition": "", "channels": [], "kpis": [], "notes": ""},
        }, {"response_id": "local-test"})


class Wave51AIHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.ai_client = FakeAIClient()
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

    def request_json(self, path, *, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.base + path, method=method, data=data, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_bundle_provider_status_and_settings_are_served(self):
        with urlopen(self.base + "/ai-copilot.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        for marker in ("AI COPILOT", "Pensar mejor, no automatizar a ciegas", "Guardar en Keychain", "Generar con IA"):
            self.assertIn(marker, ui)
        status, providers = self.request_json("/api/ai/providers")
        self.assertEqual(status, 200)
        self.assertEqual({row["provider"] for row in providers}, {"openai", "anthropic", "gemini", "ollama"})
        ollama = next(row for row in providers if row["provider"] == "ollama")
        self.assertTrue(ollama["configured"])
        self.assertTrue(ollama["local"])
        status, settings = self.request_json(f"/api/companies/{self.company['id']}/ai/settings")
        self.assertEqual(status, 200)
        self.assertIsNone(settings["provider"])

    def test_settings_and_explicit_ollama_generation_roundtrip(self):
        status, settings = self.request_json(
            f"/api/companies/{self.company['id']}/ai/settings",
            method="PATCH",
            body={"provider": "ollama", "model": "local-model", "language": "es", "brand_voice": "Preciso"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(settings["provider"], "ollama")
        status, session = self.request_json(
            f"/api/companies/{self.company['id']}/ai/generate",
            method="POST",
            body={"task": "STRATEGY", "instruction": "Prioriza"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(session["provider"], "ollama")
        self.assertEqual(session["output"]["summary"], "Resumen IA")
        status, rows = self.request_json(f"/api/companies/{self.company['id']}/ai/sessions?limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(rows[0]["id"], session["id"])

    def test_loader_orders_ai_after_command_center(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("command.src='/command-center.js'", loader)
        self.assertIn("command.addEventListener('load',loadAICopilot", loader)
        self.assertIn("ai.src='/ai-copilot.js'", loader)

    def test_ai_surface_has_no_remote_marketing_execution_or_background_generation(self):
        ui = (ROOT / "web" / "ai-copilot.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave51_app.py").read_text(encoding="utf-8")
        provider = (ROOT / "src" / "binario_marketing" / "ai_provider.py").read_text(encoding="utf-8")
        self.assertNotIn("publish-now", ui)
        self.assertNotIn("/activate", ui)
        self.assertNotIn("/api/meta/", ui)
        self.assertNotIn("setInterval(", ui)
        self.assertNotIn("MutationObserver", ui)
        self.assertNotIn('"tools"', provider)
        self.assertNotIn("publish_company_publication_now(", service)
        self.assertNotIn("create_company_paid_media_remote_paused(", service)
        self.assertIn("contact_pii_included", service)
        self.assertIn("provider_secrets_included", service)
        self.assertIn("only user-triggered", service.lower())

    def test_current_arm64_builder_launches_and_audits_wave51(self):
        build = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave51_app", build)
        self.assertIn("audit_wave51_ai_copilot.sh", build)
        self.assertIn('[[ "$ARCH" == "arm64" ]]', build)


if __name__ == "__main__":
    unittest.main()
