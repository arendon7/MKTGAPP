from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_campaign_results_owner_handoff_app as base


_READY_CREATIVE_STAGES = {"READY", "SCHEDULED", "PUBLISHED", "PAID"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _distinct(rows: list[dict], key: str = "id") -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        value = _text(row.get(key))
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(row)
    return result


def compose_execution_owner_target(
    *,
    action_code: str,
    campaign_id: str,
    creatives: list[dict],
    publications: list[dict],
    paid_media: list[dict],
) -> dict:
    """Resolve the exact final owner target without choosing an arbitrary candidate."""
    code = _text(action_code).upper()
    campaign_id = _text(campaign_id)

    def result(state: str, *, view: str, target_kind: str | None = None,
               candidates: list[dict] | None = None, reason: str) -> dict:
        rows = _distinct(candidates or [])
        target = None
        if state == "TARGET_RESOLVED" and len(rows) == 1 and target_kind:
            target_id = _text(rows[0].get("id"))
            target = {
                "view": view,
                "target_kind": target_kind,
                "target_id": target_id,
                "campaign_id": campaign_id,
                "media_id": target_id if target_kind == "MEDIA" else None,
                "publication_id": target_id if target_kind == "PUBLICATION" else None,
                "paid_media_id": target_id if target_kind == "PAID_MEDIA" else None,
            }
        return {
            "state": state,
            "candidate_count": len(rows),
            "target": target,
            "reason": reason,
        }

    if code == "DEFINE_CHANNELS":
        return result(
            "TARGET_RESOLVED",
            view="campaigns",
            target_kind="CAMPAIGN",
            candidates=[{"id": campaign_id}],
            reason="La campaña canónica es el owner exacto para definir canales.",
        )
    if code == "FIX_PUBLICATION":
        candidates = [row for row in publications if _text(row.get("status")).upper() == "FAILED"]
        state = "TARGET_RESOLVED" if len(_distinct(candidates)) == 1 else (
            "TARGET_NOT_AVAILABLE" if not candidates else "TARGET_AMBIGUOUS"
        )
        return result(
            state,
            view="calendar",
            target_kind="PUBLICATION",
            candidates=candidates,
            reason=(
                "Se exige una única publicación FAILED vinculada a la campaña."
                if state == "TARGET_RESOLVED"
                else "No existe una única publicación FAILED que justifique elegir un registro."
            ),
        )
    if code == "SCHEDULE_OR_PUBLISH":
        candidates = [row for row in publications if _text(row.get("status")).upper() == "DRAFT"]
        state = "TARGET_RESOLVED" if len(_distinct(candidates)) == 1 else (
            "TARGET_NOT_AVAILABLE" if not candidates else "TARGET_AMBIGUOUS"
        )
        return result(
            state,
            view="calendar",
            target_kind="PUBLICATION",
            candidates=candidates,
            reason=(
                "Se exige un único borrador orgánico vinculado a la campaña."
                if state == "TARGET_RESOLVED"
                else "No existe un único borrador orgánico que pueda abrirse sin adivinar."
            ),
        )
    if code == "REVIEW_PAID":
        candidates = [row for row in paid_media if _text(row.get("status")).upper() == "DRAFT"]
        state = "TARGET_RESOLVED" if len(_distinct(candidates)) == 1 else (
            "TARGET_NOT_AVAILABLE" if not candidates else "TARGET_AMBIGUOUS"
        )
        return result(
            state,
            view="pauta",
            target_kind="PAID_MEDIA",
            candidates=candidates,
            reason=(
                "Se exige un único borrador de pauta vinculado a la campaña."
                if state == "TARGET_RESOLVED"
                else "No existe un único borrador de pauta que pueda elevarse como owner exacto."
            ),
        )
    if code == "FINISH_CREATIVE":
        candidates = [
            {"id": _text((row.get("media") or {}).get("id"))}
            for row in creatives
            if _text(row.get("effective_stage")).upper() not in (_READY_CREATIVE_STAGES | {"ARCHIVED"})
        ]
        state = "TARGET_RESOLVED" if len(_distinct(candidates)) == 1 else (
            "TARGET_NOT_AVAILABLE" if not _distinct(candidates) else "TARGET_AMBIGUOUS"
        )
        return result(
            state,
            view="content",
            target_kind="MEDIA",
            candidates=candidates,
            reason=(
                "Existe un único creativo incompleto vinculado a la campaña."
                if state == "TARGET_RESOLVED"
                else "Terminar creativo requiere una única pieza incompleta; no se usa el primer media por posición."
            ),
        )
    if code == "PREPARE_DISTRIBUTION":
        candidates = [
            {"id": _text((row.get("media") or {}).get("id"))}
            for row in creatives
            if _text(row.get("effective_stage")).upper() in _READY_CREATIVE_STAGES
        ]
        state = "TARGET_RESOLVED" if len(_distinct(candidates)) == 1 else (
            "TARGET_NOT_AVAILABLE" if not _distinct(candidates) else "TARGET_AMBIGUOUS"
        )
        return result(
            state,
            view="content",
            target_kind="MEDIA",
            candidates=candidates,
            reason=(
                "Existe un único creativo listo para elegir explícitamente su canal de distribución."
                if state == "TARGET_RESOLVED"
                else "Preparar distribución no elige arbitrariamente uno entre varios creativos listos."
            ),
        )
    if code in {"PLANNED_ONLY", "COMPLETE"}:
        return result(
            "TARGET_RESOLVED",
            view="campaigns",
            target_kind="CAMPAIGN",
            candidates=[{"id": campaign_id}],
            reason="La campaña exacta es suficiente para esta navegación de contexto.",
        )
    if code == "CREATE_CREATIVE":
        return result(
            "OWNER_ONLY",
            view="content",
            reason="Todavía no existe un media vinculado que pueda actuar como target exacto.",
        )
    if code == "CALENDAR":
        return result(
            "OWNER_ONLY",
            view="calendar",
            reason="La campaña ya tiene calendario activo, pero esta acción no identifica una publicación única.",
        )
    if code == "COORDINATE":
        return result(
            "OWNER_ONLY",
            view="content",
            reason="Coordinar conserva el owner creativo sin afirmar una pieza única.",
        )
    return result(
        "OWNER_ONLY",
        view="execution",
        reason="La acción W64 no requiere ni demuestra un segundo target exacto en esta capa.",
    )


class AppRuntime(base.AppRuntime):
    """Resolve exact W64 owner identity using local canonical stores only."""

    def _execution_owner_inputs(self, company_id: str, campaign_id: str) -> tuple[dict, list[dict], list[dict], list[dict]]:
        company = self.companies.get(company_id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)

        execution = self.campaign_execution_workspace(company.id)
        execution_matches = [
            row for row in execution.get("campaigns") or []
            if _text((row.get("campaign") or {}).get("id")) == campaign.id
        ]
        if len(execution_matches) != 1:
            raise ValueError("campaign execution context is not uniquely represented")
        execution_row = execution_matches[0]

        all_creatives = self.company_creatives_payload(company.id)
        media_ids = set(campaign.media_ids)
        linked_creatives: list[dict] = []
        for row in all_creatives:
            media_id = _text((row.get("media") or {}).get("id"))
            creative = row.get("creative") or {}
            if media_id in media_ids or _text(creative.get("campaign_id")) == campaign.id:
                linked_creatives.append(row)
                if media_id:
                    media_ids.add(media_id)

        publication_ids = set(campaign.publication_ids)
        paid_ids: set[str] = set()
        for row in linked_creatives:
            creative = row.get("creative") or {}
            publication_ids.update(_text(value) for value in creative.get("publication_ids") or [] if _text(value))
            paid_ids.update(_text(value) for value in creative.get("paid_media_ids") or [] if _text(value))

        publications: list[dict] = []
        for publication_id in sorted(publication_ids):
            try:
                publication = self.social.get(publication_id)
            except KeyError:
                continue
            if publication.project_id != company.id:
                continue
            publications.append({
                "id": publication.id,
                "status": publication.status,
                "channel": publication.channel,
                "scheduled_for": publication.scheduled_for,
            })

        paid_rows = self.company_paid_media(company.id)
        linked_paid: list[dict] = []
        for row in paid_rows:
            plan = row.get("plan") or {}
            if _text(plan.get("campaign_id")) == campaign.id or _text(row.get("id")) in paid_ids:
                linked_paid.append({
                    "id": row.get("id"),
                    "status": row.get("status"),
                })

        return execution_row, linked_creatives, publications, _distinct(linked_paid)

    def execution_owner_context(self, company_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        execution_row, creatives, publications, paid_media = self._execution_owner_inputs(company.id, campaign.id)
        next_action = execution_row.get("next_action") or {}
        resolution = compose_execution_owner_target(
            action_code=_text(next_action.get("code")),
            campaign_id=campaign.id,
            creatives=creatives,
            publications=publications,
            paid_media=paid_media,
        )
        return {
            "schema": "binario.marketing.execution-owner-relay.v1",
            "company": {"id": company.id, "name": company.name},
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
            },
            "execution_next_action": {
                "code": _text(next_action.get("code")).upper(),
                "label": _text(next_action.get("label")),
                "view": _text(next_action.get("view")),
                "media_id": _text(next_action.get("media_id")) or None,
            },
            "resolution": resolution,
            "contracts": {
                "wave64_is_execution_authority": True,
                "canonical_stores_are_identity_authority": True,
                "unique_target_required": True,
                "no_first_candidate_guessing": True,
                "navigation_only": True,
                "business_mutation_authority": False,
            },
            "safety": {
                "read_only_projection": True,
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "business_mutation_performed": False,
                "ai_generation_performed": False,
                "automatic_execution": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Append the exact execution owner relay after the current terminal."""

    def _execution_owner_relay_error(self, exc: Exception) -> None:
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
;(function loadPostW99ExecutionOwnerRelay(){
  if(document.querySelector('script[data-post-w99-execution-owner-relay]'))return;
  const script=document.createElement('script');
  script.src='/execution-owner-relay.js';
  script.defer=true;
  script.dataset.postW99ExecutionOwnerRelay='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/execution-owner-relay.js":
            target = self.server.runtime.repo_root / "web" / "execution-owner-relay.js"
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
        if path == "/execution-owner-relay.js":
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
                self._json(self.server.runtime.execution_owner_context(parts[2], parts[4]))
                return
        except Exception as exc:
            self._execution_owner_relay_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Execution Owner Relay: {url}")
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
    "compose_execution_owner_target",
    "create_server",
    "serve",
]
