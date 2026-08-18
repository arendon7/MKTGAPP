from __future__ import annotations

import unittest

from binario_marketing.public_gateway import derive_tenant_secret as wave56_desktop_derive
from binario_marketing.public_gateway_wave58 import derive_versioned_tenant_secret as desktop_derive
from gateway.core import MemoryQueueStorage, Unauthorized, canonical_json_bytes, request_signature
from gateway.tenant_admin import ADMIN_PATH, TenantAdminService
from gateway.tenant_registry import MemoryTenantCredentialRegistry, derive_admin_secret
from gateway.versioned_service import VersionedGatewayService, derive_versioned_tenant_secret


MASTER = "M" * 48
TENANT = "tenant_" + "a" * 24
NOW = 1787030000


def lead_body(name="Ada"):
    return canonical_json_bytes({
        "schema": "binario.marketing.public-lead.v1",
        "external_ref": "wave58-test",
        "lead": {"name": name, "email": "ada@example.com", "source": "website"},
    })


def gateway_headers(secret, *, purpose, version, body, event_hex="b", nonce_hex="d", now=NOW, path=None):
    if purpose == "ingress":
        event = "evt_" + event_hex * 32
        signed_nonce = event
        path = path or "/api/intake"
    else:
        signed_nonce = nonce_hex * 32
        path = path or "/api/pull"
    headers = {
        "X-Binario-Tenant": TENANT,
        "X-Binario-Timestamp": str(now),
        "X-Binario-Credential-Version": str(version),
        "X-Binario-Signature": request_signature(secret, str(now), signed_nonce, "POST", path, body),
    }
    if purpose == "ingress":
        headers["X-Binario-Event"] = signed_nonce
    else:
        headers["X-Binario-Nonce"] = signed_nonce
    return headers


def admin_headers(secret, body, *, now=NOW, nonce="e" * 32):
    return {
        "X-Binario-Admin-Timestamp": str(now),
        "X-Binario-Admin-Nonce": nonce,
        "X-Binario-Admin-Signature": request_signature(secret, str(now), nonce, "POST", ADMIN_PATH, body),
    }


