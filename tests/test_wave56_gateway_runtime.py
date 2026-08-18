import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.public_gateway import (
    GatewayCredentialStore,
    body_sha256,
    derive_tenant_secret,
    envelope_signature,
)
from binario_marketing.service_wave56_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]
MASTER = "wave56-master-secret-" + "x" * 40
TENANT = "tenant_" + "a" * 24
EVENT = "evt_" + "b" * 32
RECEIVED = "2026-08-18T13:20:30+00:00"


def make_envelope(master, lead, *, event_id=EVENT, received_at=RECEIVED, tenant_id=TENANT):
    payload = {"schema": "binario.marketing.public-lead.v1", "external_ref": "site-submission-1", "lead": lead}
    digest = body_sha256(payload)
    pull = derive_tenant_secret(master, tenant_id, purpose="pull")
    return {
        "schema": "binario.marketing.public-intake-envelope.v1",
        "tenant_id": tenant_id,
        "event_id": event_id,
        "received_at": received_at,
        "payload": payload,
        "payload_sha256": digest,
        "signature": envelope_signature(pull, tenant_id, event_id, received_at, digest),
    }


class FakeGatewayClient:
    def __init__(self, events):
        self.events = list(events)
        self.pull_limits = []
        self.ack_calls = []

    def pull(self, *, limit=100):
        self.pull_limits.append(limit)
        return list(self.events)[:limit]

    def ack(self, event_ids):
        self.ack_calls.append(list(event_ids))
        return {"schema": "binario.marketing.public-intake-ack.v1", "requested": len(event_ids), "acked": len(event_ids)}


