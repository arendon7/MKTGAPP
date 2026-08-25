from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from binario_marketing.public_gateway import (
    PublicGatewayClient,
    canonical_json_bytes,
    derive_tenant_secret,
    request_signature,
    verify_envelope,
)


MAX_RESPONSE = 128 * 1024


def _origin(value: str) -> str:
    from binario_marketing.public_gateway import _gateway_url
    return _gateway_url(value)


def _read_json(request: Request, *, timeout: float = 12.0) -> dict:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from None
    except URLError as exc:
        raise RuntimeError(f"network error: {type(exc.reason).__name__}") from None
    if status < 200 or status >= 300:
        raise RuntimeError(f"unexpected HTTP status {status}")
    if len(raw) > MAX_RESPONSE:
        raise RuntimeError("gateway response exceeded smoke limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("gateway returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("gateway response must be a JSON object")
    return payload


def _health(origin: str) -> dict:
    payload = _read_json(Request(origin + "/api/health", method="GET", headers={"Accept": "application/json"}))
    if payload.get("schema") != "binario.marketing.public-gateway-health.v1" or payload.get("status") != "ok":
        raise RuntimeError("gateway health contract mismatch")
    if payload.get("ready_for_intake") is not True:
        raise RuntimeError("gateway is not ready for intake")
    if payload.get("browser_secret_supported") is not False:
        raise RuntimeError("gateway health weakened browser-secret safety")
    return payload


def _ingest(origin: str, tenant_id: str, ingress_secret: str) -> str:
    event_id = "evt_" + secrets.token_hex(16)
    payload = {
        "schema": "binario.marketing.public-lead.v1",
        "external_ref": "wave57-live-smoke:" + event_id,
        "lead": {
            "name": "Binario Wave 57 Deployment Smoke",
            "source": "wave57_deployment_smoke",
            "tags": ["wave57-smoke"],
            "notes": "Synthetic deployment verification event; contains no real customer PII.",
        },
    }
    body = canonical_json_bytes(payload)
    timestamp = str(int(time.time()))
    signature = request_signature(ingress_secret, timestamp, event_id, "POST", "/api/intake", body)
    response = _read_json(Request(
        origin + "/api/intake",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Binario-Tenant": tenant_id,
            "X-Binario-Timestamp": timestamp,
            "X-Binario-Event": event_id,
            "X-Binario-Signature": signature,
        },
    ))
    if response.get("schema") != "binario.marketing.public-intake-receipt.v1":
        raise RuntimeError("ingress receipt schema mismatch")
    if response.get("event_id") != event_id:
        raise RuntimeError("ingress response event mismatch")
    if response.get("accepted") is not True or not isinstance(response.get("idempotent_reuse"), bool):
        raise RuntimeError("ingress receipt acceptance contract mismatch")
    return event_id


def run(origin: str, tenant_id: str, master_secret: str, *, ack: bool = True) -> dict:
    clean_origin = _origin(origin)
    ingress_secret = derive_tenant_secret(master_secret, tenant_id, purpose="ingress")
    pull_secret = derive_tenant_secret(master_secret, tenant_id, purpose="pull")
    health = _health(clean_origin)
    event_id = _ingest(clean_origin, tenant_id, ingress_secret)
    client = PublicGatewayClient(clean_origin, tenant_id, pull_secret)
    envelopes = client.pull(limit=100)
    match = next((row for row in envelopes if row.get("event_id") == event_id), None)
    if match is None:
        raise RuntimeError("synthetic event was not returned by authenticated pull")
    payload = verify_envelope(match, tenant_id=tenant_id, pull_secret=pull_secret)
    if payload.get("external_ref") != "wave57-live-smoke:" + event_id:
        raise RuntimeError("pulled synthetic payload does not match ingested event")
    acked = 0
    if ack:
        result = client.ack([event_id])
        acked = int(result.get("acked", 0))
        if acked != 1:
            raise RuntimeError("synthetic event ACK was not confirmed")
    return {
        "schema": "binario.marketing.wave57-live-smoke.v1",
        "status": "PASS",
        "health": health.get("status"),
        "ready_for_intake": health.get("ready_for_intake"),
        "authentication": health.get("authentication"),
        "queue": health.get("queue"),
        "ingress": "PASS",
        "authenticated_pull": "PASS",
        "envelope_verification": "PASS",
        "ack": "PASS" if ack else "SKIPPED",
        "acked": acked,
        "synthetic_event_id": event_id,
        "real_customer_pii_used": False,
        "crm_mutations": 0,
        "provider_mutations": 0,
        "secrets_returned": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave 57 live public gateway smoke")
    parser.add_argument("--gateway-url", default=os.environ.get("BINARIO_GATEWAY_URL", ""))
    parser.add_argument("--tenant-id", default=os.environ.get("BINARIO_GATEWAY_TENANT_ID", ""))
    parser.add_argument("--master-secret", default=os.environ.get("BINARIO_GATEWAY_MASTER_SECRET", ""))
    parser.add_argument("--no-ack", action="store_true")
    args = parser.parse_args()
    if not args.gateway_url or not args.tenant_id or not args.master_secret:
        parser.error("gateway URL, tenant id and master secret are required (arguments or BINARIO_GATEWAY_* env vars)")
    try:
        result = run(args.gateway_url, args.tenant_id, args.master_secret, ack=not args.no_ack)
    except Exception as exc:
        print(json.dumps({
            "schema": "binario.marketing.wave57-live-smoke.v1",
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "secrets_returned": False,
        }, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
