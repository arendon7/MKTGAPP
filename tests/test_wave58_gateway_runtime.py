from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.public_gateway import body_sha256, envelope_signature
from binario_marketing.public_gateway_wave58 import derive_versioned_tenant_secret
from binario_marketing.service_wave58_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]
MASTER = "wave58-master-secret-" + "x" * 40
TENANT = "tenant_" + "8" * 24
EVENT = "evt_" + "9" * 32
RECEIVED = "2026-08-18T18:58:00+00:00"


def remote_tenant(*, status="ACTIVE", ingress=1, pull=1):
    return {
        "tenant_id": TENANT,
        "status": status,
        "ingress_version": ingress,
        "pull_version": pull,
        "created_at": "2026-08-18T18:50:00+00:00",
        "updated_at": "2026-08-18T18:55:00+00:00",
        "revoked_at": "2026-08-18T18:56:00+00:00" if status == "REVOKED" else None,
    }


class FakeAdminClient:
    states = {}
    calls = []

    def __init__(self, gateway_url, master_secret):
        self.gateway_url = gateway_url
        self.master_secret = master_secret

    def execute(self, tenant_id, action, *, purpose=None):
        self.__class__.calls.append((tenant_id, action, purpose))
        key = (action, purpose)
        tenant = dict(self.__class__.states[key])
        return {
            "schema": "binario.marketing.gateway-tenant-admin.v1",
            "action": action if not purpose else f"{action}_{purpose.upper()}",
            "tenant": tenant,
            "secret_returned": False,
            "master_secret_returned": False,
        }


class FakeGatewayClient:
    def __init__(self, events):
        self.events = list(events)
        self.ack_calls = []
        self.pull_limits = []

    def pull(self, *, limit=100):
        self.pull_limits.append(limit)
        return self.events[:limit]

    def ack(self, event_ids):
        self.ack_calls.append(list(event_ids))
        return {
            "schema": "binario.marketing.public-intake-ack.v1",
            "credential_version": 2,
            "requested": len(event_ids),
            "acked": len(event_ids),
        }


def make_envelope(*, pull_version=2, lead=None):
    payload = {
        "schema": "binario.marketing.public-lead.v1",
        "external_ref": "wave58-runtime",
        "lead": lead or {"name": "Wave 58 Lead", "email": "wave58@example.com", "source": "gateway"},
    }
    digest = body_sha256(payload)
    secret = derive_versioned_tenant_secret(MASTER, TENANT, purpose="pull", version=pull_version)
    return {
        "schema": "binario.marketing.public-intake-envelope.v1",
        "tenant_id": TENANT,
        "event_id": EVENT,
        "received_at": RECEIVED,
        "payload": payload,
        "payload_sha256": digest,
        "credential_version": pull_version,
        "signature": envelope_signature(secret, TENANT, EVENT, RECEIVED, digest),
    }


