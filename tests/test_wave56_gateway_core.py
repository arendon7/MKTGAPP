import json
import unittest

from binario_marketing.public_gateway import (
    derive_tenant_secret as desktop_derive,
    request_signature as desktop_request_signature,
)
from gateway.core import (
    Conflict,
    GatewayError,
    GatewayService,
    MemoryQueueStorage,
    Unauthorized,
    canonical_json_bytes,
    derive_tenant_secret,
    request_signature,
)


MASTER = "M" * 48
TENANT = "tenant_" + "a" * 24
EVENT = "evt_" + "b" * 32
NOW = 1787030000


def headers(secret, *, event=EVENT, timestamp=NOW, path="/api/intake", body=b"", nonce=None):
    value = event if nonce is None else nonce
    result = {
        "X-Binario-Tenant": TENANT,
        "X-Binario-Timestamp": str(timestamp),
        "X-Binario-Signature": request_signature(secret, str(timestamp), value, "POST", path, body),
    }
    if nonce is None:
        result["X-Binario-Event"] = event
    else:
        result["X-Binario-Nonce"] = nonce
    return result


def lead_body(*, email="ada@example.com", extra=None):
    payload = {
        "schema": "binario.marketing.public-lead.v1",
        "external_ref": "form-123",
        "lead": {
            "name": "Ada",
            "email": email,
            "source": "website",
            "attribution_capture": {"bm_tid": "bm_" + "1" * 24},
        },
    }
    if extra:
        payload["lead"].update(extra)
    return canonical_json_bytes(payload)


class Wave56GatewayCoreTests(unittest.TestCase):
    def setUp(self):
        self.storage = MemoryQueueStorage()
        self.service = GatewayService(self.storage, MASTER)
        self.ingress = derive_tenant_secret(MASTER, TENANT, purpose="ingress")
        self.pull = derive_tenant_secret(MASTER, TENANT, purpose="pull")

    def test_fixed_signature_vector_matches_desktop_and_remote_implementation(self):
        payload = {"schema": "binario.marketing.public-lead.v1", "lead": {"name": "Ada", "email": "ada@example.com"}}
        body = canonical_json_bytes(payload)
        self.assertEqual(self.ingress, "b6f145bb1b40f0616013f461e88fab555b5d51a7209efbbeffb1cb08fe977d89")
        expected = "v1=c71cbafc9d8670c29890ccf65f1d16c44940877356bdafcd12db7ef11d1bdc49"
        remote = request_signature(self.ingress, str(NOW), EVENT, "POST", "/api/intake", body)
        desktop_secret = desktop_derive(MASTER, TENANT, purpose="ingress")
        desktop = desktop_request_signature(desktop_secret, str(NOW), EVENT, "POST", "/api/intake", body)
        self.assertEqual(remote, expected)
        self.assertEqual(desktop, expected)

    def test_valid_ingest_is_accepted_and_exact_replay_is_idempotent(self):
        body = lead_body()
        signed = headers(self.ingress, body=body)
        status, receipt = self.service.ingest(signed, body, now=NOW)
        self.assertEqual(status, 202)
        self.assertFalse(receipt["idempotent_reuse"])
        status, reused = self.service.ingest(signed, body, now=NOW)
        self.assertEqual(status, 200)
        self.assertTrue(reused["idempotent_reuse"])
        self.assertEqual(len(self.storage.rows), 1)

    def test_same_event_with_different_payload_fails_closed(self):
        first = lead_body(email="one@example.com")
        self.service.ingest(headers(self.ingress, body=first), first, now=NOW)
        second = lead_body(email="two@example.com")
        with self.assertRaisesRegex(Conflict, "different payload"):
            self.service.ingest(headers(self.ingress, body=second), second, now=NOW)
        self.assertEqual(len(self.storage.rows), 1)

    def test_stale_timestamp_and_wrong_signature_are_unauthorized(self):
        body = lead_body()
        with self.assertRaisesRegex(Unauthorized, "outside allowed window"):
            self.service.ingest(headers(self.ingress, body=body, timestamp=NOW - 301), body, now=NOW)
        bad = headers(self.ingress, body=body)
        bad["X-Binario-Signature"] = "v1=" + "0" * 64
        with self.assertRaisesRegex(Unauthorized, "invalid request signature"):
            self.service.ingest(bad, body, now=NOW)
        self.assertEqual(len(self.storage.rows), 0)

    def test_secret_bearing_fields_and_overwide_public_shape_are_rejected(self):
        body = lead_body(extra={"password": "do-not-store"})
        signed = headers(self.ingress, body=body)
        with self.assertRaises(GatewayError):
            self.service.ingest(signed, body, now=NOW)
        payload = {"schema": "binario.marketing.public-lead.v1", "lead": {"name": "A", "unexpected": "x"}}
        body = canonical_json_bytes(payload)
        with self.assertRaisesRegex(GatewayError, "unsupported lead fields"):
            self.service.ingest(headers(self.ingress, event="evt_" + "c" * 32, body=body), body, now=NOW)

    def test_pull_returns_signed_envelope_then_ack_redacts_remote_pii(self):
        body = lead_body()
        self.service.ingest(headers(self.ingress, body=body), body, now=NOW)
        pull_body = canonical_json_bytes({"limit": 10})
        nonce = "d" * 32
        status, batch = self.service.pull(
            headers(self.pull, path="/api/pull", body=pull_body, nonce=nonce), pull_body, now=NOW,
        )
        self.assertEqual(status, 200)
        self.assertEqual(batch["schema"], "binario.marketing.public-intake-pull.v1")
        self.assertEqual(batch["count"], 1)
        envelope = batch["events"][0]
        self.assertEqual(envelope["schema"], "binario.marketing.public-intake-envelope.v1")
        self.assertTrue(envelope["signature"].startswith("v1="))
        self.assertEqual(envelope["payload"]["lead"]["email"], "ada@example.com")

        ack_body = canonical_json_bytes({"event_ids": [EVENT]})
        ack_nonce = "e" * 32
        status, ack = self.service.ack(
            headers(self.pull, path="/api/ack", body=ack_body, nonce=ack_nonce), ack_body, now=NOW,
        )
        self.assertEqual(status, 200)
        self.assertEqual(ack["acked"], 1)
        self.assertTrue(ack["payloads_redacted"])
        row = self.storage.get_event(TENANT, EVENT)
        self.assertEqual(row.status, "ACKED")
        self.assertIsNone(row.payload)
        self.assertEqual(len(row.payload_sha256), 64)

    def test_expiry_redacts_pending_payload_without_background_worker(self):
        body = lead_body()
        self.service.ingest(headers(self.ingress, body=body), body, now=NOW)
        future = NOW + 30 * 24 * 3600 + 1
        pull_body = canonical_json_bytes({"limit": 10})
        nonce = "f" * 32
        _, batch = self.service.pull(
            headers(self.pull, timestamp=future, path="/api/pull", body=pull_body, nonce=nonce),
            pull_body,
            now=future,
        )
        self.assertEqual(batch["count"], 0)
        row = self.storage.get_event(TENANT, EVENT)
        self.assertEqual(row.status, "EXPIRED")
        self.assertIsNone(row.payload)


if __name__ == "__main__":
    unittest.main()
