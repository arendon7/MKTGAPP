from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .learning_store import DATE_PRESETS, LearningStore
from . import service_wave51_app as base


_SOCIAL_METRICS = ("reach", "views", "likes", "comments", "shares", "saved", "total_interactions")
_PAID_TOTAL_METRICS = ("impressions", "reach", "clicks", "spend")


def _number(value) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return int(number) if number.is_integer() else number


def _metric_subset(payload: dict, keys: tuple[str, ...]) -> dict:
    result = {}
    for key in keys:
        value = _number((payload or {}).get(key))
        if value is not None:
            result[key] = value
    return result


def _add_metrics(target: dict, source: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        value = _number(source.get(key))
        if value is not None:
            target[key] = target.get(key, 0) + value


def _derived(metrics: dict) -> dict:
    impressions = float(_number(metrics.get("impressions")) or 0)
    paid_reach = float(_number(metrics.get("paid_reach")) or 0)
    clicks = float(_number(metrics.get("clicks")) or 0)
    spend = float(_number(metrics.get("spend")) or 0)
    organic_reach = float(_number(metrics.get("organic_reach")) or 0)
    interactions = float(_number(metrics.get("total_interactions")) or 0)
    result = dict(metrics)
    result["paid_ctr"] = round(clicks * 100 / impressions, 4) if impressions else None
    result["paid_cpc"] = round(spend / clicks, 6) if clicks and "spend" in metrics else None
    result["paid_cpm"] = round(spend * 1000 / impressions, 6) if impressions and "spend" in metrics else None
    result["paid_frequency"] = round(impressions / paid_reach, 4) if paid_reach else None
    result["organic_interaction_rate"] = round(interactions * 100 / organic_reach, 4) if organic_reach else None
    return result


class AppRuntime(base.AppRuntime):
    """Wave 52 turns explicit provider readback into durable, attributable-by-link evidence."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.learning = LearningStore(runtime.data_root / "State" / "learning")
        return runtime

    def _learning_links(self, company_id: str) -> tuple[dict, dict, dict]:
        publication_links: dict[str, dict] = {}
        paid_links: dict[str, dict] = {}
        creative_meta: dict[str, dict] = {}
        for item in self.company_creatives_payload(company_id):
            media = item.get("media") or {}
            profile = item.get("creative") or {}
            media_id = media.get("id")
            if not media_id or not profile:
                continue
            meta = {
                "media_id": media_id,
                "title": profile.get("title") or media.get("original_name") or media_id,
                "kind": media.get("kind"),
                "campaign_id": profile.get("campaign_id"),
                "purpose": profile.get("purpose"),
                "stage": item.get("effective_stage"),
            }
            creative_meta[media_id] = meta
            for publication_id in profile.get("publication_ids") or []:
                publication_links[publication_id] = meta
            for draft_id in profile.get("paid_media_ids") or []:
                paid_links[draft_id] = meta
        return publication_links, paid_links, creative_meta

    def _crm_learning_evidence(self, company_id: str) -> dict:
        opportunities = self.crm.list_opportunities(company_id)
        by_currency: dict[str, dict] = {}
        for row in opportunities:
            bucket = by_currency.setdefault(row.currency, {
                "open_count": 0, "won_count": 0, "lost_count": 0,
                "open_value": 0, "won_value": 0, "lost_value": 0,
            })
            value = int(row.value or 0)
            if row.stage == "WON":
                bucket["won_count"] += 1; bucket["won_value"] += value
            elif row.stage == "LOST":
                bucket["lost_count"] += 1; bucket["lost_value"] += value
            else:
                bucket["open_count"] += 1; bucket["open_value"] += value
        raw = self.crm.summary(company_id)
        summary = {
            "contacts": raw.get("contacts", 0),
            "opportunities_open": raw.get("opportunities_open", 0),
            "opportunities_won": raw.get("opportunities_won", 0),
            "pending_activities": raw.get("pending_activities", 0),
            "overdue_activities": raw.get("overdue_activities", 0),
            "stage_counts": raw.get("stage_counts") or {},
        }
        return {
            "summary": summary,
            "value_by_currency": by_currency,
            "attributed_to_campaign": False,
            "attribution_reason": "CRM opportunities do not yet carry a certified campaign/source attribution key.",
        }

    def refresh_learning(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("learning refresh payload must be an object")
        allowed = {"date_preset", "social_limit", "paid_limit"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported learning refresh fields: {', '.join(sorted(unknown))}")
        company = self.companies.get(company_id)
        preset = str(payload.get("date_preset") or "last_7d").strip().lower()
        if preset not in DATE_PRESETS:
            raise ValueError("unsupported learning date preset")
        social_limit = int(payload.get("social_limit") or 20)
        paid_limit = int(payload.get("paid_limit") or 20)
        if not 1 <= social_limit <= 20 or not 1 <= paid_limit <= 20:
            raise ValueError("learning refresh limits must be between 1 and 20")

        publication_links, paid_links, _creative_meta = self._learning_links(company.id)
        social_remote = self.social_analytics_meta(company.id, limit=social_limit)
        social_observations = []
        for row in social_remote.get("observations") or []:
            link = publication_links.get(row.get("id")) or {}
            social_observations.append({
                "publication_id": row.get("id"),
                "channel": row.get("channel"),
                "kind": row.get("kind"),
                "remote_state": row.get("remote_state"),
                "creative_media_id": link.get("media_id"),
                "campaign_id": link.get("campaign_id"),
                "metrics": _metric_subset(row.get("metrics") or {}, _SOCIAL_METRICS),
                "available": bool(row.get("available")),
                "provider_error": bool(row.get("provider_error")),
            })
        social_evidence = {
            "configured": bool(social_remote.get("configured")),
            "coverage": social_remote.get("coverage") or {},
            "totals": _metric_subset(social_remote.get("totals") or {}, _SOCIAL_METRICS),
            "observations": social_observations,
        }

        all_paid_rows = [row for row in self.company_paid_media(company.id) if row.get("campaign_id") or row.get("ad_id")]
        paid_rows = list(reversed(all_paid_rows))[:paid_limit]
        paid_observations = []
        paid_errors = 0
        paid_measured = 0
        for row in paid_rows:
            link = paid_links.get(row.get("id")) or {}
            internal_campaign = (row.get("marketing_campaign") or {}).get("id") or link.get("campaign_id")
            try:
                observed = self.company_paid_media_observability(company.id, row["id"], date_preset=preset)
                insights = observed.get("insights") if isinstance(observed.get("insights"), dict) else {}
                metrics = _metric_subset(insights, _PAID_TOTAL_METRICS)
                if metrics:
                    paid_measured += 1
                safety = observed.get("safety") or {}
                paid_observations.append({
                    "draft_id": row.get("id"),
                    "status": row.get("status"),
                    "creative_media_id": link.get("media_id") or (row.get("creative_source") or {}).get("id"),
                    "campaign_id": internal_campaign,
                    "currency": (row.get("plan") or {}).get("currency"),
                    "metrics": metrics,
                    "configured_paused": safety.get("configured_paused"),
                    "explicit_active_detected": bool(safety.get("explicit_active_detected")),
                    "provider_error": False,
                })
            except Exception as exc:
                paid_errors += 1
                paid_observations.append({
                    "draft_id": row.get("id"),
                    "status": row.get("status"),
                    "creative_media_id": link.get("media_id") or (row.get("creative_source") or {}).get("id"),
                    "campaign_id": internal_campaign,
                    "currency": (row.get("plan") or {}).get("currency"),
                    "metrics": {},
                    "configured_paused": None,
                    "explicit_active_detected": False,
                    "provider_error": type(exc).__name__,
                })

        paid_totals: dict[str, float | int] = {}
        paid_totals_by_currency: dict[str, dict] = {}
        currencies = sorted({row.get("currency") for row in paid_observations if row.get("currency")})
        for row in paid_observations:
            metrics = row.get("metrics") or {}
            _add_metrics(paid_totals, metrics, _PAID_TOTAL_METRICS)
            currency = row.get("currency") or "UNKNOWN"
            bucket = paid_totals_by_currency.setdefault(currency, {})
            _add_metrics(bucket, metrics, _PAID_TOTAL_METRICS)
        spend_aggregated = len(currencies) <= 1
        if not spend_aggregated:
            paid_totals.pop("spend", None)
        paid_evidence = {
            "coverage": {
                "eligible": len(all_paid_rows),
                "requested": len(paid_rows),
                "measured": paid_measured,
                "errors": paid_errors,
            },
            "currencies": currencies,
            "spend_aggregated": spend_aggregated,
            "totals": paid_totals,
            "totals_by_currency": paid_totals_by_currency,
            "observations": paid_observations,
        }
        crm_evidence = self._crm_learning_evidence(company.id)
        coverage = {
            "social": social_evidence["coverage"],
            "paid_media": paid_evidence["coverage"],
            "crm_campaign_attribution": False,
        }
        snapshot = self.learning.create_snapshot(company.id, {
            "date_preset": preset,
            "social": social_evidence,
            "paid_media": paid_evidence,
            "crm": crm_evidence,
            "coverage": coverage,
        })
        self.workspace.registries.timeline.append("learning.snapshot.created", {
            "company_id": company.id,
            "snapshot_id": snapshot.id,
            "date_preset": preset,
            "social_requested": (social_evidence.get("coverage") or {}).get("requested", 0),
            "paid_requested": paid_evidence["coverage"]["requested"],
            "provider_mutation_performed": False,
        })
        result = self.learning_payload(company.id)
        result["safety"]["provider_refresh_performed"] = True
        return result

    @staticmethod
    def _entity_metrics() -> dict:
        return {
            "organic_reach": 0,
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "saved": 0,
            "total_interactions": 0,
            "impressions": 0,
            "paid_reach": 0,
            "clicks": 0,
            "spend": 0,
        }

    def _learning_rollups(self, company_id: str, snapshot) -> dict:
        _pub_links, _paid_links, creative_meta = self._learning_links(company_id)
        campaigns = {row.id: {
            "id": row.id,
            "name": row.name,
            "objective": row.objective,
            "status": row.status,
            "creative_count": len(row.media_ids),
            "metrics": self._entity_metrics(),
            "organic_observations": 0,
            "paid_observations": 0,
        } for row in self.campaigns.list(company_id)}
        creatives = {media_id: {
            **meta,
            "metrics": self._entity_metrics(),
            "organic_observations": 0,
            "paid_observations": 0,
        } for media_id, meta in creative_meta.items()}

        for row in snapshot.social.get("observations") or []:
            metrics = row.get("metrics") or {}
            mapped = {
                "organic_reach": metrics.get("reach"),
                "views": metrics.get("views"),
                "likes": metrics.get("likes"),
                "comments": metrics.get("comments"),
                "shares": metrics.get("shares"),
                "saved": metrics.get("saved"),
                "total_interactions": metrics.get("total_interactions"),
            }
            media_id, campaign_id = row.get("creative_media_id"), row.get("campaign_id")
            if media_id in creatives:
                _add_metrics(creatives[media_id]["metrics"], mapped, tuple(mapped))
                if metrics: creatives[media_id]["organic_observations"] += 1
            if campaign_id in campaigns:
                _add_metrics(campaigns[campaign_id]["metrics"], mapped, tuple(mapped))
                if metrics: campaigns[campaign_id]["organic_observations"] += 1

        for row in snapshot.paid_media.get("observations") or []:
            metrics = row.get("metrics") or {}
            mapped = {
                "impressions": metrics.get("impressions"),
                "paid_reach": metrics.get("reach"),
                "clicks": metrics.get("clicks"),
                "spend": metrics.get("spend"),
            }
            media_id, campaign_id = row.get("creative_media_id"), row.get("campaign_id")
            if media_id in creatives:
                _add_metrics(creatives[media_id]["metrics"], mapped, tuple(mapped))
                if metrics: creatives[media_id]["paid_observations"] += 1
            if campaign_id in campaigns:
                _add_metrics(campaigns[campaign_id]["metrics"], mapped, tuple(mapped))
                if metrics: campaigns[campaign_id]["paid_observations"] += 1

        if snapshot.paid_media.get("spend_aggregated") is False:
            for item in campaigns.values():
                item["metrics"].pop("spend", None)
            for item in creatives.values():
                item["metrics"].pop("spend", None)

        decisions = self.learning.list_decisions(company_id, limit=100)
        latest_decision = {}
        for row in decisions:
            key = (row.entity_kind, row.entity_id)
            if key not in latest_decision:
                latest_decision[key] = asdict(row)
        for item in campaigns.values():
            item["metrics"] = _derived(item["metrics"])
            item["evidence"] = "OBSERVED" if item["organic_observations"] or item["paid_observations"] else "INSUFFICIENT"
            item["latest_decision"] = latest_decision.get(("CAMPAIGN", item["id"]))
        for item in creatives.values():
            item["metrics"] = _derived(item["metrics"])
            item["evidence"] = "OBSERVED" if item["organic_observations"] or item["paid_observations"] else "INSUFFICIENT"
            item["latest_decision"] = latest_decision.get(("CREATIVE", item["media_id"]))

        campaign_rows = list(campaigns.values())
        creative_rows = list(creatives.values())
        paid_candidates = [row for row in creative_rows if row["metrics"].get("paid_ctr") is not None]
        organic_candidates = [row for row in creative_rows if row["metrics"].get("organic_interaction_rate") is not None]
        leaders = {
            "paid_ctr": max(paid_candidates, key=lambda row: row["metrics"]["paid_ctr"], default=None),
            "organic_interaction_rate": max(organic_candidates, key=lambda row: row["metrics"]["organic_interaction_rate"], default=None),
        }
        if leaders["paid_ctr"]:
            leaders["paid_ctr"] = {"media_id": leaders["paid_ctr"]["media_id"], "title": leaders["paid_ctr"]["title"], "value": leaders["paid_ctr"]["metrics"]["paid_ctr"]}
        if leaders["organic_interaction_rate"]:
            leaders["organic_interaction_rate"] = {"media_id": leaders["organic_interaction_rate"]["media_id"], "title": leaders["organic_interaction_rate"]["title"], "value": leaders["organic_interaction_rate"]["metrics"]["organic_interaction_rate"]}
        return {"campaigns": campaign_rows, "creatives": creative_rows, "leaders": leaders}

    def learning_payload(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        snapshots = self.learning.list_snapshots(company.id, limit=12)
        latest = snapshots[0] if snapshots else None
        rollups = self._learning_rollups(company.id, latest) if latest else {"campaigns": [], "creatives": [], "leaders": {"paid_ctr": None, "organic_interaction_rate": None}}
        decisions = [asdict(row) for row in self.learning.list_decisions(company.id, limit=30)]
        return {
            "schema": "binario.marketing.learning-loop.v1",
            "company_id": company.id,
            "latest_snapshot": asdict(latest) if latest else None,
            "history": [{"id": row.id, "date_preset": row.date_preset, "created_at": row.created_at, "coverage": row.coverage} for row in snapshots],
            "campaigns": rollups["campaigns"],
            "creatives": rollups["creatives"],
            "leaders": rollups["leaders"],
            "decisions": decisions,
            "crm_current": self._crm_learning_evidence(company.id),
            "attribution": {
                "creative_to_publication": True,
                "creative_to_paid_media": True,
                "campaign_to_creative": True,
                "crm_to_campaign": False,
                "note": "CRM is shown as a company outcome signal, not as campaign-attributed conversion or revenue.",
            },
            "safety": {
                "provider_refresh_performed": False,
                "provider_mutation_performed": False,
                "decision_execution_performed": False,
            },
        }

    def record_learning_decision(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        kind = str((payload or {}).get("entity_kind") or "").strip().upper()
        entity_id = str((payload or {}).get("entity_id") or "").strip()
        if kind == "CAMPAIGN":
            self.campaigns.get_for_company(company.id, entity_id)
        elif kind == "CREATIVE":
            media = self.company_media.get_for_company(company.id, entity_id)
            if self.creatives.get(company.id, media.id) is None:
                raise ValueError("creative decision requires a saved Creative Studio brief")
        row = self.learning.create_decision(company.id, payload)
        self.workspace.registries.timeline.append("learning.decision.recorded", {
            "company_id": company.id,
            "decision_id": row.id,
            "entity_kind": row.entity_kind,
            "entity_id": row.entity_id,
            "action": row.action,
            "snapshot_id": row.snapshot_id,
            "provider_mutation_performed": False,
        })
        return asdict(row)

    def _ai_context(self, company_id: str, *, task: str, campaign_id: str | None, creative_media_id: str | None) -> dict:
        context = super()._ai_context(company_id, task=task, campaign_id=campaign_id, creative_media_id=creative_media_id)
        learning = self.learning_payload(company_id)
        latest = learning.get("latest_snapshot") or {}
        crm_source = latest.get("crm") or learning.get("crm_current") or {}
        context["learning"] = {
            "snapshot_id": latest.get("id"),
            "captured_at": latest.get("created_at"),
            "date_preset": latest.get("date_preset"),
            "coverage": latest.get("coverage") or {},
            "attribution": learning.get("attribution") or {},
            "campaigns": [{
                "id": row.get("id"), "name": row.get("name"), "objective": row.get("objective"),
                "evidence": row.get("evidence"), "metrics": row.get("metrics"),
                "latest_decision": (row.get("latest_decision") or {}).get("action"),
            } for row in learning.get("campaigns") or []][:12],
            "creatives": [{
                "media_id": row.get("media_id"), "title": row.get("title"), "purpose": row.get("purpose"),
                "campaign_id": row.get("campaign_id"), "evidence": row.get("evidence"), "metrics": row.get("metrics"),
                "latest_decision": (row.get("latest_decision") or {}).get("action"),
            } for row in learning.get("creatives") or []][:20],
            "leaders": learning.get("leaders") or {},
            "crm_company_outcome": {
                "summary": crm_source.get("summary") or {},
                "value_by_currency": crm_source.get("value_by_currency") or {},
                "attributed_to_campaign": False,
            },
        }
        return context


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/learning-loop.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "learning":
                self._json(self.server.runtime.learning_payload(parts[2]))
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["learning", "refresh"]:
                # Explicit readback only. This path performs provider reads and persists sanitized evidence.
                result = self.server.runtime.refresh_learning(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["learning", "decisions"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.record_learning_decision(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_POST()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App: {url}")
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
