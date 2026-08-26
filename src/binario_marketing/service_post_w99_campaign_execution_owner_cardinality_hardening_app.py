from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_campaign_coordinate_recovery_guidance_app as base
from . import service_post_w99_campaign_execution_owner_relay_app as owner_relay


_READY_CREATIVE_STAGES = {"READY", "SCHEDULED", "PUBLISHED", "PAID"}
_MEDIA_EXECUTION_CODES = {"FINISH_CREATIVE", "PREPARE_DISTRIBUTION"}


def _semantic_media_candidates(code: str, linked_creatives: list[dict]) -> list[dict]:
    normalized = owner_relay._text(code).upper()
    if normalized == "FINISH_CREATIVE":
        return [
            row for row in linked_creatives
            if owner_relay._text(row.get("effective_stage")).upper()
            not in (_READY_CREATIVE_STAGES | {"ARCHIVED"})
        ]
    if normalized == "PREPARE_DISTRIBUTION":
        return [
            row for row in linked_creatives
            if owner_relay._text(row.get("effective_stage")).upper() in _READY_CREATIVE_STAGES
        ]
    return []


def _harden_media_resolution(*, next_action: dict, linked_creatives: list[dict], inherited_resolution: dict) -> dict:
    """Require semantic cardinality before promoting W64 media_id to final identity."""
    code = owner_relay._text(next_action.get("code")).upper()
    if code not in _MEDIA_EXECUTION_CODES:
        return deepcopy(inherited_resolution)

    eligible = _semantic_media_candidates(code, linked_creatives)
    candidates = [owner_relay._candidate_media(row) for row in eligible]
    media_id = owner_relay._text(next_action.get("media_id"))

    if len(eligible) > 1:
        return {
            "state": "AMBIGUOUS_TARGET",
            "source_code": code,
            "owner_view": "content",
            "target_kind": "MEDIA",
            "target_id": None,
            "candidate_count": len(eligible),
            "candidates": candidates,
            "reason": (
                "Hay varios creativos semánticamente elegibles para esta acción W64. "
                "El media_id posicional no se convierte en autoridad de identidad y no se elige una pieza por orden."
            ),
        }

    if not eligible:
        return {
            "state": "NO_TARGET",
            "source_code": code,
            "owner_view": "content",
            "target_kind": None,
            "target_id": None,
            "candidate_count": 0,
            "candidates": [],
            "reason": (
                "La lectura local ya no contiene un creativo semánticamente elegible para la acción W64; "
                "se conserva el owner sin inventar un media."
            ),
        }

    candidate_id = owner_relay._text((eligible[0].get("media") or {}).get("id"))
    if not media_id or media_id != candidate_id:
        return {
            "state": "NO_TARGET",
            "source_code": code,
            "owner_view": "content",
            "target_kind": "MEDIA",
            "target_id": None,
            "candidate_count": 1,
            "candidates": candidates,
            "reason": (
                "Existe un único creativo semánticamente elegible, pero no coincide con el media_id declarado por W64. "
                "La divergencia falla cerrada en vez de sustituir el target."
            ),
        }

    return {
        "state": "EXACT_TARGET",
        "source_code": code,
        "owner_view": "content",
        "target_kind": "MEDIA",
        "target_id": candidate_id,
        "candidate_count": 1,
        "candidates": candidates,
        "reason": (
            "Existe exactamente un creativo semánticamente elegible y su media_id coincide con W64; "
            "la identidad final puede elevarse sin depender del orden de una lista."
        ),
    }


class AppRuntime(base.AppRuntime):
    """Preserve Coordinate Recovery Guidance while hardening normal W64 MEDIA identity."""

    def campaign_execution_owner_context(self, company_id: str, campaign_id: str) -> dict:
        payload = super().campaign_execution_owner_context(company_id, campaign_id)
        next_action = (payload.get("execution") or {}).get("next_action") or {}
        code = owner_relay._text(next_action.get("code")).upper()

        contracts = dict(payload.get("contracts") or {})
        contracts.update({
            "media_identity_requires_semantic_cardinality": True,
            "w64_positional_media_id_is_not_identity_authority": True,
        })
        if code not in _MEDIA_EXECUTION_CODES:
            payload["contracts"] = contracts
            return payload

        company = self.companies.get(company_id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        creative_rows = self.company_creatives_payload(company.id)
        media_ids = set(campaign.media_ids)
        linked_creatives = [
            row for row in creative_rows
            if (row.get("media") or {}).get("id") in media_ids
            or ((row.get("creative") or {}).get("campaign_id") == campaign.id)
        ]
        payload["resolution"] = _harden_media_resolution(
            next_action=next_action,
            linked_creatives=linked_creatives,
            inherited_resolution=payload.get("resolution") or {},
        )
        contracts["single_semantic_media_must_match_w64_media_id"] = True
        payload["contracts"] = contracts
        return payload


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Load the zero-transport cardinality adapter after Coordinate Recovery Guidance."""

    def _static(self, path: str) -> None:
        if path == "/campaign-coordinate-recovery-guidance.js":
            target = self.server.runtime.repo_root / "web" / "campaign-coordinate-recovery-guidance.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignExecutionOwnerCardinalityHardening(){
  if(document.querySelector('script[data-post-w99-campaign-execution-owner-cardinality-hardening]'))return;
  const script=document.createElement('script');
  script.src='/campaign-execution-owner-cardinality-hardening.js';
  script.defer=true;
  script.dataset.postW99CampaignExecutionOwnerCardinalityHardening='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/campaign-execution-owner-cardinality-hardening.js":
            target = self.server.runtime.repo_root / "web" / "campaign-execution-owner-cardinality-hardening.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/campaign-execution-owner-cardinality-hardening.js":
            self._static(path)
            return
        super().do_GET()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App · post-W99 Campaign Execution Owner Cardinality Hardening: {url}")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = [
    "AppRuntime",
    "MarketingHandler",
    "MarketingHTTPServer",
    "_harden_media_resolution",
    "_semantic_media_candidates",
    "create_server",
    "serve",
]
