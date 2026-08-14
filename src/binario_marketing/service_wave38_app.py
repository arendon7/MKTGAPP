from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import service_wave37_app as ui_base
from .meta_credentials import MetaCredentialError, MetaCredentialStore
from .meta_graph import MetaGraphError
from .meta_observability import MetaObservability
from .service_wave37 import AppRuntime as Wave37Runtime


_ANALYTIC_METRICS = (
    "reach",
    "views",
    "likes",
    "comments",
    "shares",
    "saved",
    "total_interactions",
)
_STATUS_ORDER = ("DRAFT", "QUEUED", "PUBLISHING", "PUBLISHED", "FAILED", "CANCELLED")
_CHANNEL_ORDER = ("facebook_page", "instagram")


def _number(value) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value if value >= 0 else None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _metric_totals() -> dict[str, float | int]:
    return {metric: 0 for metric in _ANALYTIC_METRICS}


def _publication_payload(row, company_name: str) -> dict:
    return {
        "id": row.id,
        "company_id": row.project_id,
        "company_name": company_name,
        "channel": row.channel,
        "kind": row.kind,
        "message": row.message,
        "status": row.status,
        "scheduled_for": row.scheduled_for,
        "remote_id": row.remote_id,
        "attempts": row.attempts,
        "error": row.error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class AppRuntime(Wave37Runtime):
    """Wave 38 adds user-facing read-only social analytics per company."""

    def _analytics_companies(self, company_id: str | None):
        if company_id:
            return [self.companies.get(company_id)]
        return self.companies.list()

    def social_analytics(self, company_id: str | None = None) -> dict:
        companies = self._analytics_companies(company_id)
        aggregate_status = {status: 0 for status in _STATUS_ORDER}
        aggregate_channels = {channel: 0 for channel in _CHANNEL_ORDER}
        aggregate_kinds: dict[str, int] = {}
        recent: list[dict] = []
        by_company: list[dict] = []

        for company in companies:
            rows = self.social.list(company.id)
            statuses = {status: 0 for status in _STATUS_ORDER}
            channels = {channel: 0 for channel in _CHANNEL_ORDER}
            kinds: dict[str, int] = {}
            for row in rows:
                statuses[row.status] = statuses.get(row.status, 0) + 1
                channels[row.channel] = channels.get(row.channel, 0) + 1
                kinds[row.kind] = kinds.get(row.kind, 0) + 1
                aggregate_status[row.status] = aggregate_status.get(row.status, 0) + 1
                aggregate_channels[row.channel] = aggregate_channels.get(row.channel, 0) + 1
                aggregate_kinds[row.kind] = aggregate_kinds.get(row.kind, 0) + 1
                recent.append(_publication_payload(row, company.name))
            by_company.append({
                "company_id": company.id,
                "company_name": company.name,
                "accounts": {
                    "facebook": bool(company.facebook_page_id),
                    "instagram": bool(company.instagram_id),
                },
                "total": len(rows),
                "statuses": statuses,
                "channels": channels,
                "kinds": kinds,
            })

        recent.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("id") or "")), reverse=True)
        credential = MetaCredentialStore().status()
        published_remote = sum(
            1 for row in recent
            if row["status"] == "PUBLISHED" and row.get("remote_id")
        )
        return {
            "schema": "binario.marketing.social-analytics.v1",
            "company_id": company_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "meta": {
                "configured": bool(credential.configured),
                "source": credential.source,
                "remote_refresh_available": bool(company_id and credential.configured and published_remote),
            },
            "summary": {
                "companies": len(companies),
                "total": sum(aggregate_status.values()),
                "draft": aggregate_status.get("DRAFT", 0),
                "queued": aggregate_status.get("QUEUED", 0),
                "publishing": aggregate_status.get("PUBLISHING", 0),
                "published": aggregate_status.get("PUBLISHED", 0),
                "failed": aggregate_status.get("FAILED", 0),
                "cancelled": aggregate_status.get("CANCELLED", 0),
                "published_with_remote_id": published_remote,
            },
            "statuses": aggregate_status,
            "channels": aggregate_channels,
            "kinds": aggregate_kinds,
            "by_company": by_company,
            "recent": recent[:30],
        }

    def social_analytics_meta(self, company_id: str, *, limit: int = 12) -> dict:
        company = self.companies.get(company_id)
        if limit < 1 or limit > 20:
            raise ValueError("analytics Meta limit must be between 1 and 20")
        credential = MetaCredentialStore().status()
        if not credential.configured:
            return {
                "schema": "binario.marketing.social-analytics-meta.v1",
                "company_id": company.id,
                "company_name": company.name,
                "configured": False,
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
                "coverage": {"eligible": 0, "requested": 0, "observed": 0, "measured": 0, "errors": 0},
                "totals": _metric_totals(),
                "top_content": [],
                "observations": [],
                "reason": "Meta is not connected",
            }

        eligible = [
            row for row in self.social.list(company.id)
            if row.status == "PUBLISHED" and row.remote_id and row.channel in _CHANNEL_ORDER
        ]
        eligible.sort(key=lambda row: (row.updated_at, row.id), reverse=True)
        selected = eligible[:limit]
        observer = MetaObservability.from_env()
        totals = _metric_totals()
        observations: list[dict] = []

        for row in selected:
            base = _publication_payload(row, company.name)
            try:
                observed = observer.publication(row)
                insights = observed.get("insights") if isinstance(observed.get("insights"), dict) else {}
                clean_metrics: dict[str, float | int] = {}
                for metric in _ANALYTIC_METRICS:
                    value = _number(insights.get(metric))
                    if value is not None:
                        clean_metrics[metric] = value
                        totals[metric] += value
                remote = observed.get("remote") if isinstance(observed.get("remote"), dict) else {}
                permalink = remote.get("permalink") or remote.get("permalink_url")
                observations.append({
                    **base,
                    "available": bool(observed.get("available")),
                    "remote_state": observed.get("remote_state"),
                    "metrics": clean_metrics,
                    "metric_errors": sorted((observed.get("metric_errors") or {}).keys()),
                    "permalink": str(permalink) if permalink else None,
                    "media_type": remote.get("media_type") or remote.get("media_product_type"),
                    "provider_error": None,
                })
            except (MetaGraphError, MetaCredentialError) as exc:
                observations.append({
                    **base,
                    "available": False,
                    "remote_state": "ERROR",
                    "metrics": {},
                    "metric_errors": [],
                    "permalink": None,
                    "media_type": None,
                    "provider_error": str(exc)[:500],
                })

        measured = [row for row in observations if row.get("metrics")]
        observed_count = sum(1 for row in observations if row.get("available"))
        errors = sum(1 for row in observations if row.get("provider_error"))

        def score(row: dict) -> tuple[float, float, float, str]:
            metrics = row.get("metrics") or {}
            interactions = _number(metrics.get("total_interactions"))
            if interactions is None:
                interactions = sum(_number(metrics.get(key)) or 0 for key in ("likes", "comments", "shares", "saved"))
            return (
                float(interactions or 0),
                float(_number(metrics.get("views")) or 0),
                float(_number(metrics.get("reach")) or 0),
                str(row.get("updated_at") or ""),
            )

        top_content = sorted(measured, key=score, reverse=True)[:5]
        return {
            "schema": "binario.marketing.social-analytics-meta.v1",
            "company_id": company.id,
            "company_name": company.name,
            "configured": True,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "coverage": {
                "eligible": len(eligible),
                "requested": len(selected),
                "observed": observed_count,
                "measured": len(measured),
                "errors": errors,
            },
            "totals": totals,
            "top_content": top_content,
            "observations": observations,
            "notes": {
                "instagram": "Metrics are read from the existing certified Instagram media insights path.",
                "facebook": "Current Facebook readback confirms remote presence/status; this wave does not invent unsupported organic metrics.",
            },
        }


MarketingHTTPServer = ui_base.MarketingHTTPServer


class MarketingHandler(ui_base.MarketingHandler):
    """Wave 38 analytics routes are GET/read-only and provider refresh is user-triggered."""

    def _wave38_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, MetaGraphError):
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        elif isinstance(exc, MetaCredentialError):
            self._error(HTTPStatus.CONFLICT, str(exc))
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/audiences.js":
            self._static("/audiences-wave38-loader.js")
            return
        if path == "/audiences-wave37.js":
            self._static("/audiences-wave37-loader.js")
            return
        if path == "/analytics.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "analytics", "social"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.social_analytics(company_id))
                return
            if parts == ["api", "analytics", "social", "meta"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = str((query.get("company_id") or [""])[0]).strip()
                if not company_id:
                    raise ValueError("company_id is required for Meta analytics refresh")
                raw_limit = str((query.get("limit") or ["12"])[0]).strip()
                try:
                    limit = int(raw_limit)
                except ValueError as exc:
                    raise ValueError("analytics Meta limit must be an integer") from exc
                self._json(self.server.runtime.social_analytics_meta(company_id, limit=limit))
                return
        except Exception as exc:
            self._wave38_error(exc)
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
