import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service_wave59_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave59LocalProductIntegrationTests(unittest.TestCase):
    def test_runtime_and_command_center_work_without_cloud_configuration(self):
        cloud = {
            "BINARIO_GATEWAY_MASTER_SECRET": "",
            "SUPABASE_URL": "",
            "SUPABASE_SECRET_KEY": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "VERCEL_TOKEN": "",
        }
        with patch.dict(os.environ, cloud, clear=False), tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company = runtime.create_company({"name": "Local Only"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(base + "/local-product-integration.js", timeout=5) as response:
                    ui = response.read().decode("utf-8")
                self.assertIn("Marketing OS local", ui)
                with urlopen(base + f"/api/companies/{company['id']}/command-center", timeout=5) as response:
                    center = json.loads(response.read().decode("utf-8"))
                self.assertEqual(center["schema"], "binario.marketing.command-center.v1")
                self.assertEqual(center["company"]["id"], company["id"])
                self.assertFalse(center["safety"]["remote_refresh_performed"])
                self.assertFalse(center["safety"]["provider_mutation_performed"])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()

    def test_navigation_is_operational_and_cloud_is_explicitly_optional(self):
        ui = (ROOT / "web" / "local-product-integration.js").read_text(encoding="utf-8")
        for marker in (
            "TRABAJO DIARIO", "CREAR Y DISTRIBUIR", "MEDIR Y MEJORAR", "CONFIGURACIÓN",
            "Hoy", "Inbox", "Leads", "CRM", "Campañas", "Creative Studio", "Video Studio",
            "Calendario", "Publicar", "Pauta", "Resultados", "Empresas & Meta",
            "Recepción web 24/7", "Avanzado · opcional", "No son necesarias para operar la app local",
        ):
            self.assertIn(marker, ui)
        for step in ("01 · ATENDER", "02 · CONVERTIR", "03 · PLANEAR", "04 · CREAR", "05 · DISTRIBUIR", "06 · APRENDER"):
            self.assertIn(step, ui)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertNotIn("SUPABASE_", ui)
        self.assertNotIn("VERCEL_", ui)

    def test_service_adds_static_surface_only_and_keeps_loopback_boundary(self):
        service = (ROOT / "src" / "binario_marketing" / "service_wave59_app.py").read_text(encoding="utf-8")
        self.assertIn("service_wave56_app as base", service)
        self.assertIn('path == "/local-product-integration.js"', service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertIn('host: str = "127.0.0.1"', service)
        self.assertIn("refusing non-loopback bind without --allow-network", service)
        for cloud in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "VERCEL_TOKEN"):
            self.assertNotIn(cloud, service)

    def test_loader_preserves_wave56_and_loads_wave59_after_it(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("lead.addEventListener('load',loadPublicGateway", loader)
        self.assertIn("gateway.src='/public-gateway.js'", loader)
        self.assertIn("gateway.addEventListener('load',loadLocalProduct", loader)
        self.assertIn("existing.addEventListener('load',loadLocalProduct", loader)
        self.assertIn("local.src='/local-product-integration.js'", loader)

    def test_builder_keeps_all_historical_gates_and_makes_wave59_current(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave55_guard_app','service_wave56_app','service_wave59_app", builder)
        for marker in (
            "audit_wave47_product_surface.sh", "audit_wave48_paid_media_center.sh", "audit_wave49_creative_studio.sh",
            "audit_wave50_command_center.sh", "audit_wave51_ai_copilot.sh", "audit_wave52_learning_loop.sh",
            "audit_wave53_attribution_foundation.sh", "audit_wave54_capture_bridge.sh", "audit_wave55_lead_intake.sh",
            "audit_wave56_public_gateway.sh", "audit_wave59_local_product_integration.sh",
        ):
            self.assertIn(marker, builder)
        self.assertIn("CURRENT ARM64 ITERATION BUILD PASS: Wave 59", builder)
        self.assertIn('[[ "$ARCH" == "arm64" ]]', builder)

    def test_workflow_count_and_release_boundary_are_unchanged(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)


if __name__ == "__main__":
    unittest.main()
