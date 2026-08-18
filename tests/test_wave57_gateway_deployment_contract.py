from __future__ import annotations

import unittest
from pathlib import Path

from api.health import health_response


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "wave57_gateway_live_smoke.py"
DOC = ROOT / "docs" / "WAVE57_GATEWAY_DEPLOYMENT_LIVE.md"
VERCEL = ROOT / "vercel.json"
QUEUE_SQL = ROOT / "gateway" / "supabase" / "001_public_intake_queue.sql"
HEALTH = ROOT / "api" / "health.py"
STORAGE = ROOT / "gateway" / "supabase_storage.py"


class _HealthyStorage:
    def healthcheck(self):
        return True


class _BrokenStorage:
    def healthcheck(self):
        raise RuntimeError("synthetic remote queue failure")


class Wave57GatewayDeploymentContractTests(unittest.TestCase):
    def test_live_smoke_proves_full_signed_roundtrip_without_real_customer_pii(self):
        text = SMOKE.read_text(encoding="utf-8")
        self.assertIn('"Binario Wave 57 Deployment Smoke"', text)
        self.assertIn('request_signature(ingress_secret', text)
        self.assertIn('client.pull(limit=100)', text)
        self.assertIn('verify_envelope(match', text)
        self.assertIn('client.ack([event_id])', text)
        self.assertIn('"real_customer_pii_used": False', text)
        self.assertIn('"crm_mutations": 0', text)
        self.assertIn('"provider_mutations": 0', text)
        self.assertIn('"secrets_returned": False', text)
        self.assertNotIn("service_wave57_app", text)

    def test_smoke_requires_server_side_configuration_and_does_not_embed_secrets(self):
        text = SMOKE.read_text(encoding="utf-8")
        for name in (
            "BINARIO_GATEWAY_URL",
            "BINARIO_GATEWAY_TENANT_ID",
            "BINARIO_GATEWAY_MASTER_SECRET",
        ):
            self.assertIn(name, text)
        self.assertNotIn("SUPABASE_SECRET_KEY=", text)
        self.assertNotIn("sb_secret_", text)
        self.assertNotIn("service_role", text)

    def test_public_health_is_fail_closed_until_master_and_remote_queue_are_ready(self):
        status, payload = health_response(environ={}, storage_factory=_HealthyStorage)
        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "unavailable")
        self.assertFalse(payload["ready_for_intake"])

        status, payload = health_response(
            environ={"BINARIO_GATEWAY_MASTER_SECRET": "x" * 32},
            storage_factory=_BrokenStorage,
        )
        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "unavailable")
        self.assertFalse(payload["ready_for_intake"])
        self.assertNotIn("error", payload)

        status, payload = health_response(
            environ={"BINARIO_GATEWAY_MASTER_SECRET": "x" * 32},
            storage_factory=_HealthyStorage,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["ready_for_intake"])
        self.assertFalse(payload["browser_secret_supported"])

    def test_health_probe_checks_the_real_dedicated_queue_table_without_secret_echo(self):
        health_text = HEALTH.read_text(encoding="utf-8")
        storage_text = STORAGE.read_text(encoding="utf-8")
        self.assertIn("storage.healthcheck()", health_text)
        self.assertIn("GatewayService(storage", health_text)
        self.assertIn('return 503', health_text)
        self.assertIn('"ready_for_intake": False', health_text)
        self.assertIn('def healthcheck(self)', storage_text)
        self.assertIn('"select": "tenant_id"', storage_text)
        self.assertNotIn("SUPABASE_SECRET_KEY\"", health_text)
        self.assertNotIn("BINARIO_GATEWAY_MASTER_SECRET\":", health_text)

    def test_deployment_runbook_requires_dedicated_infrastructure_and_live_evidence(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("dedicated Supabase project", text)
        self.assertIn("dedicated Vercel project", text)
        self.assertIn("BINARIO_GATEWAY_MASTER_SECRET", text)
        self.assertIn("SUPABASE_URL", text)
        self.assertIn("SUPABASE_SECRET_KEY", text)
        self.assertIn("ACTIVE_HEALTHY", text)
        self.assertIn("/api/health", text)
        self.assertIn("wave57_gateway_live_smoke.py", text)
        self.assertIn("does not change the product release boundary", text)
        self.assertIn("0.9.0.dev1", text)

    def test_existing_deployable_gateway_contract_remains_present(self):
        self.assertTrue(VERCEL.is_file())
        self.assertTrue(QUEUE_SQL.is_file())
        sql = QUEUE_SQL.read_text(encoding="utf-8").lower()
        self.assertIn("enable row level security", sql)
        self.assertIn("revoke", sql)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
