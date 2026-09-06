import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from gateway.core import canonical_json_bytes
from gateway.social_queue import REMOTE_SOCIAL_JOB_SCHEMA
from gateway.social_supabase_storage import (
    BEGIN_EFFECT_RPC,
    CLAIM_RPC,
    COMPLETE_RPC,
    FAIL_RPC,
    SupabaseSocialQueueStorage,
)
from binario_marketing.cloud_social_worker import (
    CloudSocialWorker,
    CloudSocialWorkerError,
    WORKER_RESULT_SCHEMA,
    parse_worker_tenants,
)
from binario_marketing.meta_graph import MetaGraphError


ROOT = Path(__file__).resolve().parents[1]
TENANT = "tenant_" + "a" * 24
PUB = "3" * 32
TOKEN = "4" * 64
NOW = datetime(2026, 9, 5, 23, 50, tzinfo=timezone.utc)


def publication(*, channel="facebook_page", kind="text", media_url=None):
    return {
        "schema": REMOTE_SOCIAL_JOB_SCHEMA,
        "publication": {
            "id": PUB,
            "project_id": "greenatics",
            "channel": channel,
            "target_id": "page-1" if channel == "facebook_page" else "ig-1",
            "target_name": "Greenatics",
            "kind": kind,
            "message": "Contenido aprobado",
            "link_url": "https://greenatics.co/oferta" if kind == "link" else None,
            "media_url": media_url,
            "scheduled_for": NOW.isoformat(),
        },
        "approval": {"source_status": "QUEUED", "operator_approved": True},
    }


def lease(body=None, *, digest=None):
    body = body or publication()
    return {
        "tenant_id": TENANT,
        "publication_id": PUB,
        "body_json": body,
        "body_sha256": digest or hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
        "attempt": 1,
        "lease_token": TOKEN,
        "lease_expires_at": "2026-09-05T23:55:00+00:00",
    }


class FakeStorage:
    def __init__(self, leases=None, *, fail_complete=False, fail_begin=False):
        self.leases = list(leases or [])
        self.fail_complete = fail_complete
        self.fail_begin = fail_begin
        self.events = []

    def claim_due_atomic(self, tenant_id, worker_id, *, now_iso, limit, lease_seconds):
        self.events.append(("claim", tenant_id, limit, lease_seconds))
        rows, self.leases = self.leases, []
        return rows

    def begin_provider_effect_atomic(self, tenant_id, publication_id, lease_token, *, now_iso):
        self.events.append(("begin", publication_id))
        if self.fail_begin:
            raise RuntimeError("checkpoint unavailable")

    def mark_published_atomic(self, tenant_id, publication_id, lease_token, remote_id, *, now_iso):
        self.events.append(("complete", publication_id, remote_id))
        if self.fail_complete:
            raise RuntimeError("completion unavailable")

    def mark_failed_atomic(self, tenant_id, publication_id, lease_token, error, *, retryable, now_iso):
        self.events.append(("fail", publication_id, retryable, error))
        return {"status": "FAILED", "provider_outcome_ambiguous": True}


class FakeMeta:
    def __init__(self, events, *, fail=False, instagram_statuses=None):
        self.events = events
        self.fail = fail
        self.instagram_statuses = list(instagram_statuses or ["FINISHED"])

    def publish_page_feed(self, page_id, message, link_url=None):
        self.events.append(("provider", "feed", page_id))
        if self.fail:
            raise MetaGraphError("provider detail must not be persisted")
        return "fb_123"

    def publish_page_photo(self, page_id, image_url, caption=""):
        self.events.append(("provider", "photo", page_id))
        if self.fail:
            raise MetaGraphError("provider detail must not be persisted")
        return "fb_photo_123"

    def create_instagram_container(self, instagram_id, media_url, caption, kind):
        self.events.append(("provider", "ig_create", instagram_id, kind))
        if self.fail:
            raise MetaGraphError("provider detail must not be persisted")
        return "container_1"

    def instagram_container_status(self, container_id, instagram_id):
        self.events.append(("provider", "ig_status", instagram_id))
        return self.instagram_statuses.pop(0) if self.instagram_statuses else "FINISHED"

    def publish_instagram_container(self, instagram_id, container_id):
        self.events.append(("provider", "ig_publish", instagram_id))
        return "ig_media_123"


