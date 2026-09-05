from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gateway.social_api import SOCIAL_ENQUEUE_PATH, SOCIAL_STATUS_PATH, derive_social_secret
from gateway.social_queue import REMOTE_SOCIAL_JOB_SCHEMA, validate_remote_social_job

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .public_gateway import (
    GatewayCredentialStore,
    PublicGatewayConfigStore,
    canonical_json_bytes,
    request_signature,
)
from .social_store import Publication, SocialStore, _now


DELEGATION_SCHEMA = "binario.marketing.cloud-social-delegation.v1"
DELEGATION_STATUSES = {
    "PREPARED",
    "CONFIRMED",
    "REMOTE_PUBLISHED",
    "REMOTE_FAILED",
    "AMBIGUOUS",
}
MAX_RESPONSE_BYTES = 256 * 1024
_PUBLICATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TENANT_ID_RE = re.compile(r"^tenant_[0-9a-f]{24}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CloudSocialBridgeError(RuntimeError):
    pass


class CloudSocialTransportError(CloudSocialBridgeError):
    pass


@dataclass(frozen=True)
class CloudSocialDelegation:
    schema: str
    company_id: str
    publication_id: str
    gateway_url: str
    tenant_id: str
    payload_sha256: str
    status: str
    remote_status: str | None
    remote_id: str | None
    provider_outcome_ambiguous: bool
    transport_error_type: str | None
    created_at: str
    updated_at: str
    confirmed_at: str | None = None
    last_checked_at: str | None = None


class CloudSocialDelegationStore:
    """Secret-free durable handoff evidence; publication content remains in SocialStore."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, publication_id: str) -> Path:
        publication = str(publication_id or "").strip().lower()
        if not _PUBLICATION_ID_RE.fullmatch(publication):
            raise ValueError("invalid publication id")
        return self.root / f"{publication}.json"

    @staticmethod
    def _validate(row: CloudSocialDelegation) -> CloudSocialDelegation:
        if row.schema != DELEGATION_SCHEMA:
            raise ValueError("cloud social delegation schema mismatch")
        if not COMPANY_ID_RE.fullmatch(row.company_id):
            raise ValueError("invalid delegation company id")
        if not _PUBLICATION_ID_RE.fullmatch(row.publication_id):
            raise ValueError("invalid delegation publication id")
        if not row.gateway_url.startswith("https://") or len(row.gateway_url) > 2048:
            raise ValueError("invalid delegation gateway origin")
        if not _TENANT_ID_RE.fullmatch(row.tenant_id):
            raise ValueError("invalid delegation tenant id")
        if not _SHA256_RE.fullmatch(row.payload_sha256):
            raise ValueError("invalid delegation payload digest")
        if row.status not in DELEGATION_STATUSES:
            raise ValueError("invalid delegation status")
        if row.remote_status is not None and row.remote_status not in {"PENDING", "LEASED", "PUBLISHED", "FAILED"}:
            raise ValueError("invalid remote delegation status")
        if row.remote_id is not None and (not row.remote_id.strip() or len(row.remote_id) > 256):
            raise ValueError("invalid delegated remote id")
        if row.transport_error_type is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", row.transport_error_type):
            raise ValueError("invalid delegation transport error type")
        return row

    def get(self, publication_id: str) -> CloudSocialDelegation | None:
        path = self._path(publication_id)
        with self._lock:
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid cloud social delegation payload")
        forbidden = {"message", "media_url", "link_url", "access_token", "token", "secret", "authorization"}
        if any(str(key).casefold() in forbidden for key in payload):
            raise ValueError("delegation sidecar contains forbidden publication or secret fields")
        return self._validate(CloudSocialDelegation(**payload))

    def prepare(
        self,
        company_id: str,
        publication_id: str,
        *,
        gateway_url: str,
        tenant_id: str,
        payload_sha256: str,
    ) -> CloudSocialDelegation:
        company = str(company_id or "").strip()
        publication = str(publication_id or "").strip().lower()
        digest = str(payload_sha256 or "").strip().lower()
        with self._lock:
            current = self.get(publication)
            if current:
                identity = (current.company_id, current.gateway_url, current.tenant_id, current.payload_sha256)
                proposed = (company, gateway_url, tenant_id, digest)
                if identity != proposed:
                    raise CloudSocialBridgeError("existing cloud delegation is bound to different immutable handoff identity")
                return current
            now = _now()
            row = self._validate(CloudSocialDelegation(
                schema=DELEGATION_SCHEMA,
                company_id=company,
                publication_id=publication,
                gateway_url=str(gateway_url),
                tenant_id=str(tenant_id).lower(),
                payload_sha256=digest,
                status="PREPARED",
                remote_status=None,
                remote_id=None,
                provider_outcome_ambiguous=False,
                transport_error_type=None,
                created_at=now,
                updated_at=now,
            ))
            write_json_atomic(self._path(publication), asdict(row))
            return row

    def update(
        self,
        publication_id: str,
        *,
        status: str,
        remote_status: str | None = None,
        remote_id: str | None = None,
        provider_outcome_ambiguous: bool = False,
        transport_error_type: str | None = None,
        confirmed: bool = False,
        checked: bool = False,
    ) -> CloudSocialDelegation:
        clean_status = str(status or "").strip().upper()
        if clean_status not in DELEGATION_STATUSES:
            raise ValueError("invalid delegation status")
        with self._lock:
            current = self.get(publication_id)
            if current is None:
                raise KeyError(publication_id)
            now = _now()
            updated = replace(
                current,
                status=clean_status,
                remote_status=remote_status,
                remote_id=(str(remote_id).strip() or None) if remote_id is not None else current.remote_id,
                provider_outcome_ambiguous=bool(provider_outcome_ambiguous),
                transport_error_type=(str(transport_error_type).strip() or None) if transport_error_type else None,
                confirmed_at=(current.confirmed_at or now) if confirmed else current.confirmed_at,
                last_checked_at=now if checked else current.last_checked_at,
                updated_at=now,
            )
            self._validate(updated)
            write_json_atomic(self._path(updated.publication_id), asdict(updated))
            return updated


class CloudSocialGatewayClient:
    """Desktop signed client. It receives only a purpose-separated social secret."""

    def __init__(self, gateway_url: str, tenant_id: str, social_secret: str, *, timeout: float = 12.0):
        origin = str(gateway_url or "").strip().rstrip("/")
        if not origin.startswith("https://") or "/" in origin.removeprefix("https://"):
            raise ValueError("gateway_url must be a credential-free HTTPS origin")
        tenant = str(tenant_id or "").strip().lower()
        if not _TENANT_ID_RE.fullmatch(tenant):
            raise ValueError("invalid social gateway tenant id")
        secret = str(social_secret or "").strip().lower()
        if not _SHA256_RE.fullmatch(secret):
            raise ValueError("invalid derived social gateway secret")
        self.gateway_url = origin
        self.tenant_id = tenant
        self.social_secret = secret
        self.timeout = max(1.0, min(float(timeout), 30.0))

    def _post(self, path: str, payload: dict, *, max_bytes: int) -> tuple[int, dict]:
        body = canonical_json_bytes(payload)
        if len(body) > max_bytes:
            raise ValueError("cloud social request body exceeds endpoint limit")
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        signature = request_signature(self.social_secret, timestamp, nonce, "POST", path, body)
        request = Request(
            self.gateway_url + path,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Binario-Tenant": self.tenant_id,
                "X-Binario-Timestamp": timestamp,
                "X-Binario-Nonce": nonce,
                "X-Binario-Signature": signature,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = int(response.status)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            # Do not reflect gateway/provider bodies into local durable state.
            raise CloudSocialTransportError(f"cloud social gateway HTTP {exc.code}") from None
        except URLError as exc:
            raise CloudSocialTransportError(f"cloud social gateway network error: {type(exc.reason).__name__}") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise CloudSocialTransportError("cloud social gateway response exceeded limit")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudSocialTransportError("cloud social gateway returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise CloudSocialTransportError("cloud social gateway response must be an object")
        return status, decoded

    def enqueue(self, payload: dict) -> dict:
        status, response = self._post(SOCIAL_ENQUEUE_PATH, payload, max_bytes=64 * 1024)
        if status not in {200, 202} or response.get("schema") != "binario.marketing.remote-social-receipt.v1":
            raise CloudSocialTransportError("cloud social enqueue receipt is invalid")
        return response

    def status(self, publication_id: str) -> tuple[int, dict]:
        publication = str(publication_id or "").strip().lower()
        if not _PUBLICATION_ID_RE.fullmatch(publication):
            raise ValueError("invalid publication id")
        return self._post(SOCIAL_STATUS_PATH, {"publication_id": publication}, max_bytes=4096)


class CloudSocialBridge:
    def __init__(
        self,
        social: SocialStore,
        configs: PublicGatewayConfigStore,
        credentials: GatewayCredentialStore,
        delegations: CloudSocialDelegationStore,
        *,
        client_factory: Callable[[str, str, str], CloudSocialGatewayClient] = CloudSocialGatewayClient,
    ):
        self.social = social
        self.configs = configs
        self.credentials = credentials
        self.delegations = delegations
        self.client_factory = client_factory
        self._lock = threading.RLock()

    @staticmethod
    def _job(publication: Publication) -> dict:
        if publication.status not in {"QUEUED", "DELEGATED"}:
            raise CloudSocialBridgeError("cloud delegation requires queued or already delegated publication")
        if not publication.scheduled_for:
            raise CloudSocialBridgeError("cloud delegation requires a scheduled publication")
        candidate = {
            "schema": REMOTE_SOCIAL_JOB_SCHEMA,
            "publication": {
                "id": publication.id,
                "project_id": publication.project_id,
                "channel": publication.channel,
                "target_id": publication.target_id,
                "target_name": publication.target_name,
                "kind": publication.kind,
                "message": publication.message,
                "link_url": publication.link_url,
                "media_url": publication.media_url,
                "scheduled_for": publication.scheduled_for,
            },
            # This captures the explicit operator-approved source state that existed at
            # delegation time. The local row subsequently becomes DELEGATED before IO.
            "approval": {"source_status": "QUEUED", "operator_approved": True},
        }
        raw = canonical_json_bytes(candidate)
        return validate_remote_social_job(raw)

    def _bound_client(self, delegation: CloudSocialDelegation) -> CloudSocialGatewayClient:
        master = self.credentials.read()
        if not master:
            raise CloudSocialBridgeError("gateway master credential is not configured")
        social_secret = derive_social_secret(master, delegation.tenant_id)
        return self.client_factory(delegation.gateway_url, delegation.tenant_id, social_secret)

    def _prepare(self, company_id: str, publication_id: str) -> tuple[Publication, dict, CloudSocialDelegation]:
        publication = self.social.get(publication_id)
        if publication.project_id != company_id:
            raise KeyError(publication_id)
        if publication.status not in {"QUEUED", "DELEGATED"}:
            raise CloudSocialBridgeError("publication has no delegable local authority")
        config = self.configs.get(company_id)
        if config is None:
            raise CloudSocialBridgeError("company public gateway is not configured")
        job = self._job(publication)
        digest = hashlib.sha256(canonical_json_bytes(job)).hexdigest()
        delegation = self.delegations.prepare(
            company_id,
            publication.id,
            gateway_url=config.gateway_url,
            tenant_id=config.tenant_id,
            payload_sha256=digest,
        )
        return publication, job, delegation

    def delegate(self, company_id: str, publication_id: str) -> dict:
        """Withdraw local authority first, then attempt idempotent remote enqueue."""
        company = str(company_id or "").strip()
        if not COMPANY_ID_RE.fullmatch(company):
            raise ValueError("invalid company id")
        with self._lock:
            publication, job, delegation = self._prepare(company, publication_id)
            if publication.status == "QUEUED":
                publication = self.social.delegate(publication.id)
            # From this point forward local due()/publish() cannot own this row.
            try:
                receipt = self._bound_client(delegation).enqueue(job)
            except Exception as exc:
                self.delegations.update(
                    publication.id,
                    status="PREPARED",
                    transport_error_type=type(exc).__name__,
                )
                return self.overview(publication.id)
            if str(receipt.get("publication_id") or "").strip().lower() != publication.id:
                raise CloudSocialBridgeError("cloud social receipt publication mismatch")
            self.delegations.update(
                publication.id,
                status="CONFIRMED",
                remote_status="PENDING",
                confirmed=True,
            )
            return self.overview(publication.id)

    def retry_enqueue(self, company_id: str, publication_id: str) -> dict:
        with self._lock:
            publication = self.social.get(publication_id)
            delegation = self.delegations.get(publication_id)
            if publication.project_id != company_id:
                raise KeyError(publication_id)
            if publication.status != "DELEGATED" or delegation is None or delegation.status != "PREPARED":
                raise CloudSocialBridgeError("only unconfirmed delegated publications can retry cloud enqueue")
            job = self._job(publication)
            digest = hashlib.sha256(canonical_json_bytes(job)).hexdigest()
            if not hmac.compare_digest(digest, delegation.payload_sha256):
                raise CloudSocialBridgeError("delegated publication changed after authority withdrawal")
            try:
                receipt = self._bound_client(delegation).enqueue(job)
            except Exception as exc:
                self.delegations.update(publication.id, status="PREPARED", transport_error_type=type(exc).__name__)
                return self.overview(publication.id)
            if str(receipt.get("publication_id") or "").strip().lower() != publication.id:
                raise CloudSocialBridgeError("cloud social receipt publication mismatch")
            self.delegations.update(publication.id, status="CONFIRMED", remote_status="PENDING", confirmed=True)
            return self.overview(publication.id)

    def refresh_status(self, company_id: str, publication_id: str) -> dict:
        with self._lock:
            publication = self.social.get(publication_id)
            delegation = self.delegations.get(publication_id)
            if publication.project_id != company_id:
                raise KeyError(publication_id)
            if publication.status not in {"DELEGATED", "PUBLISHED", "FAILED"} or delegation is None:
                raise CloudSocialBridgeError("publication has no cloud delegation to refresh")
            try:
                status_code, remote = self._bound_client(delegation).status(publication.id)
            except Exception as exc:
                self.delegations.update(
                    publication.id,
                    status=delegation.status,
                    remote_status=delegation.remote_status,
                    remote_id=delegation.remote_id,
                    provider_outcome_ambiguous=delegation.provider_outcome_ambiguous,
                    transport_error_type=type(exc).__name__,
                    checked=True,
                )
                return self.overview(publication.id)
            if status_code == 404:
                # A PREPARED delegation can be retried explicitly. A previously confirmed
                # delegation disappearing remotely is anomalous and remains fail-closed.
                next_status = "PREPARED" if delegation.status == "PREPARED" else "AMBIGUOUS"
                self.delegations.update(publication.id, status=next_status, checked=True)
                return self.overview(publication.id)
            if status_code != 200 or str(remote.get("publication_id") or "").lower() != publication.id:
                raise CloudSocialBridgeError("cloud social status response is invalid")
            remote_status = str(remote.get("status") or "").strip().upper()
            ambiguous = bool(remote.get("provider_outcome_ambiguous", False))
            remote_id = str(remote.get("remote_id") or "").strip() or None
            if remote_status == "PUBLISHED":
                if not remote_id:
                    raise CloudSocialBridgeError("published cloud status is missing remote id")
                if publication.status == "DELEGATED":
                    publication = self.social.mark_delegated_published(publication.id, remote_id)
                self.delegations.update(
                    publication.id,
                    status="REMOTE_PUBLISHED",
                    remote_status="PUBLISHED",
                    remote_id=remote_id,
                    checked=True,
                )
            elif remote_status == "FAILED":
                if ambiguous:
                    # Keep DELEGATED: neither local queue nor an automatic retry may own it.
                    self.delegations.update(
                        publication.id,
                        status="AMBIGUOUS",
                        remote_status="FAILED",
                        provider_outcome_ambiguous=True,
                        checked=True,
                    )
                else:
                    if publication.status == "DELEGATED":
                        publication = self.social.mark_delegated_failed(
                            publication.id,
                            "cloud publication failed before a confirmed provider outcome; explicit review required",
                        )
                    self.delegations.update(
                        publication.id,
                        status="REMOTE_FAILED",
                        remote_status="FAILED",
                        provider_outcome_ambiguous=False,
                        checked=True,
                    )
            elif remote_status in {"PENDING", "LEASED"}:
                self.delegations.update(
                    publication.id,
                    status="CONFIRMED",
                    remote_status=remote_status,
                    provider_outcome_ambiguous=False,
                    checked=True,
                )
            else:
                raise CloudSocialBridgeError("unsupported cloud social status")
            return self.overview(publication.id)

    def overview(self, publication_id: str) -> dict:
        publication = self.social.get(publication_id)
        delegation = self.delegations.get(publication_id)
        return {
            "schema": "binario.marketing.cloud-social-delegation-overview.v1",
            "publication_id": publication.id,
            "company_id": publication.project_id,
            "local_status": publication.status,
            "local_scheduler_authority": publication.status == "QUEUED",
            "delegated": delegation is not None,
            "delegation": asdict(delegation) if delegation else None,
            "requires_manual_reconciliation": bool(delegation and delegation.status == "AMBIGUOUS"),
            "secret_returned": False,
            "publication_body_returned": False,
        }


__all__ = [
    "CloudSocialBridge", "CloudSocialBridgeError", "CloudSocialDelegation",
    "CloudSocialDelegationStore", "CloudSocialGatewayClient", "CloudSocialTransportError",
    "DELEGATION_SCHEMA", "DELEGATION_STATUSES",
]