class Wave58TenantCredentialTests(unittest.TestCase):
    def setUp(self):
        self.queue = MemoryQueueStorage()
        self.registry = MemoryTenantCredentialRegistry()
        self.registry.register(TENANT)
        self.service = VersionedGatewayService(self.queue, MASTER, self.registry)

    def secret(self, purpose, version):
        return derive_versioned_tenant_secret(MASTER, TENANT, purpose=purpose, version=version)

    def test_version_one_is_exact_wave56_contract_and_desktop_matches_remote(self):
        expected = "b6f145bb1b40f0616013f461e88fab555b5d51a7209efbbeffb1cb08fe977d89"
        self.assertEqual(wave56_desktop_derive(MASTER, TENANT, purpose="ingress"), expected)
        self.assertEqual(derive_versioned_tenant_secret(MASTER, TENANT, purpose="ingress", version=1), expected)
        self.assertEqual(desktop_derive(MASTER, TENANT, purpose="ingress", version=1), expected)
        v2 = derive_versioned_tenant_secret(MASTER, TENANT, purpose="ingress", version=2)
        self.assertEqual(v2, desktop_derive(MASTER, TENANT, purpose="ingress", version=2))
        self.assertNotEqual(v2, expected)

    def test_unregistered_tenant_is_rejected_before_queue_mutation(self):
        other = "tenant_" + "f" * 24
        secret = derive_versioned_tenant_secret(MASTER, other, purpose="ingress", version=1)
        body = lead_body()
        event = "evt_" + "b" * 32
        headers = {
            "X-Binario-Tenant": other,
            "X-Binario-Timestamp": str(NOW),
            "X-Binario-Credential-Version": "1",
            "X-Binario-Event": event,
            "X-Binario-Signature": request_signature(secret, str(NOW), event, "POST", "/api/intake", body),
        }
        with self.assertRaisesRegex(Unauthorized, "not registered"):
            self.service.ingest(headers, body, now=NOW)
        self.assertEqual(self.queue.rows, {})

    def test_rotate_ingress_invalidates_only_old_ingress_and_pull_v1_still_works(self):
        first = lead_body("First")
        self.service.ingest(gateway_headers(self.secret("ingress", 1), purpose="ingress", version=1, body=first), first, now=NOW)
        row = self.registry.rotate(TENANT, "ingress")
        self.assertEqual((row.ingress_version, row.pull_version), (2, 1))

        stale = lead_body("Stale")
        with self.assertRaisesRegex(Unauthorized, "stale"):
            self.service.ingest(
                gateway_headers(self.secret("ingress", 1), purpose="ingress", version=1, body=stale, event_hex="c"),
                stale,
                now=NOW,
            )
        fresh = lead_body("Fresh")
        status, receipt = self.service.ingest(
            gateway_headers(self.secret("ingress", 2), purpose="ingress", version=2, body=fresh, event_hex="c"),
            fresh,
            now=NOW,
        )
        self.assertEqual(status, 202)
        self.assertEqual(receipt["credential_version"], 2)

        pull_body = canonical_json_bytes({"limit": 10})
        status, batch = self.service.pull(
            gateway_headers(self.secret("pull", 1), purpose="pull", version=1, body=pull_body),
            pull_body,
            now=NOW,
        )
        self.assertEqual(status, 200)
        self.assertEqual(batch["credential_version"], 1)
        self.assertEqual(batch["count"], 2)

    def test_rotate_pull_invalidates_only_old_pull_and_current_ingress_still_works(self):
        self.registry.rotate(TENANT, "ingress")
        row = self.registry.rotate(TENANT, "pull")
        self.assertEqual((row.ingress_version, row.pull_version), (2, 2))
        pull_body = canonical_json_bytes({"limit": 10})
        with self.assertRaisesRegex(Unauthorized, "stale"):
            self.service.pull(
                gateway_headers(self.secret("pull", 1), purpose="pull", version=1, body=pull_body),
                pull_body,
                now=NOW,
            )
        _, batch = self.service.pull(
            gateway_headers(self.secret("pull", 2), purpose="pull", version=2, body=pull_body),
            pull_body,
            now=NOW,
        )
        self.assertEqual(batch["credential_version"], 2)

        body = lead_body("Ingress survives pull rotation")
        status, receipt = self.service.ingest(
            gateway_headers(self.secret("ingress", 2), purpose="ingress", version=2, body=body, event_hex="c"),
            body,
            now=NOW,
        )
        self.assertEqual(status, 202)
        self.assertEqual(receipt["credential_version"], 2)

    def test_revoke_blocks_ingress_pull_and_ack_then_reactivate_invalidates_all_old_keys(self):
        self.registry.rotate(TENANT, "ingress")
        self.registry.rotate(TENANT, "pull")
        self.registry.revoke(TENANT)
        body = lead_body("Blocked")
        with self.assertRaisesRegex(Unauthorized, "revoked"):
            self.service.ingest(
                gateway_headers(self.secret("ingress", 2), purpose="ingress", version=2, body=body), body, now=NOW,
            )
        pull_body = canonical_json_bytes({"limit": 10})
        with self.assertRaisesRegex(Unauthorized, "revoked"):
            self.service.pull(
                gateway_headers(self.secret("pull", 2), purpose="pull", version=2, body=pull_body), pull_body, now=NOW,
            )
        ack_body = canonical_json_bytes({"event_ids": ["evt_" + "b" * 32]})
        with self.assertRaisesRegex(Unauthorized, "revoked"):
            self.service.ack(
                gateway_headers(self.secret("pull", 2), purpose="pull", version=2, body=ack_body, path="/api/ack"), ack_body, now=NOW,
            )

        active = self.registry.reactivate(TENANT)
        self.assertEqual((active.ingress_version, active.pull_version), (3, 3))
        with self.assertRaisesRegex(Unauthorized, "stale"):
            self.service.ingest(
                gateway_headers(self.secret("ingress", 2), purpose="ingress", version=2, body=body), body, now=NOW,
            )
        status, receipt = self.service.ingest(
            gateway_headers(self.secret("ingress", 3), purpose="ingress", version=3, body=body), body, now=NOW,
        )
        self.assertEqual(status, 202)
        self.assertEqual(receipt["credential_version"], 3)

    def test_registry_actions_are_idempotent_where_safe_and_audited(self):
        again = self.registry.register(TENANT)
        self.assertEqual((again.ingress_version, again.pull_version), (1, 1))
        self.registry.rotate(TENANT, "ingress")
        revoked = self.registry.revoke(TENANT)
        self.assertEqual(self.registry.revoke(TENANT), revoked)
        active = self.registry.reactivate(TENANT)
        self.assertEqual(self.registry.reactivate(TENANT), active)
        actions = [row["action"] for row in self.registry.audit]
        self.assertEqual(actions, ["REGISTER", "ROTATE_INGRESS", "REVOKE", "REACTIVATE"])
        self.assertEqual((active.ingress_version, active.pull_version), (3, 2))

    def test_admin_key_is_separate_from_site_and_pull_keys_and_response_is_secret_free(self):
        registry = MemoryTenantCredentialRegistry()
        admin = TenantAdminService(registry, MASTER)
        admin_secret = derive_admin_secret(MASTER)
        body = canonical_json_bytes({"action": "REGISTER", "tenant_id": TENANT})
        status, result = admin.execute(admin_headers(admin_secret, body), body, now=NOW)
        self.assertEqual(status, 201)
        self.assertFalse(result["secret_returned"])
        self.assertFalse(result["master_secret_returned"])
        self.assertNotIn(MASTER, str(result))
        self.assertNotIn(admin_secret, str(result))

        _, reused = admin.execute(admin_headers(admin_secret, body), body, now=NOW)
        self.assertTrue(reused["idempotent"])
        for wrong in (
            derive_versioned_tenant_secret(MASTER, TENANT, purpose="ingress", version=1),
            derive_versioned_tenant_secret(MASTER, TENANT, purpose="pull", version=1),
        ):
            with self.assertRaisesRegex(Unauthorized, "admin signature"):
                admin.execute(admin_headers(wrong, body), body, now=NOW)
        with self.assertRaisesRegex(Unauthorized, "outside allowed window"):
            admin.execute(admin_headers(admin_secret, body, now=NOW - 301), body, now=NOW)


if __name__ == "__main__":
    unittest.main()
