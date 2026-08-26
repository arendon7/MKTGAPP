from __future__ import annotations

from copy import deepcopy

from . import service_post_w99_planned_only_actionability_app as base


_ACTIVE_CAMPAIGN_STATUSES = {"PLANNING", "READY", "IN_PROGRESS"}
_SETUP_SHADOW_SCHEMA = "binario.marketing.setup-shadow-action.v1"


def _text(value: object) -> str:
    return str(value or "").strip()


def _focus_from_queue(queue: list[dict]) -> dict:
    return {
        "now": [row for row in queue if _text(row.get("urgency")).upper() in {"CRITICAL", "HIGH"}][:8],
        "next": [row for row in queue if _text(row.get("urgency")).upper() == "MEDIUM"][:8],
        "later": [row for row in queue if _text(row.get("urgency")).upper() == "LOW"][:8],
    }


def _campaign_action_ids(queue: list[dict], kind: str) -> set[str]:
    result: set[str] = set()
    expected = kind.lower()
    for row in queue:
        if _text(row.get("source")).upper() != "CAMPAIGN":
            continue
        if _text(row.get("kind")).lower() != expected:
            continue
        campaign_id = _text((row.get("action") or {}).get("campaign_id"))
        if campaign_id:
            result.add(campaign_id)
    return result


def _review_paid_candidate_ids(queue: list[dict]) -> set[str]:
    """Return only canonically enumerated DRAFT IDs from valid REVIEW_PAID resolutions."""
    result: set[str] = set()
    for row in queue:
        if _text(row.get("source")).upper() != "CAMPAIGN":
            continue
        if _text(row.get("kind")).lower() != "review_paid":
            continue
        resolution = row.get("owner_resolution") or {}
        if _text(resolution.get("source_code")).upper() != "REVIEW_PAID":
            continue
        if _text(resolution.get("owner_view")) != "pauta":
            continue
        if _text(resolution.get("target_kind")).upper() != "PAID_DRAFT":
            continue
        state = _text(resolution.get("state")).upper()
        if state not in {"EXACT_TARGET", "AMBIGUOUS_TARGET"}:
            continue
        candidates = list(resolution.get("candidates") or [])
        if not candidates or any(not isinstance(candidate, dict) for candidate in candidates):
            continue
        ids = [_text(candidate.get("id")) for candidate in candidates]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            continue
        if any(_text(candidate.get("status")).upper() != "DRAFT" for candidate in candidates):
            continue
        try:
            candidate_count = int(resolution.get("candidate_count"))
        except (TypeError, ValueError):
            continue
        if candidate_count != len(candidates):
            continue
        target_id = _text(resolution.get("target_id"))
        if state == "EXACT_TARGET":
            if len(candidates) != 1 or target_id != ids[0]:
                continue
        else:
            if len(candidates) < 2 or target_id:
                continue
        result.update(ids)
    return result


def _shadowed_copy(row: dict, *, reason_code: str, reason: str, evidence: dict) -> dict:
    shadow = deepcopy(row)
    shadow["requires_human_action"] = False
    shadow["blocking"] = False
    shadow["shadowing"] = {
        "schema": _SETUP_SHADOW_SCHEMA,
        "state": "SUPERSEDED_BY_CANONICAL_ACTIONS",
        "today_eligible": False,
        "reason_code": reason_code,
        "reason": reason,
        "evidence": deepcopy(evidence),
    }
    return shadow


