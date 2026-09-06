from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Callable, Protocol

from gateway.core import TENANT_ID_RE, canonical_json_bytes
from gateway.social_queue import REMOTE_SOCIAL_JOB_SCHEMA, validate_remote_social_job
from gateway.social_supabase_storage import SupabaseSocialQueueStorage

from .meta_graph import MetaGraphClient, MetaGraphError


WORKER_RESULT_SCHEMA = "binario.marketing.cloud-social-worker-result.v1"
LEASE_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_TENANTS = 50
MAX_LIMIT_PER_TENANT = 10
DEFAULT_LEASE_SECONDS = 300


class CloudSocialWorkerError(RuntimeError):
    pass


class DistributedSocialStorage(Protocol):
    def claim_due_atomic(self, tenant_id: str, worker_id: str, *, now_iso: str, limit: int, lease_seconds: int) -> list[dict]: ...
    def begin_provider_effect_atomic(self, tenant_id: str, publication_id: str, lease_token: str, *, now_iso: str) -> None: ...
    def mark_published_atomic(self, tenant_id: str, publication_id: str, lease_token: str, remote_id: str, *, now_iso: str) -> None: ...
    def mark_failed_atomic(self, tenant_id: str, publication_id: str, lease_token: str, error: str, *, retryable: bool, now_iso: str) -> dict: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise CloudSocialWorkerError("worker clock must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat()


def parse_worker_tenants(value: object) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return ()
    tenants: list[str] = []
    for item in raw.split(","):
        tenant = item.strip().lower()
        if not TENANT_ID_RE.fullmatch(tenant):
            raise CloudSocialWorkerError("BINARIO_SOCIAL_WORKER_TENANTS contains an invalid tenant id")
        if tenant not in tenants:
            tenants.append(tenant)
    if len(tenants) > MAX_TENANTS:
        raise CloudSocialWorkerError("BINARIO_SOCIAL_WORKER_TENANTS exceeds the 50-tenant safety limit")
    return tuple(tenants)


def _safe_worker_error(exc: Exception, *, phase: str) -> str:
    # Durable worker errors intentionally avoid provider response bodies, URLs, payloads,
    # credentials and arbitrary exception text. The phase + type is enough for triage.
    kind = type(exc).__name__
    if isinstance(exc, MetaGraphError):
        kind = "MetaGraphError"
    return f"{phase}: {kind}"


def _lease_payload(tenant_id: str, lease: dict, *, now: datetime) -> tuple[str, str, dict]:
    if not isinstance(lease, dict):
        raise CloudSocialWorkerError("claim returned a non-object lease")
    publication_id = str(lease.get("publication_id") or "").strip().lower()
    token = str(lease.get("lease_token") or "").strip().lower()
    digest = str(lease.get("body_sha256") or "").strip().lower()
    body = lease.get("body_json")
    if not re.fullmatch(r"^[0-9a-f]{32}$", publication_id):
        raise CloudSocialWorkerError("claim returned an invalid publication id")
    if not LEASE_TOKEN_RE.fullmatch(token):
        raise CloudSocialWorkerError("claim returned an invalid lease token")
    if not SHA256_RE.fullmatch(digest):
        raise CloudSocialWorkerError("claim returned an invalid body digest")
    if not isinstance(body, dict):
        raise CloudSocialWorkerError("claim returned an invalid publication body")
    if str(lease.get("tenant_id") or "").strip().lower() != tenant_id:
        raise CloudSocialWorkerError("claim crossed tenant boundary")

    raw = canonical_json_bytes(body)
    actual = hashlib.sha256(raw).hexdigest()
    if not secrets.compare_digest(actual, digest):
        raise CloudSocialWorkerError("claimed publication digest mismatch")
    normalized = validate_remote_social_job(raw, now=now)
    if normalized.get("schema") != REMOTE_SOCIAL_JOB_SCHEMA:
        raise CloudSocialWorkerError("claimed publication schema mismatch")
    if normalized["publication"]["id"] != publication_id:
        raise CloudSocialWorkerError("claimed publication identity mismatch")
    return publication_id, token, normalized


class CloudSocialWorker:
    """One-shot distributed worker with bounded Meta authority.

    The worker has no enqueue API and no browser surface. It only claims already approved
    jobs from an allowlisted tenant set. Immediately before the first Meta request it
    persists the provider-effect checkpoint. Any crash after that checkpoint is therefore
    terminal/ambiguous instead of automatically retrying and risking a duplicate post.
    """

    def __init__(
        self,
        storage: DistributedSocialStorage,
        client_factory: Callable[[], MetaGraphClient],
        tenants: tuple[str, ...],
        *,
        enabled: bool = False,
        limit_per_tenant: int = 5,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        instagram_poll_interval: float = 2.0,
        instagram_poll_attempts: int = 30,
        clock: Callable[[], datetime] = _utc_now,
    ):
        if not tenants:
            raise CloudSocialWorkerError("cloud social worker requires at least one allowlisted tenant")
        if len(tenants) > MAX_TENANTS or any(not TENANT_ID_RE.fullmatch(item) for item in tenants):
            raise CloudSocialWorkerError("invalid cloud social worker tenant allowlist")
        if limit_per_tenant < 1 or limit_per_tenant > MAX_LIMIT_PER_TENANT:
            raise CloudSocialWorkerError("worker limit_per_tenant must be between 1 and 10")
        if lease_seconds < 30 or lease_seconds > 900:
            raise CloudSocialWorkerError("worker lease_seconds must be between 30 and 900")
        if instagram_poll_interval < 0:
            raise CloudSocialWorkerError("instagram_poll_interval must be non-negative")
        if instagram_poll_attempts < 1 or instagram_poll_attempts > 120:
            raise CloudSocialWorkerError("instagram_poll_attempts must be between 1 and 120")
        self.storage = storage
        self.client_factory = client_factory
        self.tenants = tuple(dict.fromkeys(tenants))
        self.enabled = bool(enabled)
        self.limit_per_tenant = int(limit_per_tenant)
        self.lease_seconds = int(lease_seconds)
        self.sleep = sleep
        self.instagram_poll_interval = float(instagram_poll_interval)
        self.instagram_poll_attempts = int(instagram_poll_attempts)
        self.clock = clock

    @classmethod
    def from_env(cls) -> "CloudSocialWorker":
        enabled = os.environ.get("BINARIO_SOCIAL_WORKER_ENABLED", "").strip() == "1"
        tenants = parse_worker_tenants(os.environ.get("BINARIO_SOCIAL_WORKER_TENANTS", ""))
        if not tenants:
            raise CloudSocialWorkerError("BINARIO_SOCIAL_WORKER_TENANTS is required")
        try:
            limit = int(os.environ.get("BINARIO_SOCIAL_WORKER_LIMIT", "5"))
            lease_seconds = int(os.environ.get("BINARIO_SOCIAL_WORKER_LEASE_SECONDS", str(DEFAULT_LEASE_SECONDS)))
        except ValueError:
            raise CloudSocialWorkerError("cloud social worker numeric environment is invalid") from None
        return cls(
            SupabaseSocialQueueStorage(),
            MetaGraphClient.from_env,
            tenants,
            enabled=enabled,
            limit_per_tenant=limit,
            lease_seconds=lease_seconds,
        )

    def _instagram(self, client: MetaGraphClient, publication: dict) -> str:
        target_id = publication["target_id"]
        container_id = client.create_instagram_container(
            target_id,
            publication["media_url"],
            publication["message"],
            publication["kind"],
        )
        final = ""
        for attempt in range(self.instagram_poll_attempts):
            final = client.instagram_container_status(container_id, target_id)
            if final in {"FINISHED", "PUBLISHED"}:
                break
            if final in {"ERROR", "EXPIRED"}:
                raise CloudSocialWorkerError("Instagram container processing failed")
            if attempt + 1 < self.instagram_poll_attempts:
                self.sleep(self.instagram_poll_interval)
        else:
            raise CloudSocialWorkerError("Instagram container processing did not finish within the worker window")
        return client.publish_instagram_container(target_id, container_id)

    def _publish(self, client: MetaGraphClient, publication: dict) -> str:
        channel = publication["channel"]
        kind = publication["kind"]
        target_id = publication["target_id"]
        if channel == "facebook_page":
            if kind in {"text", "link"}:
                return client.publish_page_feed(target_id, publication["message"], publication["link_url"])
            if kind == "image":
                return client.publish_page_photo(target_id, publication["media_url"], publication["message"])
            raise CloudSocialWorkerError("unsupported Facebook cloud publication kind")
        if channel == "instagram":
            return self._instagram(client, publication)
        raise CloudSocialWorkerError("unsupported cloud social channel")

    def _process_lease(self, client: MetaGraphClient, tenant_id: str, lease: dict, *, claim_time: datetime) -> str:
        publication_id = str(lease.get("publication_id") or "").strip().lower()
        lease_token = str(lease.get("lease_token") or "").strip().lower()
        try:
            publication_id, lease_token, payload = _lease_payload(tenant_id, lease, now=claim_time)
        except Exception as exc:
            if re.fullmatch(r"^[0-9a-f]{32}$", publication_id) and LEASE_TOKEN_RE.fullmatch(lease_token):
                try:
                    self.storage.mark_failed_atomic(
                        tenant_id,
                        publication_id,
                        lease_token,
                        _safe_worker_error(exc, phase="lease-validation"),
                        retryable=False,
                        now_iso=_iso(self.clock()),
                    )
                except Exception:
                    pass
            return "INVALID_LEASE"

        try:
            self.storage.begin_provider_effect_atomic(
                tenant_id,
                publication_id,
                lease_token,
                now_iso=_iso(self.clock()),
            )
        except Exception:
            # No provider call occurred, so leaving the lease to expire is safe. The
            # claim RPC may recover it because provider_started_at was never committed.
            return "CHECKPOINT_BLOCKED"

        try:
            remote_id = self._publish(client, payload["publication"])
        except Exception as exc:
            try:
                self.storage.mark_failed_atomic(
                    tenant_id,
                    publication_id,
                    lease_token,
                    _safe_worker_error(exc, phase="provider"),
                    retryable=False,
                    now_iso=_iso(self.clock()),
                )
                return "FAILED_AMBIGUOUS"
            except Exception:
                # Provider effect may already exist; do not attempt another provider call.
                # Expired lease recovery will move this row to terminal ambiguity.
                return "FAILURE_CHECKPOINT_AMBIGUOUS"

        try:
            self.storage.mark_published_atomic(
                tenant_id,
                publication_id,
                lease_token,
                remote_id,
                now_iso=_iso(self.clock()),
            )
            return "PUBLISHED"
        except Exception:
            # Remote success happened but durable completion did not. Never retry Meta.
            return "COMPLETION_AMBIGUOUS"

    def run_once(self) -> dict:
        started = self.clock()
        if not self.enabled:
            return {
                "schema": WORKER_RESULT_SCHEMA,
                "enabled": False,
                "status": "DISABLED",
                "tenant_count": len(self.tenants),
                "claimed": 0,
                "published": 0,
                "failed_ambiguous": 0,
                "completion_ambiguous": 0,
                "configuration_secret_returned": False,
            }

        # Resolve the Meta credential before claiming anything. A missing/invalid cloud
        # credential must not consume attempts or leases.
        try:
            client = self.client_factory()
        except Exception:
            return {
                "schema": WORKER_RESULT_SCHEMA,
                "enabled": True,
                "status": "PROVIDER_CONFIGURATION_BLOCKED",
                "tenant_count": len(self.tenants),
                "claimed": 0,
                "published": 0,
                "failed_ambiguous": 0,
                "completion_ambiguous": 0,
                "configuration_secret_returned": False,
            }

        worker_id = "worker_" + secrets.token_hex(8)
        outcomes: dict[str, int] = {}
        claimed = 0
        for tenant_id in self.tenants:
            leases = self.storage.claim_due_atomic(
                tenant_id,
                worker_id,
                now_iso=_iso(self.clock()),
                limit=self.limit_per_tenant,
                lease_seconds=self.lease_seconds,
            )
            if not isinstance(leases, list):
                raise CloudSocialWorkerError("distributed claim did not return a list")
            claimed += len(leases)
            for lease in leases:
                outcome = self._process_lease(client, tenant_id, lease, claim_time=started)
                outcomes[outcome] = outcomes.get(outcome, 0) + 1

        ambiguous = sum(
            count for key, count in outcomes.items()
            if key in {"FAILED_AMBIGUOUS", "FAILURE_CHECKPOINT_AMBIGUOUS"}
        )
        completion_ambiguous = outcomes.get("COMPLETION_AMBIGUOUS", 0)
        status = "OK"
        if ambiguous or completion_ambiguous:
            status = "MANUAL_RECONCILIATION_REQUIRED"
        elif outcomes.get("INVALID_LEASE") or outcomes.get("CHECKPOINT_BLOCKED"):
            status = "PARTIAL"

        return {
            "schema": WORKER_RESULT_SCHEMA,
            "enabled": True,
            "status": status,
            "tenant_count": len(self.tenants),
            "claimed": claimed,
            "published": outcomes.get("PUBLISHED", 0),
            "failed_ambiguous": ambiguous,
            "completion_ambiguous": completion_ambiguous,
            "invalid_or_blocked": outcomes.get("INVALID_LEASE", 0) + outcomes.get("CHECKPOINT_BLOCKED", 0),
            "configuration_secret_returned": False,
        }


def main() -> int:
    try:
        result = CloudSocialWorker.from_env().run_once()
    except Exception as exc:
        result = {
            "schema": WORKER_RESULT_SCHEMA,
            "enabled": False,
            "status": "WORKER_CONFIGURATION_ERROR",
            "error_type": type(exc).__name__,
            "configuration_secret_returned": False,
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("status") in {"OK", "DISABLED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