class CloudSocialWorkerTests(unittest.TestCase):
    def worker(self, storage, client, *, enabled=True):
        return CloudSocialWorker(
            storage,
            lambda: client,
            (TENANT,),
            enabled=enabled,
            sleep=lambda _: None,
            instagram_poll_interval=0,
            clock=lambda: NOW,
        )

    def test_disabled_worker_never_claims_or_resolves_provider(self):
        storage = FakeStorage([lease()])
        called = []
        worker = CloudSocialWorker(storage, lambda: called.append(True), (TENANT,), enabled=False, clock=lambda: NOW)
        result = worker.run_once()
        self.assertEqual(result["schema"], WORKER_RESULT_SCHEMA)
        self.assertEqual(result["status"], "DISABLED")
        self.assertEqual(storage.events, [])
        self.assertEqual(called, [])

    def test_provider_configuration_is_resolved_before_claim(self):
        storage = FakeStorage([lease()])
        worker = CloudSocialWorker(
            storage,
            lambda: (_ for _ in ()).throw(ValueError("missing token")),
            (TENANT,),
            enabled=True,
            clock=lambda: NOW,
        )
        result = worker.run_once()
        self.assertEqual(result["status"], "PROVIDER_CONFIGURATION_BLOCKED")
        self.assertEqual(storage.events, [])
        self.assertEqual(result["claimed"], 0)

    def test_happy_path_checkpoints_before_meta_and_completes_once(self):
        storage = FakeStorage([lease()])
        provider_events = []
        client = FakeMeta(provider_events)
        result = self.worker(storage, client).run_once()
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["published"], 1)
        self.assertEqual(storage.events[0][0], "claim")
        self.assertEqual(storage.events[1], ("begin", PUB))
        self.assertEqual(provider_events, [("provider", "feed", "page-1")])
        self.assertEqual(storage.events[2], ("complete", PUB, "fb_123"))
        self.assertFalse(any(event[0] == "fail" for event in storage.events))

    def test_provider_failure_after_checkpoint_is_terminal_ambiguous_and_not_retried(self):
        storage = FakeStorage([lease()])
        client = FakeMeta([], fail=True)
        result = self.worker(storage, client).run_once()
        self.assertEqual(result["status"], "MANUAL_RECONCILIATION_REQUIRED")
        self.assertEqual(result["failed_ambiguous"], 1)
        failure = next(event for event in storage.events if event[0] == "fail")
        self.assertFalse(failure[2])
        self.assertEqual(failure[3], "provider: MetaGraphError")
        self.assertNotIn("provider detail", json.dumps(storage.events))

    def test_completion_failure_never_calls_provider_or_failure_checkpoint_twice(self):
        storage = FakeStorage([lease()], fail_complete=True)
        provider_events = []
        result = self.worker(storage, FakeMeta(provider_events)).run_once()
        self.assertEqual(result["status"], "MANUAL_RECONCILIATION_REQUIRED")
        self.assertEqual(result["completion_ambiguous"], 1)
        self.assertEqual(len(provider_events), 1)
        self.assertFalse(any(event[0] == "fail" for event in storage.events))

    def test_begin_checkpoint_failure_performs_zero_provider_calls(self):
        storage = FakeStorage([lease()], fail_begin=True)
        provider_events = []
        result = self.worker(storage, FakeMeta(provider_events)).run_once()
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["invalid_or_blocked"], 1)
        self.assertEqual(provider_events, [])
        self.assertFalse(any(event[0] in {"complete", "fail"} for event in storage.events))

    def test_digest_corruption_fails_before_provider_checkpoint(self):
        storage = FakeStorage([lease(digest="0" * 64)])
        provider_events = []
        result = self.worker(storage, FakeMeta(provider_events)).run_once()
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(provider_events, [])
        self.assertFalse(any(event[0] == "begin" for event in storage.events))
        failure = next(event for event in storage.events if event[0] == "fail")
        self.assertEqual(failure[3], "lease-validation: CloudSocialWorkerError")

    def test_instagram_reel_uses_existing_meta_client_contract_under_one_effect_checkpoint(self):
        body = publication(channel="instagram", kind="reel", media_url="https://cdn.example.com/reel.mp4")
        storage = FakeStorage([lease(body)])
        provider_events = []
        client = FakeMeta(provider_events, instagram_statuses=["IN_PROGRESS", "FINISHED"])
        result = self.worker(storage, client).run_once()
        self.assertEqual(result["published"], 1)
        self.assertEqual(storage.events[1], ("begin", PUB))
        self.assertEqual([event[1] for event in provider_events], ["ig_create", "ig_status", "ig_status", "ig_publish"])
        self.assertEqual(storage.events[-1], ("complete", PUB, "ig_media_123"))

    def test_tenant_allowlist_is_explicit_bounded_and_deduplicated(self):
        self.assertEqual(parse_worker_tenants(f"{TENANT},{TENANT}"), (TENANT,))
        with self.assertRaises(CloudSocialWorkerError):
            parse_worker_tenants("tenant_bad")
        with self.assertRaises(CloudSocialWorkerError):
            CloudSocialWorker(FakeStorage(), lambda: FakeMeta([]), (), enabled=True)