class Wave56GatewayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BINARIO_GATEWAY_MASTER_SECRET": MASTER}, clear=False)
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.configure_public_gateway(self.company["id"], {
            "gateway_url": "https://gateway.example.com",
            "tenant_id": TENANT,
        })

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()
        self.env.stop()

    def test_gateway_config_is_secret_free_and_credential_status_never_echoes_master(self):
        center = self.runtime.public_gateway_payload(self.company["id"])
        self.assertTrue(center["readiness"]["ready_to_sync"])
        self.assertEqual(center["credential"]["source"], "environment")
        text = json.dumps(center, ensure_ascii=False)
        self.assertNotIn(MASTER, text)
        stored = list((Path(self.tmp.name) / "data" / "State" / "public-gateway").glob("*.json"))
        self.assertEqual(len(stored), 1)
        self.assertNotIn(MASTER, stored[0].read_text(encoding="utf-8"))
        self.assertFalse(center["safety"]["master_secret_persisted_in_json"])
        self.assertFalse(center["protocol"]["browser_secret_supported"])

    def test_keychain_gateway_namespace_reads_and_writes_without_argv_secret(self):
        root = Path(self.tmp.name) / "keychain"
        root.mkdir()
        helper = root / "helper"
        state = root / "state"
        state.mkdir()
        helper.write_text(
            "#!/bin/sh\nset -eu\n"
            f"ROOT='{state}'\nCMD=${{1:-status}}\nNS=${{2:-meta}}\n"
            "[ \"$NS\" = gateway ] || exit 2\nFILE=\"$ROOT/$NS\"\n"
            "case \"$CMD\" in\n"
            "get) [ -f \"$FILE\" ] || exit 3; cat \"$FILE\";;\n"
            "set) cat > \"$FILE\"; echo ok;;\n"
            "delete) rm -f \"$FILE\"; echo ok;;\n"
            "status) [ -f \"$FILE\" ] && echo configured || echo missing;;\n"
            "*) exit 64;; esac\n",
            encoding="utf-8",
        )
        helper.chmod(0o755)
        with patch.dict(os.environ, {"BINARIO_GATEWAY_MASTER_SECRET": ""}, clear=False):
            store = GatewayCredentialStore(helper)
            self.assertFalse(store.status().configured)
            store.write(MASTER)
            self.assertEqual(store.read(), MASTER)
            self.assertTrue(store.status().configured)
            store.delete()
            self.assertIsNone(store.read())

    def test_explicit_sync_imports_signed_event_without_crm_mutation_and_preserves_receive_time(self):
        envelope = make_envelope(MASTER, {"name": "Ada", "email": "ada@example.com", "source": "landing"})
        fake = FakeGatewayClient([envelope])
        self.runtime._gateway_client = lambda company_id: fake
        result = self.runtime.sync_public_gateway(self.company["id"], {"limit": 20})
        self.assertEqual(result["pulled"], 1)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["crm_mutations"], 0)
        self.assertEqual(fake.ack_calls, [[EVENT]])
        rows = self.runtime.lead_intake.list(self.company["id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].received_at, RECEIVED)
        self.assertEqual(rows[0].source_ref, f"public_gateway:{TENANT}:{EVENT}")
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)
        self.assertFalse(result["background_polling"])

    def test_tampered_envelope_is_not_written_or_acked(self):
        envelope = make_envelope(MASTER, {"name": "Ada", "email": "ada@example.com"})
        envelope["signature"] = "v1=" + "0" * 64
        fake = FakeGatewayClient([envelope])
        self.runtime._gateway_client = lambda company_id: fake
        result = self.runtime.sync_public_gateway(self.company["id"])
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(fake.ack_calls, [])
        self.assertEqual(len(self.runtime.lead_intake.list(self.company["id"])), 0)
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)

    def test_invalid_bm_tid_is_rejected_locally_and_event_remains_unacked(self):
        envelope = make_envelope(MASTER, {
            "name": "Atribución falsa",
            "email": "fake@example.com",
            "attribution_capture": {"bm_tid": "bm_" + "f" * 24},
        })
        fake = FakeGatewayClient([envelope])
        self.runtime._gateway_client = lambda company_id: fake
        result = self.runtime.sync_public_gateway(self.company["id"])
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(fake.ack_calls, [])
        self.assertEqual(len(self.runtime.lead_intake.list(self.company["id"])), 0)

    def test_canonical_bm_tid_is_verified_before_ack_and_reimport_is_idempotent(self):
        campaign = self.runtime.create_campaign(self.company["id"], {"name": "Gateway Leads", "objective": "LEADS"})
        link = self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": campaign["id"],
            "destination_url": "https://example.com/form",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
        })
        envelope = make_envelope(MASTER, {
            "name": "Atribuido",
            "email": "attributed@example.com",
            "attribution_capture": {
                "bm_tid": link["tracking_code"],
                "utm_source": "instagram",
                "utm_medium": "paid_social",
            },
        })
        fake = FakeGatewayClient([envelope])
        self.runtime._gateway_client = lambda company_id: fake
        first = self.runtime.sync_public_gateway(self.company["id"])
        second = self.runtime.sync_public_gateway(self.company["id"])
        self.assertEqual(first["imported"], 1)
        self.assertEqual(second["imported"], 1)
        self.assertEqual(len(self.runtime.lead_intake.list(self.company["id"])), 1)
        row = self.runtime.lead_intake.list(self.company["id"])[0]
        self.assertEqual(row.tracking_code, link["tracking_code"])
        self.assertEqual(row.received_at, RECEIVED)
        self.assertEqual(fake.ack_calls, [[EVENT], [EVENT]])
        self.assertTrue(second["results"][0]["idempotent_reuse"])

    def test_ai_context_exposes_only_gateway_aggregate_flags(self):
        private = self.runtime.intake_lead(self.company["id"], {
            "connector": "API_IMPORT", "name": "Privado", "email": "private@example.com"
        })
        context = self.runtime._ai_context(self.company["id"], task="STRATEGY", campaign_id=None, creative_media_id=None)
        text = json.dumps(context, ensure_ascii=False)
        self.assertIn("public_gateway", context)
        self.assertNotIn("https://gateway.example.com", text)
        self.assertNotIn(TENANT, text)
        self.assertNotIn(MASTER, text)
        self.assertNotIn("Privado", text)
        self.assertNotIn("private@example.com", text)
        self.assertNotIn(private["id"], text)
        self.assertFalse(context["public_gateway"]["privacy"]["lead_payloads_included"])


if __name__ == "__main__":
    unittest.main()
