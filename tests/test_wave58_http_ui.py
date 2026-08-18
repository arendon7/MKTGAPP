from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from binario_marketing.service_wave58_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
MASTER = "wave58-http-master-" + "x" * 40
TENANT = "tenant_" + "7" * 24


class FakeAdminClient:
    def __init__(self, gateway_url, master_secret):
        self.gateway_url = gateway_url
        self.master_secret = master_secret

    def execute(self, tenant_id, action, *, purpose=None):
        versions = {
            ("REGISTER", None): (1, 1, "ACTIVE"),
            ("STATUS", None): (1, 1, "ACTIVE"),
            ("ROTATE", "ingress"): (2, 1, "ACTIVE"),
            ("ROTATE", "pull"): (1, 2, "ACTIVE"),
            ("REVOKE", None): (1, 1, "REVOKED"),
            ("REACTIVATE", None): (2, 2, "ACTIVE"),
        }
        ingress, pull, status = versions[(action, purpose)]
        return {
            "schema": "binario.marketing.gateway-tenant-admin.v1",
            "action": action,
            "tenant": {
                "tenant_id": tenant_id,
                "status": status,
                "ingress_version": ingress,
                "pull_version": pull,
                "created_at": "2026-08-18T18:00:00+00:00",
                "updated_at": "2026-08-18T18:01:00+00:00",
                "revoked_at": "2026-08-18T18:01:00+00:00" if status == "REVOKED" else None,
            },
            "secret_returned": False,
            "master_secret_returned": False,
        }


class Wave58HttpUiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BINARIO_GATEWAY_MASTER_SECRET": MASTER}, clear=False)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Wave58 HTTP"})
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

    def configure(self):
        return self.request_json(
            f"/api/companies/{self.company['id']}/public-gateway/config",
            method="POST",
            body={"gateway_url": "https://gateway.example.com", "tenant_id": TENANT},
        )

    def test_wave58_bundle_is_served_and_exposes_explicit_controls_without_polling(self):
        with urlopen(self.base + "/public-gateway-wave58.js", timeout=5) as response:
            text = response.read().decode("utf-8")
        for marker in (
            "Registro, rotación y revocación",
            "Registrar tenant",
            "Rotar secreto del sitio",
            "Rotar pull del desktop",
            "Revocar tenant",
            "Reactivar + invalidar claves antiguas",
            "X-Binario-Credential-Version",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("setInterval", text)
        self.assertNotIn("fetch('https://", text)
        self.assertIn("opsApi", text)

    def test_tenant_control_route_is_company_scoped_explicit_and_secret_free(self):
        self.configure()
        status, before = self.request_json(f"/api/companies/{self.company['id']}/public-gateway")
        self.assertEqual(status, 200)
        self.assertFalse(before["readiness"]["ready_to_sync"])
        with patch("binario_marketing.service_wave58_app.GatewayTenantAdminClient", FakeAdminClient):
            status, result = self.request_json(
                f"/api/companies/{self.company['id']}/public-gateway/tenant-control",
                method="POST",
                body={"action": "REGISTER"},
            )
        self.assertEqual(status, 200)
        self.assertTrue(result["center"]["readiness"]["ready_to_sync"])
        self.assertFalse(result["secret_returned"])
        text = json.dumps(result)
        self.assertNotIn(MASTER, text)
        self.assertNotIn("site_secret", text)
        self.assertNotIn("pull_secret", text)

    def test_loader_orders_wave58_after_wave56_and_builder_keeps_historical_chain(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("gateway.addEventListener('load',loadPublicGateway58", loader)
        self.assertIn("if(ready('#wave56-gateway-style'))loadPublicGateway58()", loader)
        self.assertIn("tenant.src='/public-gateway-wave58.js'", loader)
        self.assertIn("'service_wave56_app','service_wave58_app'", builder)
        self.assertIn("audit_wave56_public_gateway.sh", builder)
        self.assertIn("audit_wave58_tenant_registry.sh", builder)
        self.assertIn("CURRENT ARM64 ITERATION BUILD PASS: Wave 58", builder)
        for marker in ("audit_wave52_learning_loop.sh", "audit_wave53_attribution_foundation.sh", "audit_wave54_capture_bridge.sh", "audit_wave55_lead_intake.sh"):
            self.assertIn(marker, builder)

    def test_sql_registry_is_rls_locked_atomic_service_role_only_and_secret_free(self):
        sql = (ROOT / "gateway" / "supabase" / "002_tenant_credential_registry.sql").read_text(encoding="utf-8")
        lower = sql.lower()
        self.assertGreaterEqual(lower.count("enable row level security"), 2)
        self.assertGreaterEqual(lower.count("revoke all on table"), 2)
        self.assertIn("security definer", lower)
        self.assertIn("set search_path = pg_catalog, public", lower)
        self.assertIn("binario_gateway_tenant_rotate", lower)
        self.assertIn("returning * into v_row", lower)
        self.assertIn("v_old := v_row.ingress_version - 1", lower)
        self.assertIn("v_old := v_row.pull_version - 1", lower)
        self.assertIn("grant execute on function public.binario_gateway_tenant_rotate(text, text) to service_role", lower)
        tenant_columns = lower.split("create table if not exists public.binario_gateway_tenants", 1)[1].split(");", 1)[0]
        for forbidden in ("master_secret", "ingress_secret", "pull_secret", "hmac_secret", " site_secret"):
            self.assertNotIn(forbidden, tenant_columns)

    def test_deployed_source_has_admin_endpoint_and_registry_health_gate(self):
        shared = (ROOT / "api" / "_shared.py").read_text(encoding="utf-8")
        health = (ROOT / "api" / "health.py").read_text(encoding="utf-8")
        tenant_api = (ROOT / "api" / "tenant.py").read_text(encoding="utf-8")
        self.assertIn("VersionedGatewayService", shared)
        self.assertIn("SupabaseTenantCredentialRegistry", shared)
        self.assertIn("tenant_admin_service", shared)
        self.assertIn("registry.healthcheck()", health)
        self.assertIn("HMAC_SHA256_V1_VERSIONED", health)
        self.assertIn("tenant_admin_service().execute", tenant_api)
        self.assertIn("max_bytes=8 * 1024", tenant_api)

    def test_exactly_three_canonical_workflows_remain(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