class SocialWorkerSqlAndAdapterContractTests(unittest.TestCase):
    def test_sql_marks_expired_provider_started_lease_failed_not_pending(self):
        sql = (ROOT / "gateway" / "supabase" / "003_social_worker_execution.sql").read_text(encoding="utf-8")
        self.assertIn("provider_started_at", sql)
        self.assertIn("provider_outcome_ambiguous", sql)
        self.assertIn("manual reconciliation required", sql)
        self.assertIn("when q.provider_started_at is not null then 'FAILED'", sql)
        self.assertIn("binario_begin_social_provider_effect", sql)
        self.assertIn("binario_complete_social_publish_job", sql)
        self.assertIn("binario_fail_social_publish_job", sql)
        self.assertIn("grant execute", sql.lower())
        self.assertIn("to service_role", sql.lower())
        self.assertIn("from public, anon, authenticated", sql.lower())
        self.assertNotIn("access_token", sql)

    @patch.object(SupabaseSocialQueueStorage, "_request")
    def test_adapter_uses_only_lease_bound_execution_rpcs(self, request):
        storage = SupabaseSocialQueueStorage("https://example.supabase.co", "server-secret")
        request.return_value = True
        storage.begin_provider_effect_atomic(TENANT, PUB, TOKEN, now_iso=NOW.isoformat())
        self.assertEqual(request.call_args.args[1], f"rpc/{BEGIN_EFFECT_RPC}")
        storage.mark_published_atomic(TENANT, PUB, TOKEN, "remote-1", now_iso=NOW.isoformat())
        self.assertEqual(request.call_args.args[1], f"rpc/{COMPLETE_RPC}")
        request.return_value = [{"status": "FAILED", "attempts": 1, "available_at": NOW.isoformat(), "provider_outcome_ambiguous": True}]
        row = storage.mark_failed_atomic(TENANT, PUB, TOKEN, "provider: MetaGraphError", retryable=False, now_iso=NOW.isoformat())
        self.assertTrue(row["provider_outcome_ambiguous"])
        self.assertEqual(request.call_args.args[1], f"rpc/{FAIL_RPC}")
        with self.assertRaises(RuntimeError):
            storage.replace(object())

    def test_worker_is_one_shot_and_contains_no_public_http_or_daemon_loop(self):
        source = (ROOT / "src" / "binario_marketing" / "cloud_social_worker.py").read_text(encoding="utf-8")
        self.assertIn("MetaGraphClient.from_env", source)
        self.assertIn("def run_once", source)
        self.assertNotIn("BaseHTTPRequestHandler", source)
        self.assertNotIn("threading.Thread", source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("access_token", source)
        self.assertNotIn("SUPABASE_SECRET_KEY", source)
        self.assertIn("BINARIO_SOCIAL_WORKER_ENABLED", source)
        self.assertIn("BINARIO_SOCIAL_WORKER_TENANTS", source)

    def test_existing_claim_rpc_name_is_preserved(self):
        self.assertEqual(CLAIM_RPC, "binario_claim_social_publish_jobs")


if __name__ == "__main__":
    unittest.main()
