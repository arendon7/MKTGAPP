from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_decision_review_app as base
from . import service_post_w99_action_center_app as action_base


_URGENCY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_CURRENCY_FIELDS = (
    "open_count", "won_count", "lost_count",
    "open_value", "won_value", "lost_value",
)


def _currency_totals(target: dict, source: dict) -> None:
    """Aggregate exact same-currency commercial totals without FX conversion."""
    for currency, values in (source or {}).items():
        code = str(currency or "").strip().upper()
        if not code or not isinstance(values, dict):
            continue
        bucket = target.setdefault(code, {field: 0 for field in _CURRENCY_FIELDS})
        for field in _CURRENCY_FIELDS:
            value = values.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            bucket[field] += value


def _portfolio_item(company: dict, item: dict) -> dict:
    row = deepcopy(item)
    row["portfolio_id"] = f"{company['id']}:{item.get('id') or 'action'}"
    row["company"] = {"id": company["id"], "name": company["name"]}
    return row


def _queue_key(item: dict) -> tuple:
    return (
        int(item.get("rank") if isinstance(item.get("rank"), int) else 999),
        _URGENCY_ORDER.get(str(item.get("urgency") or "").upper(), 9),
        0 if item.get("blocking") else 1,
        str((item.get("company") or {}).get("name") or "").casefold(),
        str(item.get("portfolio_id") or item.get("id") or ""),
    )


def portfolio_control_tower_projection(runtime) -> dict:
    """Compose a deterministic cross-company read model from existing projections.

    Action Center remains the authority for per-company ordering. The portfolio layer
    only adds company identity, exact same-currency commercial context and one global
    queue. It never invents a health score, forecast, causal claim or FX conversion.
    """
    companies = list(runtime.companies.list())
    company_rows: list[dict] = []
    global_queue: list[dict] = []
    portfolio_values: dict[str, dict] = {}

    totals = {
        "queue_total": 0,
        "blocking": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "captured_leads": 0,
        "converted_leads": 0,
        "attributed_opportunities": 0,
        "attributed_won": 0,
        "decision_reviews_ready": 0,
        "decision_follow_through": 0,
    }

    for company in companies:
        identity = {"id": company.id, "name": company.name}
        action = runtime.action_center(company.id)
        commercial = runtime.commercial_outcomes(company.id)
        action_summary = action.get("summary") or {}
        commercial_summary = commercial.get("summary") or {}

        queue = [_portfolio_item(identity, item) for item in (action.get("queue") or [])]
        global_queue.extend(queue)
        next_action = queue[0] if queue else None

        for key in ("queue_total", "blocking", "critical", "high", "medium", "low",
                    "decision_reviews_ready", "decision_follow_through"):
            totals[key] += int(action_summary.get(key) or 0)
        for key in ("captured_leads", "converted_leads", "attributed_opportunities", "attributed_won"):
            totals[key] += int(commercial_summary.get(key) or 0)
        _currency_totals(portfolio_values, commercial_summary.get("value_by_currency") or {})

        if int(action_summary.get("blocking") or 0):
            attention_state = "BLOCKING"
        elif int(action_summary.get("critical") or 0):
            attention_state = "CRITICAL"
        elif int(action_summary.get("high") or 0):
            attention_state = "HIGH"
        elif int(action_summary.get("medium") or 0):
            attention_state = "MEDIUM"
        elif int(action_summary.get("low") or 0):
            attention_state = "LOW"
        else:
            attention_state = "CLEAR"

        company_rows.append({
            "company": identity,
            "attention": {
                "state": attention_state,
                "next_action": next_action,
                "queue_total": int(action_summary.get("queue_total") or 0),
                "blocking": int(action_summary.get("blocking") or 0),
                "critical": int(action_summary.get("critical") or 0),
                "high": int(action_summary.get("high") or 0),
                "medium": int(action_summary.get("medium") or 0),
                "low": int(action_summary.get("low") or 0),
                "by_source": deepcopy(action_summary.get("by_source") or {}),
                "decision_reviews_ready": int(action_summary.get("decision_reviews_ready") or 0),
                "decision_follow_through": int(action_summary.get("decision_follow_through") or 0),
            },
            "commercial": {
                "captured_leads": int(commercial_summary.get("captured_leads") or 0),
                "converted_leads": int(commercial_summary.get("converted_leads") or 0),
                "converted_without_opportunity": int(commercial_summary.get("converted_without_opportunity") or 0),
                "attributed_opportunities": int(commercial_summary.get("attributed_opportunities") or 0),
                "attributed_won": int(commercial_summary.get("attributed_won") or 0),
                "value_by_currency": deepcopy(commercial_summary.get("value_by_currency") or {}),
            },
        })

    global_queue.sort(key=_queue_key)
    for row in company_rows:
        next_action = row["attention"]["next_action"]
        row["_sort"] = _queue_key(next_action) if next_action else (
            999, 9, 1, row["company"]["name"].casefold(), row["company"]["id"]
        )
    company_rows.sort(key=lambda row: row["_sort"])
    for row in company_rows:
        row.pop("_sort", None)

    return {
        "schema": "binario.marketing.portfolio-control-tower.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_companies": len(company_rows),
            "companies_with_attention": sum(1 for row in company_rows if row["attention"]["queue_total"]),
            "companies_blocking": sum(1 for row in company_rows if row["attention"]["blocking"]),
            "companies_critical": sum(1 for row in company_rows if row["attention"]["critical"]),
            **totals,
            "value_by_currency": portfolio_values,
        },
        "next_action": global_queue[0] if global_queue else None,
        "focus": {
            "now": [row for row in global_queue if row.get("urgency") in {"CRITICAL", "HIGH"}][:12],
            "next": [row for row in global_queue if row.get("urgency") == "MEDIUM"][:12],
            "later": [row for row in global_queue if row.get("urgency") == "LOW"][:12],
        },
        "companies": company_rows,
        "queue": global_queue[:100],
        "contracts": {
            "active_companies_only": True,
            "action_center_is_priority_authority": True,
            "cross_company_order_is_deterministic": True,
            "no_opaque_health_score": True,
            "no_value_weighted_priority": True,
            "currencies_remain_separate": True,
            "no_fx_conversion": True,
            "human_execution_required": True,
        },
        "safety": {
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "business_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
            "forecasting": False,
            "causal_inference": False,
        },
    }


class AppRuntime(base.AppRuntime):
    """Post-W99 chain with deterministic cross-company operator visibility."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def portfolio_control_tower(self) -> dict:
        return portfolio_control_tower_projection(self)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path == "/decision-review.js":
            target = self.server.runtime.repo_root / "web" / "decision-review.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PortfolioControlTower(){
  if(document.querySelector('script[data-post-w99-portfolio-control-tower]'))return;
  const script=document.createElement('script');
  script.src='/portfolio-control-tower.js';
  script.defer=true;
  script.dataset.postW99PortfolioControlTower='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/portfolio-control-tower.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-control-tower.js"
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
        if parsed.path == "/portfolio-control-tower.js":
            self._static(parsed.path)
            return
        try:
            if parsed.path == "/api/portfolio-control-tower":
                self._json(self.server.runtime.portfolio_control_tower())
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
    print(f"BINARIO Marketing App · post-W99 portfolio control tower: {url}")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = [
    "AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve",
    "portfolio_control_tower_projection",
]
