from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now


GATEWAY_CONFIG_SCHEMA = "binario.marketing.public-gateway-config.v1"
GATEWAY_ENVELOPE_SCHEMA = "binario.marketing.public-intake-envelope.v1"
PUBLIC_LEAD_SCHEMA = "binario.marketing.public-lead.v1"
TENANT_ID_RE = re.compile(r"^tenant_[0-9a-f]{24}$")
EVENT_ID_RE = re.compile(r"^evt_[0-9a-f]{32}$")
MAX_GATEWAY_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_GATEWAY_BATCH = 100


def _company(value: object) -> str:
    text = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(text):
        raise ValueError("invalid company id")
    return text


def _tenant(value: object) -> str:
    text = str(value or "").strip().lower()
    if not TENANT_ID_RE.fullmatch(text):
        raise ValueError("invalid gateway tenant id")
    return text


def _gateway_url(value: object) -> str:
    text = str(value or "").strip()
    if len(text) > 2048:
        raise ValueError("gateway URL is too long")
    parsed = urlsplit(text)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("gateway URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("gateway URL cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("gateway URL cannot contain query or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("gateway URL must be an origin without a path")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{host}{port}"


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def body_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _master_secret(value: object) -> str:
    clean = str(value or "").strip()
    if len(clean) < 32:
        raise ValueError("gateway master secret must contain at least 32 characters")
    if len(clean) > 4096:
        raise ValueError("gateway master secret is unexpectedly large")
    return clean


def derive_tenant_secret(master_secret: str, tenant_id: str, *, purpose: str) -> str:
    master = _master_secret(master_secret).encode("utf-8")
    tenant = _tenant(tenant_id)
    if purpose not in {"ingress", "pull"}:
        raise ValueError("invalid gateway secret purpose")
    message = f"binario-gateway-v1:{purpose}:{tenant}".encode("utf-8")
    return hmac.new(master, message, hashlib.sha256).hexdigest()


def request_signature(secret_hex: str, timestamp: str, nonce: str, method: str, path: str, body: bytes = b"") -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", str(secret_hex or "")):
        raise ValueError("invalid derived gateway secret")
    clean_timestamp = str(timestamp or "").strip()
    if not clean_timestamp.isdigit():
        raise ValueError("gateway timestamp must be Unix seconds")
    clean_nonce = str(nonce or "").strip()
    if not clean_nonce or len(clean_nonce) > 128:
        raise ValueError("invalid gateway nonce")
    clean_method = str(method or "").strip().upper()
    if clean_method not in {"GET", "POST"}:
        raise ValueError("unsupported gateway request method")
    clean_path = str(path or "").strip()
    if not clean_path.startswith("/api/") or "?" in clean_path:
        raise ValueError("gateway signature path must be a canonical API path")
    digest = hashlib.sha256(bytes(body)).hexdigest()
    canonical = f"v1\n{clean_timestamp}\n{clean_nonce}\n{clean_method}\n{clean_path}\n{digest}".encode("utf-8")
    return "v1=" + hmac.new(bytes.fromhex(secret_hex), canonical, hashlib.sha256).hexdigest()


def envelope_signature(secret_hex: str, tenant_id: str, event_id: str, received_at: str, payload_sha256: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", str(secret_hex or "")):
        raise ValueError("invalid derived gateway secret")
    tenant = _tenant(tenant_id)
    event = str(event_id or "").strip().lower()
    if not EVENT_ID_RE.fullmatch(event):
        raise ValueError("invalid gateway event id")
    digest = str(payload_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid gateway payload hash")
    canonical = f"event-v1\n{tenant}\n{event}\n{received_at}\n{digest}".encode("utf-8")
    return "v1=" + hmac.new(bytes.fromhex(secret_hex), canonical, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class PublicGatewayConfig:
    schema: str
    company_id: str
    gateway_url: str
    tenant_id: str
    created_at: str
    updated_at: str


class PublicGatewayConfigStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, company_id: str) -> Path:
        return self.root / f"{_company(company_id)}.json"

    def get(self, company_id: str) -> PublicGatewayConfig | None:
        path = self._path(company_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = PublicGatewayConfig(**payload)
        if row.schema != GATEWAY_CONFIG_SCHEMA or row.company_id != _company(company_id):
            raise ValueError("invalid public gateway config")
        _gateway_url(row.gateway_url)
        _tenant(row.tenant_id)
        return row

    def upsert(self, company_id: str, payload: dict) -> PublicGatewayConfig:
        company = _company(company_id)
        if not isinstance(payload, dict):
            raise ValueError("gateway config payload must be an object")
        unknown = set(payload) - {"gateway_url", "tenant_id"}
        if unknown:
            raise ValueError(f"unsupported gateway config fields: {', '.join(sorted(unknown))}")
        current = self.get(company)
        gateway_url = _gateway_url(payload.get("gateway_url") or (current.gateway_url if current else ""))
        tenant_id = _tenant(payload.get("tenant_id") or (current.tenant_id if current else f"tenant_{secrets.token_hex(12)}"))
        now = _now()
        row = PublicGatewayConfig(
            schema=GATEWAY_CONFIG_SCHEMA,
            company_id=company,
            gateway_url=gateway_url,
            tenant_id=tenant_id,
            created_at=current.created_at if current else now,
            updated_at=now,
        )
        write_json_atomic(self._path(company), asdict(row))
        return row


@dataclass(frozen=True)
class GatewayCredentialStatus:
    configured: bool
    source: str
    writable: bool


class GatewayCredentialError(RuntimeError):
    pass


class GatewayCredentialStore:
    """One installation-level master secret, kept out of application JSON."""

    ENV_NAME = "BINARIO_GATEWAY_MASTER_SECRET"

    def __init__(self, helper: Path | None = None):
        configured = os.environ.get("BINARIO_KEYCHAIN_HELPER", "").strip()
        meta_helper = os.environ.get("BINARIO_META_KEYCHAIN_HELPER", "").strip()
        selected = helper or (Path(configured).expanduser() if configured else None) or (Path(meta_helper).expanduser() if meta_helper else None)
        self.helper = Path(selected).expanduser() if selected else None

    def _helper_ready(self) -> bool:
        return bool(self.helper and self.helper.is_file() and os.access(self.helper, os.X_OK))

    def _run(self, command: str, *, secret: str | None = None) -> subprocess.CompletedProcess[str]:
        if not self._helper_ready():
            raise GatewayCredentialError("native gateway Keychain helper is unavailable")
        try:
            return subprocess.run(
                [str(self.helper), command, "gateway"],
                input=secret,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
                env={"PATH": "/usr/bin:/bin"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GatewayCredentialError(f"native gateway Keychain helper failed: {type(exc).__name__}") from None

    def read(self) -> str | None:
        env_value = os.environ.get(self.ENV_NAME, "").strip()
        if env_value:
            return _master_secret(env_value)
        if not self._helper_ready():
            return None
        result = self._run("get")
        if result.returncode == 3:
            return None
        if result.returncode != 0:
            raise GatewayCredentialError("unable to read gateway secret from macOS Keychain")
        value = result.stdout.strip()
        return _master_secret(value) if value else None

    def status(self) -> GatewayCredentialStatus:
        if os.environ.get(self.ENV_NAME, "").strip():
            return GatewayCredentialStatus(True, "environment", self._helper_ready())
        if not self._helper_ready():
            return GatewayCredentialStatus(False, "none", False)
        result = self._run("status")
        if result.returncode != 0:
            raise GatewayCredentialError("unable to inspect gateway secret in macOS Keychain")
        configured = result.stdout.strip() == "configured"
        return GatewayCredentialStatus(configured, "keychain" if configured else "none", True)

    def write(self, secret: str) -> GatewayCredentialStatus:
        clean = _master_secret(secret)
        if os.environ.get(self.ENV_NAME, "").strip():
            raise GatewayCredentialError(f"gateway secret is controlled by {self.ENV_NAME}")
        result = self._run("set", secret=clean)
        if result.returncode != 0:
            raise GatewayCredentialError("unable to save gateway secret in macOS Keychain")
        return GatewayCredentialStatus(True, "keychain", True)

    def delete(self) -> GatewayCredentialStatus:
        if os.environ.get(self.ENV_NAME, "").strip():
            raise GatewayCredentialError(f"gateway secret is supplied by {self.ENV_NAME} and cannot be removed by the app")
        if not self._helper_ready():
            return GatewayCredentialStatus(False, "none", False)
        result = self._run("delete")
        if result.returncode != 0:
            raise GatewayCredentialError("unable to remove gateway secret from macOS Keychain")
        return GatewayCredentialStatus(False, "none", True)


class PublicGatewayClient:
    def __init__(self, gateway_url: str, tenant_id: str, pull_secret: str, *, timeout: float = 12.0):
        self.gateway_url = _gateway_url(gateway_url)
        self.tenant_id = _tenant(tenant_id)
        if not re.fullmatch(r"[0-9a-f]{64}", str(pull_secret or "")):
            raise ValueError("invalid pull secret")
        self.pull_secret = pull_secret
        self.timeout = max(1.0, min(float(timeout), 30.0))

    def _request_json(self, path: str, *, method: str, payload: object | None = None) -> dict:
        body = canonical_json_bytes(payload) if payload is not None else b""
        timestamp = str(int(__import__("time").time()))
        nonce = secrets.token_hex(16)
        signature = request_signature(self.pull_secret, timestamp, nonce, method, path, body)
        request = Request(
            self.gateway_url + path,
            data=body if method == "POST" else None,
            method=method,
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
                raw = response.read(MAX_GATEWAY_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", "replace") if exc.fp else ""
            raise RuntimeError(f"gateway HTTP {exc.code}: {detail[:500]}") from None
        except URLError as exc:
            raise RuntimeError(f"gateway network error: {type(exc.reason).__name__}") from None
        if len(raw) > MAX_GATEWAY_RESPONSE_BYTES:
            raise RuntimeError("gateway response exceeded 5 MiB")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("gateway returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("gateway response must be an object")
        return decoded

    def pull(self, *, limit: int = MAX_GATEWAY_BATCH) -> list[dict]:
        bounded = max(1, min(int(limit), MAX_GATEWAY_BATCH))
        payload = self._request_json("/api/pull", method="POST", payload={"limit": bounded})
        if payload.get("schema") != "binario.marketing.public-intake-pull.v1":
            raise RuntimeError("gateway pull schema mismatch")
        rows = payload.get("events")
        if not isinstance(rows, list) or len(rows) > bounded:
            raise RuntimeError("gateway returned an invalid event batch")
        return rows

    def ack(self, event_ids: list[str]) -> dict:
        clean = []
        for raw in event_ids:
            event = str(raw or "").strip().lower()
            if not EVENT_ID_RE.fullmatch(event):
                raise ValueError("invalid gateway event id")
            if event not in clean:
                clean.append(event)
        if not clean:
            return {"schema": "binario.marketing.public-intake-ack.v1", "acked": 0}
        if len(clean) > MAX_GATEWAY_BATCH:
            raise ValueError("too many gateway events to acknowledge")
        return self._request_json("/api/ack", method="POST", payload={"event_ids": clean})


def verify_envelope(envelope: dict, *, tenant_id: str, pull_secret: str) -> dict:
    if not isinstance(envelope, dict):
        raise ValueError("gateway envelope must be an object")
    allowed = {"schema", "tenant_id", "event_id", "received_at", "payload", "payload_sha256", "signature"}
    unknown = set(envelope) - allowed
    if unknown:
        raise ValueError(f"unsupported gateway envelope fields: {', '.join(sorted(unknown))}")
    if envelope.get("schema") != GATEWAY_ENVELOPE_SCHEMA:
        raise ValueError("gateway envelope schema mismatch")
    tenant = _tenant(envelope.get("tenant_id"))
    if tenant != _tenant(tenant_id):
        raise ValueError("gateway envelope tenant mismatch")
    event = str(envelope.get("event_id") or "").strip().lower()
    if not EVENT_ID_RE.fullmatch(event):
        raise ValueError("invalid gateway event id")
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or payload.get("schema") != PUBLIC_LEAD_SCHEMA:
        raise ValueError("gateway event payload schema mismatch")
    digest = body_sha256(payload)
    if not hmac.compare_digest(digest, str(envelope.get("payload_sha256") or "")):
        raise ValueError("gateway payload hash mismatch")
    expected = envelope_signature(pull_secret, tenant, event, str(envelope.get("received_at") or ""), digest)
    if not hmac.compare_digest(expected, str(envelope.get("signature") or "")):
        raise ValueError("gateway envelope signature mismatch")
    return payload


__all__ = [
    "EVENT_ID_RE", "GATEWAY_CONFIG_SCHEMA", "GATEWAY_ENVELOPE_SCHEMA", "GatewayCredentialError",
    "GatewayCredentialStatus", "GatewayCredentialStore", "MAX_GATEWAY_BATCH", "PUBLIC_LEAD_SCHEMA",
    "PublicGatewayClient", "PublicGatewayConfig", "PublicGatewayConfigStore", "TENANT_ID_RE",
    "body_sha256", "canonical_json_bytes", "derive_tenant_secret", "envelope_signature",
    "request_signature", "verify_envelope",
]
