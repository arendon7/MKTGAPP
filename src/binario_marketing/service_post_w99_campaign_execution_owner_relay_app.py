from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_campaign_results_owner_handoff_app as base


_EXECUTION_OWNER_ACTION_KINDS = {
    "fix_execution",
    "define_channels",
    "finish_creative",
    "prepare_distribution",
    "calendar",
    "schedule_or_publish",
    "review_paid",
    "planned_only",
    "complete",
    "create_creative",
    "coordinate",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _candidate_publication(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "channel": row.get("channel"),
        "scheduled_for": row.get("scheduled_for"),
    }


def _candidate_media(row: dict) -> dict:
    media = row.get("media") or {}
    return {
        "id": media.get("id"),
        "stage": row.get("effective_stage"),
        "name": (row.get("creative") or {}).get("title") or media.get("original_name"),
    }


def _candidate_paid(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "campaign_name": row.get("campaign_name"),
    }


def _owner_resolution(
    *,
    campaign_id: str,
    next_action: dict,
    linked_creatives: list[dict],
    publications: list[dict],
    linked_paid: list[dict],
) -> dict:
    code = _text(next_action.get("code")).upper() or "UNKNOWN"
    view = _text(next_action.get("view")) or "execution"

    def exact(
        owner_view: str,
        target_kind: str,
        target_id: str,
        reason: str,
        candidates: list[dict] | None = None,
    ) -> dict:
        return {
            "state": "EXACT_TARGET",
            "source_code": code,
            "owner_view": owner_view,
            "target_kind": target_kind,
            "target_id": target_id,
            "candidate_count": len(candidates or [target_id]),
            "candidates": candidates or [],
            "reason": reason,
        }

    def cardinality(
        rows: list[dict],
        *,
        owner_view: str,
        target_kind: str,
        candidate_builder,
        empty_state: str,
        exact_reason: str,
        ambiguous_reason: str,
        empty_reason: str,
    ) -> dict:
        candidates = [candidate_builder(row) for row in rows]
        if len(rows) == 1:
            return exact(owner_view, target_kind, _text(candidates[0].get("id")), exact_reason, candidates)
        return {
            "state": "AMBIGUOUS_TARGET" if len(rows) > 1 else empty_state,
            "source_code": code,
            "owner_view": owner_view,
            "target_kind": target_kind if len(rows) > 1 else None,
            "target_id": None,
            "candidate_count": len(rows),
            "candidates": candidates,
            "reason": ambiguous_reason if len(rows) > 1 else empty_reason,
        }

    if code in {"DEFINE_CHANNELS", "PLANNED_ONLY", "COMPLETE"}:
        return exact(
            "campaigns",
            "CAMPAIGN",
            campaign_id,
            "El siguiente owner sigue siendo la campaña canónica y campaign_id ya identifica un único plan local.",
        )

    if code == "FIX_PUBLICATION":
        rows = [row for row in publications if _text(row.get("status")).upper() == "FAILED"]
        return cardinality(
            rows,
            owner_view="calendar",
            target_kind="PUBLICATION",
            candidate_builder=_candidate_publication,
            empty_state="NO_TARGET",
            exact_reason="Existe exactamente una publicación fallida vinculada a la campaña; puede abrirse por publication_id sin inferencia.",
            ambiguous_reason="Hay varias publicaciones fallidas vinculadas. No se elige una por fecha, canal, orden ni similitud.",
            empty_reason="W64 reporta corrección de publicación pero la lectura local ya no contiene una publicación FAILED vinculada; se conserva el owner de ejecución.",
        )

    if code in {"FINISH_CREATIVE", "PREPARE_DISTRIBUTION"}:
        media_id = _text(next_action.get("media_id"))
        rows = [row for row in linked_creatives if _text((row.get("media") or {}).get("id")) == media_id]
        if media_id and len(rows) == 1:
            return exact(
                "content",
                "MEDIA",
                media_id,
                "W64 declaró un media_id y la campaña contiene exactamente ese creativo canónico.",
                [_candidate_media(rows[0])],
            )
        return {
            "state": "AMBIGUOUS_TARGET" if len(rows) > 1 else "NO_TARGET",
            "source_code": code,
            "owner_view": "content",
            "target_kind": "MEDIA" if rows else None,
            "target_id": None,
            "candidate_count": len(rows),
            "candidates": [_candidate_media(row) for row in rows],
            "reason": "El media_id de W64 no identifica exactamente un creativo vinculado; no se selecciona otro creativo.",
        }

    if code == "SCHEDULE_OR_PUBLISH":
        rows = [row for row in publications if _text(row.get("status")).upper() == "DRAFT"]
        return cardinality(
            rows,
            owner_view="calendar",
            target_kind="PUBLICATION",
            candidate_builder=_candidate_publication,
            empty_state="NO_TARGET",
            exact_reason="Existe exactamente un borrador de publicación vinculado; el calendario puede abrir ese publication_id.",
            ambiguous_reason="Hay varios borradores de publicación vinculados; programar exige elegir explícitamente cuál y el relay no lo adivina.",
            empty_reason="W64 reporta un borrador pero ya no existe uno vinculado en la lectura local; se conserva el owner original.",
        )

    if code == "CALENDAR":
        rows = [row for row in publications if _text(row.get("status")).upper() == "QUEUED"]
        return cardinality(
            rows,
            owner_view="calendar",
            target_kind="PUBLICATION",
            candidate_builder=_candidate_publication,
            empty_state="OWNER_ONLY",
            exact_reason="Una única publicación programada representa el estado de calendario de la campaña y puede revisarse por ID exacto.",
            ambiguous_reason="Hay varias publicaciones programadas; revisar calendario es una acción de owner y no autoriza escoger una fila automáticamente.",
            empty_reason="No hay una publicación QUEUED única; abrir Calendario sigue siendo válido como owner, pero no existe target exacto.",
        )

    if code == "REVIEW_PAID":
        rows = [row for row in linked_paid if _text(row.get("status")).upper() == "DRAFT"]
        return cardinality(
            rows,
            owner_view="pauta",
            target_kind="PAID_DRAFT",
            candidate_builder=_candidate_paid,
            empty_state="NO_TARGET",
            exact_reason="Existe exactamente un plan de pauta DRAFT vinculado a la campaña; puede revisarse por draft_id local.",
            ambiguous_reason="Hay varios planes DRAFT vinculados; el relay no decide cuál revisar ni cuál crear remotamente.",
            empty_reason="W64 reporta pauta en borrador pero ya no existe un DRAFT vinculado; se conserva el owner original.",
        )

    if code == "REVIEW_RESULTS":
        return exact(
            "analytics",
            "CAMPAIGN_RESULTS",
            campaign_id,
            "La identidad final sigue siendo campaign_id y Campaign Results Owner Handoff ya certifica ese contexto local.",
        )

    if code in {"CREATE_CREATIVE", "COORDINATE"}:
        return {
            "state": "OWNER_ONLY",
            "source_code": code,
            "owner_view": view or "content",
            "target_kind": None,
            "target_id": None,
            "candidate_count": 0,
            "candidates": [],
            "reason": "La acción crea o coordina trabajo nuevo y no existe un objeto canónico único que el relay pueda seleccionar de antemano.",
        }

    return {
        "state": "OWNER_ONLY",
        "source_code": code,
        "owner_view": view,
        "target_kind": None,
        "target_id": None,
        "candidate_count": 0,
        "candidates": [],
        "reason": "W64 define un owner, pero este código no declara una identidad final única en el contrato actual.",
    }


def _rewrite_action_from_resolution(row: dict, resolution: dict) -> dict:
    result = deepcopy(row)
    result["owner_resolution"] = deepcopy(resolution)
    if resolution.get("state") != "EXACT_TARGET":
        return result

    action = dict(result.get("action") or {})
    target_kind = _text(resolution.get("target_kind")).upper()
    target_id = _text(resolution.get("target_id"))
    owner_view = _text(resolution.get("owner_view"))
    if not target_id or not owner_view:
        return result

    action["view"] = owner_view
    action["tab"] = None
    if target_kind == "PUBLICATION":
        action["entity_id"] = target_id
        action["label"] = "Abrir publicación exacta"
    elif target_kind == "MEDIA":
        action["media_id"] = target_id
        action["label"] = "Abrir creativo exacto"
    elif target_kind == "CAMPAIGN":
        action["campaign_id"] = target_id
        action["label"] = "Abrir campaña exacta"
    elif target_kind == "PAID_DRAFT":
        action["entity_id"] = target_id
        action["label"] = "Abrir plan de pauta exacto"
    elif target_kind == "CAMPAIGN_RESULTS":
        action["campaign_id"] = target_id
        action["label"] = "Abrir resultados exactos"
    result["action"] = action
    return result


def _copy_routed_rows(payload: dict, routed: dict[str, dict]) -> None:
    if payload.get("next_action"):
        action_id = _text(payload["next_action"].get("id"))
        if action_id in routed:
            payload["next_action"] = routed[action_id]
    focus = payload.get("focus") or {}
    for lane in ("now", "next", "later"):
        focus[lane] = [routed.get(_text(row.get("id")), row) for row in focus.get(lane) or []]
    payload["focus"] = focus


class AppRuntime(base.AppRuntime):
    """Resolve W64 campaign next-actions to exact existing owners when identity is provable."""

    def campaign_execution_owner_context(self, company_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        workspace = self.campaign_execution_workspace(company.id)
        cards = [row for row in workspace.get("campaigns") or [] if (row.get("campaign") or {}).get("id") == campaign.id]
        if len(cards) != 1:
            raise ValueError("campaign execution context is not uniquely represented")
        card = cards[0]

        creative_rows = self.company_creatives_payload(company.id)
        media_ids = set(campaign.media_ids)
        linked_creatives = [
            row for row in creative_rows
            if (row.get("media") or {}).get("id") in media_ids
            or ((row.get("creative") or {}).get("campaign_id") == campaign.id)
        ]
        for row in linked_creatives:
            media_id = (row.get("media") or {}).get("id")
            if media_id:
                media_ids.add(media_id)

        publication_ids = set(campaign.publication_ids)
        paid_ids: set[str] = set()
        for row in linked_creatives:
            creative = row.get("creative") or {}
            publication_ids.update(creative.get("publication_ids") or [])
            paid_ids.update(creative.get("paid_media_ids") or [])

        publications: list[dict] = []
        for publication_id in sorted(publication_ids):
            try:
                publication = self.social.get(publication_id)
            except KeyError:
                continue
            if publication.project_id != company.id:
                continue
            publications.append(asdict(publication))

        paid_rows = self.company_paid_media(company.id)
        paid_by_id = {row.get("id"): row for row in paid_rows if row.get("id")}
        linked_paid = [
            row for row in paid_rows
            if row.get("plan") and (row.get("plan") or {}).get("campaign_id") == campaign.id
        ]
        for draft_id in sorted(paid_ids):
            row = paid_by_id.get(draft_id)
            if row is not None and all(existing.get("id") != draft_id for existing in linked_paid):
                linked_paid.append(row)

        next_action = card.get("next_action") or {}
        resolution = _owner_resolution(
            campaign_id=campaign.id,
            next_action=next_action,
            linked_creatives=linked_creatives,
            publications=publications,
            linked_paid=linked_paid,
        )
        return {
            "schema": "binario.marketing.campaign-execution-owner-context.v1",
            "company": {"id": company.id, "name": company.name},
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "channels": list(campaign.channels),
            },
            "execution": {
                "next_action": deepcopy(next_action),
                "requires_action": bool(card.get("requires_action")),
                "creative_total": len(linked_creatives),
                "publication_total": len(publications),
                "paid_total": len(linked_paid),
            },
            "resolution": resolution,
            "contracts": {
                "w64_remains_next_action_authority": True,
                "exact_target_requires_canonical_id": True,
                "ambiguous_target_fails_closed": True,
                "owner_resolution_does_not_reprioritize": True,
                "existing_owner_mutation_authority_preserved": True,
                "w65_results_actions_remain_results_owner_authority": True,
            },
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "business_mutation_performed": False,
                "ai_generation_performed": False,
                "automatic_execution": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }

    def action_center(self, company_id: str) -> dict:
        payload = deepcopy(super().action_center(company_id))
        routed: dict[str, dict] = {}
        contexts: dict[str, dict] = {}
        for row in payload.get("queue") or []:
            action_id = _text(row.get("id"))
            action = row.get("action") or {}
            kind = _text(row.get("kind")).lower()
            campaign_id = _text(action.get("campaign_id"))
            current = row
            if campaign_id and kind in _EXECUTION_OWNER_ACTION_KINDS:
                try:
                    context = contexts.get(campaign_id)
                    if context is None:
                        context = self.campaign_execution_owner_context(company_id, campaign_id)
                        contexts[campaign_id] = context
                    current = _rewrite_action_from_resolution(row, context.get("resolution") or {})
                except (KeyError, ValueError, TypeError):
                    current = row
            if action_id:
                routed[action_id] = current
        payload["queue"] = [routed.get(_text(row.get("id")), row) for row in payload.get("queue") or []]
        _copy_routed_rows(payload, routed)
        contracts = dict(payload.get("contracts") or {})
        contracts.update({
            "campaign_execution_owner_resolution_is_local": True,
            "campaign_execution_exact_target_requires_unique_identity": True,
            "campaign_execution_ambiguous_target_fails_closed": True,
            "campaign_execution_owner_resolution_does_not_reprioritize": True,
            "w65_results_actions_remain_results_owner_authority": True,
        })
        payload["contracts"] = contracts
        return payload


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Add a GET-only W64 owner resolver and browser deep-link adapter."""

    def _campaign_execution_owner_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/campaign-results-owner-handoff.js":
            target = self.server.runtime.repo_root / "web" / "campaign-results-owner-handoff.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignExecutionOwnerAfterResultsOwner(){
  if(document.querySelector('script[data-post-w99-campaign-execution-owner]'))return;
  const script=document.createElement('script');
  script.src='/campaign-execution-owner-relay.js';
  script.defer=true;
  script.dataset.postW99CampaignExecutionOwner='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/campaign-execution-owner-relay.js":
            target = self.server.runtime.repo_root / "web" / "campaign-execution-owner-relay.js"
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
        if path == "/campaign-execution-owner-relay.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "campaigns"
                and parts[5] == "execution-owner-context"
            ):
                self._json(self.server.runtime.campaign_execution_owner_context(parts[2], parts[4]))
                return
        except Exception as exc:
            self._campaign_execution_owner_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Campaign Execution Owner Relay: {url}")
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


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
