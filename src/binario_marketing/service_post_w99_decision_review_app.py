from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_commercial_outcomes_app as base
from . import service_post_w99_action_center_app as action_base


_TERMINAL_CAMPAIGN_STATUSES = {"COMPLETED", "ARCHIVED"}
_REVIEW_RANK = {
    "FOLLOW_THROUGH_REQUIRED": (47, "MEDIUM"),
    "READY_FOR_REVIEW": (49, "MEDIUM"),
}


def _parse_timestamp(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_after(candidate: object, anchor: object) -> bool:
    return _parse_timestamp(candidate) > _parse_timestamp(anchor)


def _latest_campaign_decisions(runtime, company_id: str) -> dict[str, object]:
    latest: dict[str, object] = {}
    for decision in runtime.learning.list_decisions(company_id, limit=200):
        if decision.entity_kind != "CAMPAIGN":
            continue
        latest.setdefault(decision.entity_id, decision)
    return latest


def _credited_opportunities(runtime, company_id: str) -> dict[str, list[dict]]:
    """Reconstruct canonical LAST_CAPTURED_TOUCH credit for compact review evidence."""
    links = {row.id: row for row in runtime.attribution.list_links(company_id)}
    primary_by_opportunity = {}
    for claim in runtime.attribution.list_claims(company_id):
        opportunity_id = claim.opportunity_id
        if not opportunity_id:
            continue
        current = primary_by_opportunity.get(opportunity_id)
        candidate_key = (_parse_timestamp(claim.captured_at), claim.id)
        current_key = ((_parse_timestamp(current.captured_at), current.id) if current is not None else None)
        if current is None or candidate_key > current_key:
            primary_by_opportunity[opportunity_id] = claim

    by_campaign: dict[str, list[dict]] = {}
    for opportunity_id, claim in primary_by_opportunity.items():
        link = links.get(claim.tracking_link_id)
        if link is None:
            continue
        try:
            opportunity = runtime.crm.get_opportunity(opportunity_id)
        except KeyError:
            continue
        if opportunity.company_id != company_id:
            continue
        event_at = max(
            (claim.captured_at, opportunity.updated_at),
            key=_parse_timestamp,
        )
        by_campaign.setdefault(link.campaign_id, []).append({
            "opportunity_id": opportunity.id,
            "stage": opportunity.stage,
            "value": opportunity.value,
            "currency": opportunity.currency,
            "attribution_captured_at": claim.captured_at,
            "crm_updated_at": opportunity.updated_at,
            "event_at": event_at,
            "credit_model": "LAST_CAPTURED_TOUCH",
        })
    for rows in by_campaign.values():
        rows.sort(key=lambda row: (_parse_timestamp(row["event_at"]), row["opportunity_id"]), reverse=True)
    return by_campaign


def decision_review_projection(runtime, company_id: str) -> dict:
    """Review human campaign decisions only when later evidence actually exists.

    The projection deliberately does not infer that a decision caused later marketing
    metrics, CRM movement or revenue. It only establishes temporal availability of
    evidence after the recorded human decision.
    """
    company = runtime.companies.get(company_id)
    campaigns = list(runtime.campaigns.list(company.id))
    latest_decisions = _latest_campaign_decisions(runtime, company.id)
    snapshots = runtime.learning.list_snapshots(company.id, limit=100)
    credited = _credited_opportunities(runtime, company.id)
    commercial = runtime.commercial_outcomes(company.id)
    commercial_by_campaign = {
        row["campaign"]["id"]: row for row in commercial.get("campaigns") or []
    }

    snapshot_rollup_cache: dict[str, dict[str, dict]] = {}

    def observed_after(campaign_id: str, decision_created_at: str) -> dict | None:
        for snapshot in snapshots:
            if not _is_after(snapshot.created_at, decision_created_at):
                continue
            if snapshot.id not in snapshot_rollup_cache:
                rollups = runtime._learning_rollups(company.id, snapshot)
                snapshot_rollup_cache[snapshot.id] = {
                    row["id"]: row for row in rollups.get("campaigns") or []
                }
            row = snapshot_rollup_cache[snapshot.id].get(campaign_id)
            if not row or row.get("evidence") != "OBSERVED":
                continue
            return {
                "snapshot_id": snapshot.id,
                "created_at": snapshot.created_at,
                "date_preset": snapshot.date_preset,
                "organic_observations": int(row.get("organic_observations") or 0),
                "paid_observations": int(row.get("paid_observations") or 0),
                "metrics": row.get("metrics") or {},
            }
        return None

    rows: list[dict] = []
    for campaign in campaigns:
        decision = latest_decisions.get(campaign.id)
        if decision is None:
            continue
        post_observed = observed_after(campaign.id, decision.created_at)
        post_crm = [
            row for row in credited.get(campaign.id, [])
            if _is_after(row.get("event_at"), decision.created_at)
        ]
        terminal_after = (
            campaign.status in _TERMINAL_CAMPAIGN_STATUSES
            and _is_after(campaign.updated_at, decision.created_at)
        )
        commercial_row = commercial_by_campaign.get(campaign.id) or {}
        commercial_state = commercial_row.get("commercial_state") or "UNOBSERVED"

        basis = []
        if post_observed:
            basis.append("OBSERVED_MARKETING_SNAPSHOT")
        if post_crm:
            basis.append("ATTRIBUTED_CRM_UPDATE")
        if terminal_after:
            basis.append("CAMPAIGN_TERMINAL_STATE")

        if decision.action == "RETIRE" and campaign.status not in _TERMINAL_CAMPAIGN_STATUSES:
            review_state = "FOLLOW_THROUGH_REQUIRED"
            requires_attention = True
            next_action = {
                "code": "FOLLOW_THROUGH_RETIRE",
                "priority": "MEDIUM",
                "label": "Revisar ejecución de RETIRE",
                "view": "campaigns",
                "reason": "La decisión humana más reciente es RETIRE, pero la campaña continúa en un estado no terminal. La app no ejecuta esa decisión automáticamente.",
            }
        elif basis:
            review_state = "READY_FOR_REVIEW"
            requires_attention = True
            next_action = {
                "code": "REVIEW_DECISION",
                "priority": "MEDIUM",
                "label": "Revisar decisión con evidencia nueva",
                "view": "analytics",
                "reason": "Existe evidencia registrada después de la decisión; corresponde a una persona revisar si mantiene, cambia o reemplaza su criterio.",
            }
        else:
            review_state = "AWAITING_EVIDENCE"
            requires_attention = False
            next_action = {
                "code": "WAIT_FOR_EVIDENCE",
                "priority": "LOW",
                "label": "Esperar nueva evidencia",
                "view": "analytics",
                "reason": "No existe todavía evidencia posterior verificable para reabrir la decisión sin adivinar resultados.",
            }

        anchor_snapshot = None
        if decision.snapshot_id:
            try:
                anchor = runtime.learning.get_snapshot(company.id, decision.snapshot_id)
                anchor_snapshot = {
                    "id": anchor.id,
                    "created_at": anchor.created_at,
                    "date_preset": anchor.date_preset,
                }
            except KeyError:
                anchor_snapshot = None

        rows.append({
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "objective": campaign.objective,
                "updated_at": campaign.updated_at,
            },
            "decision": {
                "id": decision.id,
                "action": decision.action,
                "rationale": decision.rationale,
                "created_at": decision.created_at,
                "snapshot_id": decision.snapshot_id,
                "anchor_snapshot": anchor_snapshot,
            },
            "post_decision_evidence": {
                "basis": basis,
                "observed_marketing": post_observed,
                "attributed_crm_updates": post_crm[:20],
                "attributed_crm_update_count": len(post_crm),
                "campaign_terminal_after_decision": terminal_after,
            },
            "current_commercial": {
                "state": commercial_state,
                "funnel": commercial_row.get("funnel") or {},
                "value_by_currency": commercial_row.get("value_by_currency") or {},
            },
            "review": {
                "state": review_state,
                "requires_attention": requires_attention,
                "next_action": next_action,
                "causality_claimed": False,
                "success_or_failure_inferred": False,
            },
        })

    state_order = {"FOLLOW_THROUGH_REQUIRED": 0, "READY_FOR_REVIEW": 1, "AWAITING_EVIDENCE": 2}
    rows.sort(key=lambda row: (
        state_order.get(row["review"]["state"], 9),
        _parse_timestamp(row["decision"]["created_at"]),
        row["campaign"]["name"].casefold(),
        row["campaign"]["id"],
    ))
    ready = [row for row in rows if row["review"]["state"] == "READY_FOR_REVIEW"]
    follow_through = [row for row in rows if row["review"]["state"] == "FOLLOW_THROUGH_REQUIRED"]
    awaiting = [row for row in rows if row["review"]["state"] == "AWAITING_EVIDENCE"]
    return {
        "schema": "binario.marketing.decision-review.v1",
        "company": {"id": company.id, "name": company.name},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "campaigns_with_decision": len(rows),
            "ready_for_review": len(ready),
            "follow_through_required": len(follow_through),
            "awaiting_evidence": len(awaiting),
            "with_post_decision_observed_marketing": sum(
                1 for row in rows if row["post_decision_evidence"]["observed_marketing"]
            ),
            "with_post_decision_attributed_crm": sum(
                1 for row in rows if row["post_decision_evidence"]["attributed_crm_update_count"]
            ),
        },
        "attention": [
            {
                "campaign_id": row["campaign"]["id"],
                "campaign_name": row["campaign"]["name"],
                "decision_action": row["decision"]["action"],
                "review_state": row["review"]["state"],
                "next_action": row["review"]["next_action"],
            }
            for row in rows if row["review"]["requires_attention"]
        ][:12],
        "campaigns": rows,
        "model": {
            "decision_authority": "HUMAN_RECORDED",
            "post_decision_marketing_evidence": "OBSERVED_SNAPSHOT_AFTER_DECISION",
            "post_decision_crm_evidence": "LAST_CAPTURED_TOUCH_WITH_POST_DECISION_UPDATE",
            "causal_inference": False,
            "counterfactual_inference": False,
            "automatic_success_scoring": False,
            "forecasting": False,
        },
        "contracts": {
            "latest_campaign_decision_only": True,
            "creative_decisions_out_of_scope": True,
            "review_requires_post_decision_evidence": True,
            "retire_requires_explicit_human_follow_through": True,
            "decision_does_not_execute": True,
            "new_evidence_does_not_prove_causality": True,
            "currencies_remain_separate": True,
        },
        "safety": {
            "company_scoped": True,
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "business_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }


def enrich_action_center_with_decision_review(payload: dict, review: dict) -> dict:
    result = deepcopy(payload)
    queue = list(result.get("queue") or [])
    added_ready = 0
    added_follow_through = 0
    for row in review.get("campaigns") or []:
        state = row.get("review", {}).get("state")
        if state not in _REVIEW_RANK:
            continue
        rank, urgency = _REVIEW_RANK[state]
        campaign = row.get("campaign") or {}
        decision = row.get("decision") or {}
        action = row.get("review", {}).get("next_action") or {}
        evidence = row.get("post_decision_evidence") or {}
        basis = ", ".join(evidence.get("basis") or []) or "sin evidencia posterior"
        queue.append(action_base._item(
            rank=rank,
            urgency=urgency,
            source="CAMPAIGN",
            kind=f"decision_{state.lower()}",
            title=f"{action_base._text(action.get('label'), 'Revisar decisión')} · {action_base._text(campaign.get('name'), 'Campaña')}",
            detail=f"Decisión {action_base._text(decision.get('action'), 'registrada')} · {basis}",
            action_label=action_base._text(action.get("label"), "Revisar decisión"),
            view=action_base._text(action.get("view"), "analytics"),
            campaign_id=campaign.get("id"),
            blocking=False,
            reason_code=f"DECISION_{state}",
            reason="La decisión fue registrada por una persona. Esta prioridad solo señala seguimiento o evidencia posterior; no evalúa causalidad ni ejecuta cambios.",
        ))
        if state == "READY_FOR_REVIEW":
            added_ready += 1
        else:
            added_follow_through += 1

    deduped = {}
    for item in queue:
        current = deduped.get(item["id"])
        if current is None or (
            item["rank"], action_base._URGENCY_ORDER.get(item["urgency"], 9)
        ) < (
            current["rank"], action_base._URGENCY_ORDER.get(current["urgency"], 9)
        ):
            deduped[item["id"]] = item
    queue = list(deduped.values())
    queue.sort(key=lambda item: (
        item["rank"],
        action_base._URGENCY_ORDER.get(item["urgency"], 9),
        item.get("due_at") is None,
        item.get("due_at") or "",
        item["id"],
    ))
    queue = queue[:50]

    by_source = {key: 0 for key in ("OPERATIONS", "COMMERCIAL", "CAMPAIGN", "SETUP")}
    by_urgency = {key: 0 for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    for item in queue:
        by_source[item["source"]] = by_source.get(item["source"], 0) + 1
        by_urgency[item["urgency"]] = by_urgency.get(item["urgency"], 0) + 1

    summary = dict(result.get("summary") or {})
    summary.update({
        "queue_total": len(queue),
        "blocking": sum(1 for item in queue if item.get("blocking")),
        "critical": by_urgency["CRITICAL"],
        "high": by_urgency["HIGH"],
        "medium": by_urgency["MEDIUM"],
        "low": by_urgency["LOW"],
        "by_source": by_source,
        "decision_reviews_ready": added_ready,
        "decision_follow_through": added_follow_through,
    })
    result["summary"] = summary
    result["next_action"] = queue[0] if queue else None
    result["queue"] = queue
    result["focus"] = {
        "now": [item for item in queue if item["urgency"] in {"CRITICAL", "HIGH"}][:8],
        "next": [item for item in queue if item["urgency"] == "MEDIUM"][:8],
        "later": [item for item in queue if item["urgency"] == "LOW"][:8],
    }
    contracts = dict(result.get("contracts") or {})
    contracts.update({
        "decision_review_is_temporal_not_causal": True,
        "decision_review_never_executes_decisions": True,
        "decision_review_requires_human_judgment": True,
    })
    result["contracts"] = contracts
    return result


class AppRuntime(base.AppRuntime):
    """Post-W99 chain with deterministic human-decision review readiness."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def decision_review(self, company_id: str) -> dict:
        return decision_review_projection(self, company_id)

    def results_intelligence_workspace(self, company_id: str) -> dict:
        payload = super().results_intelligence_workspace(company_id)
        review = self.decision_review(company_id)
        by_campaign = {row["campaign"]["id"]: row for row in review["campaigns"]}
        for row in payload.get("campaigns") or []:
            campaign_id = (row.get("campaign") or {}).get("id")
            review_row = by_campaign.get(campaign_id)
            if review_row is None:
                continue
            row["decision_review"] = {
                "state": review_row["review"]["state"],
                "requires_attention": review_row["review"]["requires_attention"],
                "decision_action": review_row["decision"]["action"],
                "decision_created_at": review_row["decision"]["created_at"],
                "evidence_basis": review_row["post_decision_evidence"]["basis"],
                "next_action": review_row["review"]["next_action"],
                "causality_claimed": False,
            }
        payload["decision_review"] = {
            "schema": review["schema"],
            "summary": review["summary"],
            "model": review["model"],
            "contracts": review["contracts"],
        }
        return payload

    def marketing_command_center(self, company_id: str) -> dict:
        payload = super().marketing_command_center(company_id)
        review = self.decision_review(company_id)
        payload["decision_review"] = {
            "schema": review["schema"],
            "summary": review["summary"],
            "attention": review["attention"][:5],
            "model": review["model"],
        }
        return payload

    def action_center(self, company_id: str) -> dict:
        payload = super().action_center(company_id)
        return enrich_action_center_with_decision_review(
            payload,
            self.decision_review(company_id),
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path == "/commercial-outcomes.js":
            target = self.server.runtime.repo_root / "web" / "commercial-outcomes.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99DecisionReview(){
  if(document.querySelector('script[data-post-w99-decision-review]'))return;
  const script=document.createElement('script');
  script.src='/decision-review.js';
  script.defer=true;
  script.dataset.postW99DecisionReview='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/decision-review.js":
            target = self.server.runtime.repo_root / "web" / "decision-review.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/decision-review.js":
            self._static(parsed.path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "decision-review":
                self._json(self.server.runtime.decision_review(parts[2]))
                return
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
            return
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")
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
    print(f"BINARIO Marketing App · post-W99 decision review: {url}")
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = [
    "AppRuntime",
    "MarketingHandler",
    "MarketingHTTPServer",
    "create_server",
    "decision_review_projection",
    "enrich_action_center_with_decision_review",
    "serve",
]