class Wave58GatewayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BINARIO_GATEWAY_MASTER_SECRET": MASTER}, clear=False)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Wave 58 Company"})
        self.runtime.configure_public_gateway(self.company["id"], {
            "gateway_url": "https://gateway.example.com",
            "tenant_id": TENANT,
        })
        FakeAdminClient.calls = []
        FakeAdminClient.states = {
            ("REGISTER", None): remote_tenant(),
            ("STATUS", None): remote_tenant(),
            ("ROTATE", "ingress"): remote_tenant(ingress=2, pull=1),
            ("ROTATE", "pull"): remote_tenant(ingress=2, pull=2),
            ("REVOKE", None): remote_tenant(status="REVOKED", ingress=2, pull=2),
            ("REACTIVATE", None): remote_tenant(ingress=3, pull=3),
        }

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()
        self.env.stop()

    def tenant_action(self, action):
        with patch("binario_marketing.service_wave58_app.GatewayTenantAdminClient", FakeAdminClient):
            return self.runtime.gateway_tenant_action(self.company["id"], {"action": action})

    def test_readiness_is_fail_closed_until_remote_tenant_registration(self):
        center = self.runtime.public_gateway_payload(self.company["id"])
        self.assertFalse(center["readiness"]["ready_to_sync"])
        self.assertFalse(center["readiness"]["tenant_registered"])
        self.assertEqual(center["tenant_registry"]["status"], "UNREGISTERED")
        self.assertFalse(center["tenant_registry"]["secret_values_included"])
        result = self.tenant_action("REGISTER")
        self.assertTrue(result["center"]["readiness"]["ready_to_sync"])
        self.assertEqual(result["tenant"], {"status": "ACTIVE", "ingress_version": 1, "pull_version": 1})
        self.assertFalse(result["secret_returned"])

    def test_local_tenant_state_is_secret_free_and_does_not_store_gateway_url(self):
        self.tenant_action("REGISTER")
        files = list((Path(self.tmp.name) / "data" / "State" / "public-gateway-tenants").glob("*.json"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertNotIn(MASTER, text)
        self.assertNotIn("gateway.example.com", text)
        self.assertNotIn("site_secret", text)
        self.assertNotIn("pull_secret", text)
        self.assertIn(TENANT, text)

    def test_independent_rotations_change_only_the_selected_desktop_credential(self):
        self.tenant_action("REGISTER")
        first_site = self.runtime.reveal_gateway_site_secret(self.company["id"])
        self.assertEqual(first_site["credential_version"], 1)
        self.assertEqual(first_site["site_secret"], derive_versioned_tenant_secret(MASTER, TENANT, purpose="ingress", version=1))

        ingress = self.tenant_action("ROTATE_INGRESS")
        self.assertEqual((ingress["tenant"]["ingress_version"], ingress["tenant"]["pull_version"]), (2, 1))
        second_site = self.runtime.reveal_gateway_site_secret(self.company["id"])
        self.assertEqual(second_site["credential_version"], 2)
        self.assertNotEqual(first_site["site_secret"], second_site["site_secret"])
        self.assertEqual(second_site["site_secret"], derive_versioned_tenant_secret(MASTER, TENANT, purpose="ingress", version=2))

        pull = self.tenant_action("ROTATE_PULL")
        self.assertEqual((pull["tenant"]["ingress_version"], pull["tenant"]["pull_version"]), (2, 2))
        third_site = self.runtime.reveal_gateway_site_secret(self.company["id"])
        self.assertEqual(third_site["site_secret"], second_site["site_secret"])
        self.assertEqual(FakeAdminClient.calls, [
            (TENANT, "REGISTER", None),
            (TENANT, "ROTATE", "ingress"),
            (TENANT, "ROTATE", "pull"),
        ])

    def test_revoke_blocks_site_secret_and_sync_until_explicit_reactivation(self):
        self.tenant_action("REGISTER")
        self.tenant_action("ROTATE_INGRESS")
        self.tenant_action("ROTATE_PULL")
        revoked = self.tenant_action("REVOKE")
        self.assertFalse(revoked["center"]["readiness"]["ready_to_sync"])
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.runtime.reveal_gateway_site_secret(self.company["id"])
        with self.assertRaisesRegex(ValueError, "revoked"):
            self.runtime.sync_public_gateway(self.company["id"])
        active = self.tenant_action("REACTIVATE")
        self.assertTrue(active["center"]["readiness"]["ready_to_sync"])
        self.assertEqual((active["tenant"]["ingress_version"], active["tenant"]["pull_version"]), (3, 3))
        secret = self.runtime.reveal_gateway_site_secret(self.company["id"])
        self.assertEqual(secret["credential_version"], 3)

    def test_versioned_sync_reuses_canonical_w55_intake_before_ack_and_never_mutates_crm(self):
        self.runtime.gateway_tenant_states.upsert_remote(self.company["id"], remote_tenant(ingress=2, pull=2))
        envelope = make_envelope(pull_version=2)
        fake = FakeGatewayClient([envelope])
        self.runtime._gateway_client = lambda company_id: fake
        result = self.runtime.sync_public_gateway(self.company["id"], {"limit": 20})
        self.assertEqual(result["schema"], "binario.marketing.public-gateway-sync.v2")
        self.assertEqual(result["pull_version"], 2)
        self.assertEqual((result["pulled"], result["imported"], result["failed"]), (1, 1, 0))
        self.assertEqual(result["crm_mutations"], 0)
        self.assertEqual(result["provider_mutations"], 0)
        self.assertFalse(result["background_polling"])
        self.assertEqual(fake.ack_calls, [[EVENT]])
        leads = self.runtime.lead_intake.list(self.company["id"])
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].received_at, RECEIVED)
        self.assertEqual(leads[0].source_ref, f"public_gateway:{TENANT}:{EVENT}")
        self.assertEqual(self.runtime.crm.list_contacts(self.company["id"]), [])

    def test_wrong_envelope_version_stays_unacked_and_does_not_write_intake(self):
        self.runtime.gateway_tenant_states.upsert_remote(self.company["id"], remote_tenant(ingress=2, pull=2))
        envelope = make_envelope(pull_version=2)
        envelope["credential_version"] = 1
        fake = FakeGatewayClient([envelope])
        self.runtime._gateway_client = lambda company_id: fake
        result = self.runtime.sync_public_gateway(self.company["id"])
        self.assertEqual((result["imported"], result["failed"]), (0, 1))
        self.assertEqual(fake.ack_calls, [])
        self.assertEqual(self.runtime.lead_intake.list(self.company["id"]), [])
        self.assertEqual(self.runtime.crm.list_contacts(self.company["id"]), [])

    def test_ai_and_learning_payloads_remain_aggregate_and_secret_free(self):
        self.tenant_action("REGISTER")
        context = self.runtime._ai_context(self.company["id"], task="STRATEGY", campaign_id=None, creative_media_id=None)
        learning = self.runtime.learning_payload(self.company["id"])
        text = json.dumps({"context": context, "learning": learning}, ensure_ascii=False)
        self.assertNotIn(MASTER, text)
        self.assertNotIn(TENANT, text)
        self.assertNotIn("gateway.example.com", text)
        self.assertNotIn("site_secret", text)
        self.assertNotIn("pull_secret", text)


if __name__ == "__main__":
    unittest.main()
