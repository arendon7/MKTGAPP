import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from gateway.core import Unauthorized
from gateway.social_api import (
    SOCIAL_ENQUEUE_PATH,
    SOCIAL_STATUS_PATH,
    SOCIAL_STATUS_SCHEMA,
    SocialQueueGatewayService,
    derive_social_secret,
    social_request_headers,
)
from gateway.social_queue import MemorySocialQueueStorage, REMOTE_SOCIAL_JOB_SCHEMA
from gateway.social_supabase_storage import CLAIM_RPC, SupabaseSocialQueueStorage, TABLE


ROOT = Path(__file__).resolve().parents[1]
MASTER = "m" * 64
TENANT_A = "tenant_" + "a" * 24
TENANT_B = "tenant_" + "b" * 24
PUB = "2" * 32
NOW_EPOCH = 1788649200
NOW = datetime.fromtimestamp(NOW_EPOCH, tz=timezone.utc)
NONCE = "c" * 32


def job(publication_id=PUB):
    return json.dumps({
        "schema": REMOTE_SOCIAL_JOB_SCHEMA,
        "publication": {
            "id": publication_id,
            "project_id": "greenatics",
            "channel": "facebook_page",
            "target_id": "page-1",
            "target_name": "Greenatics",
            "kind": "text",
            "message": "Publicación aprobada",
            "link_url": None,
            "media_url": None,
            "scheduled_for": (NOW + timedelta(minutes=10)).isoformat(),
        },
        "approval": {"source_status": "QUEUED", "operator_approved": True},
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def signed(tenant, path, raw, *, nonce=NONCE, timestamp=NOW_EPOCH):
    return social_request_headers(
        MASTER,
        tenant,
        method="POST",
        path=path,
        body=raw,
        timestamp=timestamp,
        nonce=nonce,
    )


class SocialQueueSignedApiTests(unittest.TestCase):
    def setUp(self):
        self.storage = MemorySocialQueueStorage()
        self.service = SocialQueueGatewayService(self.storage, MASTER)

    def test_social_secret_is_tenant_and_purpose_separated(self):
        a = derive_social_secret(MASTER, TENANT_A)
        b = derive_social_secret(MASTER, TENANT_B)
        self.assertRegex(a, r"^[0-9a-f]{64}$")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, MASTER)
        headers = signed(TENANT_A, SOCIAL_ENQUEUE_PATH, job())
        self.assertNotIn(a, json.dumps(headers))
        self.assertNotIn(MASTER, json.dumps(headers))

    def test_signed_enqueue_then_signed_status_is_tenant_scoped_and_sanitized(self):
        raw = job()
        status, receipt = self.service.enqueue(signed(TENANT_A, SOCIAL_ENQUEUE_PATH, raw), raw, now=NOW_EPOCH)
        self.assertEqual(status, 202)
        self.assertEqual(receipt["publication_id"], PUB)

        query = json.dumps({"publication_id": PUB}, separators=(",", ":")).encode("utf-8")
        status, result = self.service.status(signed(TENANT_A, SOCIAL_STATUS_PATH, query), query, now=NOW_EPOCH)
        self.assertEqual(status, 200)
        self.assertEqual(result["schema"], SOCIAL_STATUS_SCHEMA)
        self.assertTrue(result["found"])
        self.assertEqual(result["status"], "PENDING")
        self.assertFalse(result["provider_error_exposed"])
        self.assertFalse(result["lease_exposed"])
        serialized = json.dumps(result).lower()
        self.assertNotIn("lease_token", serialized)
        self.assertNotIn("lease_sha256", serialized)
        self.assertNotIn("body_json", serialized)
        self.assertNotIn("message", serialized)

        other_status, other = self.service.status(signed(TENANT_B, SOCIAL_STATUS_PATH, query), query, now=NOW_EPOCH)
        self.assertEqual(other_status, 404)
        self.assertFalse(other["found"])

    def test_exact_replay_is_safe_because_enqueue_is_publication_idempotent(self):
        raw = job()
        headers = signed(TENANT_A, SOCIAL_ENQUEUE_PATH, raw)
        first_status, first = self.service.enqueue(headers, raw, now=NOW_EPOCH)
        second_status, second = self.service.enqueue(headers, raw, now=NOW_EPOCH)
        self.assertEqual(first_status, 202)
        self.assertEqual(second_status, 200)
        self.assertFalse(first["idempotent_reuse"])
        self.assertTrue(second["idempotent_reuse"])
        self.assertEqual(len(self.storage.rows), 1)

    def test_tampered_body_wrong_path_wrong_signature_and_stale_timestamp_fail(self):
        raw = job()
        headers = signed(TENANT_A, SOCIAL_ENQUEUE_PATH, raw)
        tampered = raw.replace(b"aprobada", b"alterada")
        with self.assertRaises(Unauthorized):
            self.service.enqueue(headers, tampered, now=NOW_EPOCH)

        wrong_path_headers = signed(TENANT_A, SOCIAL_STATUS_PATH, raw)
        with self.assertRaises(Unauthorized):
            self.service.enqueue(wrong_path_headers, raw, now=NOW_EPOCH)

        bad = dict(headers)
        bad["X-Binario-Signature"] = "v1=" + "0" * 64
        with self.assertRaises(Unauthorized):
            self.service.enqueue(bad, raw, now=NOW_EPOCH)

        stale = signed(TENANT_A, SOCIAL_ENQUEUE_PATH, raw, timestamp=NOW_EPOCH - 301)
        with self.assertRaisesRegex(Unauthorized, "timestamp"):
            self.service.enqueue(stale, raw, now=NOW_EPOCH)

    def test_status_requires_exact_small_body(self):
        raw = job()
        self.service.enqueue(signed(TENANT_A, SOCIAL_ENQUEUE_PATH, raw), raw, now=NOW_EPOCH)
        invalid = json.dumps({"publication_id": PUB, "extra": True}).encode("utf-8")
        with self.assertRaisesRegex(Exception, "publication_id only"):
            self.service.status(signed(TENANT_A, SOCIAL_STATUS_PATH, invalid), invalid, now=NOW_EPOCH)

    def test_gateway_layer_contains_zero_meta_provider_authority(self):
        source = (ROOT / "gateway" / "social_api.py").read_text(encoding="utf-8")
        shared = (ROOT / "api" / "_social_shared.py").read_text(encoding="utf-8")
        combined = source + shared
        self.assertNotIn("MetaGraphClient", combined)
        self.assertNotIn("graph.facebook.com", combined)
        self.assertNotIn("publish_now", combined)
        self.assertNotIn("MetaSocialPublisher", combined)
        self.assertNotIn("access_token", combined)


class SocialQueueSupabaseAdapterTests(unittest.TestCase):
    def test_adapter_uses_isolated_table_and_atomic_claim_rpc(self):
        storage = SupabaseSocialQueueStorage("https://example.supabase.co", "server-secret")
        self.assertEqual(TABLE, "binario_social_publish_queue")
        self.assertEqual(CLAIM_RPC, "binario_claim_social_publish_jobs")
        with self.assertRaisesRegex(RuntimeError, "claim_due_atomic"):
            storage.list_due(TENANT_A, NOW.isoformat(), 10)
        with self.assertRaisesRegex(RuntimeError, "lease-bound"):
            storage.replace(object())

    def test_adapter_rejects_insecure_or_credential_bearing_supabase_origin(self):
        for url in ("http://example.supabase.co", "https://user:pass@example.supabase.co", "not-a-url"):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                SupabaseSocialQueueStorage(url, "server-secret")

    @patch("gateway.social_supabase_storage.urlopen")
    def test_service_role_key_stays_only_in_server_request_headers(self, mocked_urlopen):
        response = MagicMock()
        response.read.return_value = b"[]"
        mocked_urlopen.return_value.__enter__.return_value = response
        key = "header.payload.signature"
        storage = SupabaseSocialQueueStorage("https://example.supabase.co", key)
        self.assertIsNone(storage.get(TENANT_A, PUB))
        request = mocked_urlopen.call_args.args[0]
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers["apikey"], key)
        self.assertEqual(headers["authorization"], f"Bearer {key}")
        self.assertNotIn(key, request.full_url)

    @patch("gateway.social_supabase_storage.urlopen")
    def test_atomic_claim_calls_only_claim_rpc_with_server_headers(self, mocked_urlopen):
        response = MagicMock()
        response.read.return_value = b"[]"
        mocked_urlopen.return_value.__enter__.return_value = response
        storage = SupabaseSocialQueueStorage("https://example.supabase.co", "server-secret")
        result = storage.claim_due_atomic(
            TENANT_A,
            "worker_0123456789abcdef",
            now_iso=NOW.isoformat(),
            limit=5,
            lease_seconds=120,
        )
        self.assertEqual(result, [])
        request = mocked_urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/rest/v1/rpc/binario_claim_social_publish_jobs"))
        self.assertEqual(request.method, "POST")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["p_tenant_id"], TENANT_A)
        self.assertEqual(body["p_limit"], 5)
        self.assertNotIn("secret", json.dumps(body).lower())