def deduplicate_setup_shadow_actions(
    payload: dict,
    *,
    active_campaigns_without_media: set[str],
    paid_draft_ids: set[str],
    creative_profile_exists: bool,
) -> dict:
    """Remove only setup aggregates proven to be fully represented by canonical work.

    The transform is deliberately fail-closed. Partial, malformed, stale or ambiguous
    coverage keeps the aggregate setup row in the actionable queue.
    """
    result = deepcopy(payload)
    inherited_queue = list(result.get("queue") or [])
    create_creative_campaigns = _campaign_action_ids(inherited_queue, "create_creative")
    review_paid_ids = _review_paid_candidate_ids(inherited_queue)

    actionable: list[dict] = []
    newly_shadowed: list[dict] = []

    for row in inherited_queue:
        if _text(row.get("source")).upper() != "SETUP":
            actionable.append(row)
            continue

        kind = _text(row.get("kind")).lower()
        shadow = None

        if (
            kind == "campaign_media"
            and active_campaigns_without_media
            and active_campaigns_without_media.issubset(create_creative_campaigns)
        ):
            shadow = _shadowed_copy(
                row,
                reason_code="CAMPAIGN_MEDIA_FULLY_COVERED",
                reason=(
                    "Cada campaña activa que todavía no tiene media ya está representada por "
                    "una acción CAMPAIGN/create_creative con campaign_id canónico."
                ),
                evidence={
                    "gap_campaign_ids": sorted(active_campaigns_without_media),
                    "covering_campaign_ids": sorted(create_creative_campaigns),
                },
            )

        elif (
            kind == "setup_creative"
            and not creative_profile_exists
            and bool(create_creative_campaigns)
        ):
            shadow = _shadowed_copy(
                row,
                reason_code="CREATIVE_READINESS_COVERED_BY_CREATE_FLOW",
                reason=(
                    "Creative Studio aún no tiene un perfil guardado, pero existe al menos una "
                    "acción create_creative de campaña que abre el flujo canónico que resuelve esa readiness."
                ),
                evidence={"covering_campaign_ids": sorted(create_creative_campaigns)},
            )

        elif (
            kind == "paid_draft"
            and paid_draft_ids
            and paid_draft_ids.issubset(review_paid_ids)
        ):
            shadow = _shadowed_copy(
                row,
                reason_code="PAID_DRAFTS_FULLY_COVERED",
                reason=(
                    "Todos los planes de pauta DRAFT canónicos están enumerados por resoluciones "
                    "REVIEW_PAID exactas o ambiguas; el agregado no añade trabajo distinto."
                ),
                evidence={
                    "gap_paid_draft_ids": sorted(paid_draft_ids),
                    "covering_paid_draft_ids": sorted(review_paid_ids),
                },
            )

        if shadow is None:
            actionable.append(row)
        else:
            newly_shadowed.append(shadow)

    existing = list(result.get("shadowed_actions") or [])
    existing_ids = {_text(row.get("id")) for row in existing}
    for row in newly_shadowed:
        row_id = _text(row.get("id"))
        if row_id and row_id not in existing_ids:
            existing.append(row)
            existing_ids.add(row_id)

    result["queue"] = actionable
    result["next_action"] = actionable[0] if actionable else None
    result["focus"] = _focus_from_queue(actionable)
    result["shadowed_actions"] = existing

    urgency_counts = {key: 0 for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    source_counts = {key: 0 for key in ("OPERATIONS", "COMMERCIAL", "CAMPAIGN", "SETUP")}
    for row in actionable:
        urgency = _text(row.get("urgency")).upper()
        source = _text(row.get("source")).upper() or "OTHER"
        if urgency in urgency_counts:
            urgency_counts[urgency] += 1
        source_counts[source] = source_counts.get(source, 0) + 1

    summary = dict(result.get("summary") or {})
    summary.update({
        "queue_total": len(actionable),
        "blocking": sum(1 for row in actionable if row.get("blocking")),
        "critical": urgency_counts["CRITICAL"],
        "high": urgency_counts["HIGH"],
        "medium": urgency_counts["MEDIUM"],
        "low": urgency_counts["LOW"],
        "by_source": source_counts,
        "campaign_actions": sum(
            1 for row in actionable if _text(row.get("source")).upper() == "CAMPAIGN"
        ),
        "shadowed_actions_total": len(existing),
        "shadowed_setup_actions": sum(
            1 for row in existing if _text(row.get("source")).upper() == "SETUP"
        ),
    })
    result["summary"] = summary

    contracts = dict(result.get("contracts") or {})
    contracts.update({
        "setup_shadow_deduplication_fail_closed": True,
        "setup_shadow_requires_full_canonical_coverage": True,
        "partial_setup_coverage_remains_actionable": True,
        "specific_canonical_actions_are_never_removed": True,
        "shadowed_setup_excluded_from_today": True,
        "setup_shadow_deduplication_is_read_only": True,
    })
    result["contracts"] = contracts
    return result


class AppRuntime(base.AppRuntime):
    """Deduplicate aggregate setup work only when canonical coverage is provable."""

    def action_center(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        inherited = super().action_center(company.id)

        active_campaigns_without_media = {
            row.id
            for row in self.campaigns.list(company.id)
            if row.status in _ACTIVE_CAMPAIGN_STATUSES and not row.media_ids
        }
        paid_draft_ids = {
            _text(row.get("id"))
            for row in self.company_paid_media(company.id)
            if _text(row.get("status")).upper() == "DRAFT" and _text(row.get("id"))
        }
        creative = self.creative_context(company.id)
        creative_profile_exists = any(
            bool(row.get("creative")) for row in (creative.get("items") or [])
        )

        return deduplicate_setup_shadow_actions(
            inherited,
            active_campaigns_without_media=active_campaigns_without_media,
            paid_draft_ids=paid_draft_ids,
            creative_profile_exists=creative_profile_exists,
        )


MarketingHTTPServer = base.MarketingHTTPServer
MarketingHandler = base.MarketingHandler


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App · post-W99 Setup Shadow Action Deduplication: {url}")
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
    "create_server",
    "deduplicate_setup_shadow_actions",
    "serve",
]
