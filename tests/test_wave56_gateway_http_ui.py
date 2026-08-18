import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave56_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
MASTER = "wave56-http-master-" + "x" * 40
TENANT = "tenant_" + "c" * 24


class Wave56GatewayHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BINARIO_GATEWAY_MASTER_SECRET": MASTER}, clear=False)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
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
        self.env.stop()

    def request_json(self, path, *, method="GET", body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            self.base + path,
            method=method,
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
        )
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_bundle_center_and_secret_free_credential_status_are_served(self):
        with urlopen(self.base + "/public-gateway.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        self.assertIn("Public Intake Gateway", ui)
        self.assertIn("Sincronizar ahora", ui)
        status, center = self.request_json(f"/api/companies/{self.company['id']}/public-gateway")
        self.assertEqual(status, 200)
        self.assertEqual(center["schema"], "binario.marketing.public-gateway-center.v1")
        self.assertFalse(center["readiness"]["gateway_url_configured"])
        status, credential = self.request_json("/api/public-gateway/credential")
        self.assertEqual(status, 200)
        self.assertTrue(credential["configured"])
        self.assertEqual(credential["source"], "environment")
        self.assertNotIn(MASTER, json.dumps(credential))
        self.assertFalse(credential["secret_returned"])

    def test_company_gateway_config_requires_clean_https_origin(self):
        endpoint = f"/api/companies/{self.company['id']}/public-gateway/config"
        invalid = [
            "http://gateway.example.com",
            "https://user:pass@gateway.example.com",
            "https://gateway.example.com/path",
            "https://gateway.example.com?secret=x",
        ]
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(HTTPError) as caught:
                    self.request_json(endpoint, method="POST", body={"gateway_url": url, "tenant_id": TENANT})
                self.assertEqual(caught.exception.code, 400)
        status, center = self.request_json(endpoint, method="POST", body={
            "gateway_url": "https://gateway.example.com/", "tenant_id": TENANT,
        })
        self.assertEqual(status, 200)
        self.assertEqual(center["config"]["gateway_url"], "https://gateway.example.com")
        self.assertEqual(center["config"]["tenant_id"], TENANT)
        self.assertTrue(center["readiness"]["ready_to_sync"])
        self.assertNotIn(MASTER, json.dumps(center))

    def test_site_secret_is_explicit_and_derived_not_master_or_pull_secret(self):
        self.request_json(f"/api/companies/{self.company['id']}/public-gateway/config", method="POST", body={
            "gateway_url": "https://gateway.example.com", "tenant_id": TENANT,
        })
        status, payload = self.request_json(
            f"/api/companies/{self.company['id']}/public-gateway/site-secret",
            method="POST",
            body={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["tenant_id"], TENANT)
        self.assertEqual(payload["purpose"], "SERVER_TO_SERVER_INGRESS_ONLY")
        self.assertFalse(payload["browser_safe"])
        self.assertNotEqual(payload["site_secret"], MASTER)
        self.assertEqual(len(payload["site_secret"]), 64)

    def test_loader_builder_audit_and_deployment_contract_preserve_historical_layers(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_wave56_public_gateway.sh").read_text(encoding="utf-8")
        ui = (ROOT / "web" / "public-gateway.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave56_app.py").read_text(encoding="utf-8")
        core = (ROOT / "gateway" / "core.py").read_text(encoding="utf-8")
        sql = (ROOT / "gateway" / "supabase" / "001_public_intake_queue.sql").read_text(encoding="utf-8")
        keychain = (ROOT / "native" / "meta_keychain_helper.swift").read_text(encoding="utf-8")
        vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

        self.assertIn("lead.addEventListener('load',loadPublicGateway", loader)
        self.assertIn("gateway.src='/public-gateway.js'", loader)
        self.assertIn("service_wave55_guard_app','service_wave56_app", builder)
        for marker in ("Wave 52", "Wave 53", "Wave 54", "Wave 55", "Wave 56"):
            self.assertIn(marker, builder)
        self.assertIn("audit_wave56_public_gateway.sh", builder)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertIn('"background_polling": False', service)
        self.assertIn('"gateway_can_mutate_crm": False', service)
        self.assertIn("MAX_CLOCK_SKEW_SECONDS = 300", core)
        self.assertIn("RETENTION_SECONDS = 30 * 24 * 3600", core)
        self.assertIn("enable row level security", sql.lower())
        self.assertIn("revoke all on table public.binario_public_intake_queue from anon, authenticated", sql)
        self.assertIn('"gateway": SecretSlot', keychain)
        self.assertIn("api/*.py", vercel["functions"])
        self.assertNotIn(".github/workflows", audit)

    def test_gateway_source_has_four_deployment_entrypoints_and_no_fourth_workflow(self):
        for name in ("intake", "pull", "ack", "health"):
            path = ROOT / "api" / f"{name}.py"
            self.assertTrue(path.is_file(), name)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        storage = (ROOT / "gateway" / "supabase_storage.py").read_text(encoding="utf-8")
        ui = (ROOT / "web" / "public-gateway.js").read_text(encoding="utf-8")
        self.assertIn("SUPABASE_SECRET_KEY", storage)
        self.assertNotIn("SUPABASE_SECRET_KEY", ui)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", ui)


if __name__ == "__main__":
    unittest.main()