class SocialQueueHttpSourceContractTests(unittest.TestCase):
    def test_deployed_files_match_signed_paths_and_are_post_only(self):
        enqueue = (ROOT / "api" / "social_enqueue.py").read_text(encoding="utf-8")
        status = (ROOT / "api" / "social_status.py").read_text(encoding="utf-8")
        gateway = (ROOT / "gateway" / "social_api.py").read_text(encoding="utf-8")
        self.assertIn('SOCIAL_ENQUEUE_PATH = "/api/social_enqueue"', gateway)
        self.assertIn('SOCIAL_STATUS_PATH = "/api/social_status"', gateway)
        self.assertIn("def do_POST", enqueue)
        self.assertIn("def do_POST", status)
        self.assertIn("405", enqueue)
        self.assertIn("405", status)
        self.assertNotIn("do_DELETE", enqueue + status)
        self.assertNotIn("do_PATCH", enqueue + status)

    def test_http_endpoints_never_read_social_credentials_or_provider_modules(self):
        combined = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in ("api/_social_shared.py", "api/social_enqueue.py", "api/social_status.py")
        )
        self.assertNotIn("Meta", combined)
        self.assertNotIn("access_token", combined)
        self.assertNotIn("keychain", combined.lower())
        self.assertIn("BINARIO_GATEWAY_MASTER_SECRET", combined)


if __name__ == "__main__":
    unittest.main()
