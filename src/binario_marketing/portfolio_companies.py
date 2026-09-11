from __future__ import annotations

from typing import Any, Iterable

SCHEMA = "binario.marketing.portfolio-companies.v1"
W50_STEP_ORDER = ("workspace", "meta", "facebook", "instagram", "ads", "campaign", "creative", "crm")
SETUP_STEP_IDS = {"meta", "facebook", "instagram", "ads"}


def _company_identity(company: Any) -> dict[str, str]:
    return {"id": str(company.id), "name": str(company.name)}


def _safe_steps(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    source = {str(row.get("id")): row for row in readiness.get("steps") or [] if isinstance(row, dict)}
    rows: list[dict[str, Any]] = []
    for step_id in W50_STEP_ORDER:
        row = source.get(step_id)
        if not row:
            continue
        rows.append({
            "id": step_id,
            "label": str(row.get("label") or step_id),
            "ready": bool(row.get("ready")),
            "view": str(row.get("view") or "companies"),
        })
    return rows


def _next_action(company_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    missing = next((row for row in steps if not row["ready"]), None)
    if missing is None:
        return {
            "code": "READY",
            "label": "Abrir empresa",
            "view": "companies",
            "company_id": company_id,
            "owner": "COMPANY_WORKSPACE",
        }
    if missing["id"] in SETUP_STEP_IDS:
        return {
            "code": f"SETUP_{missing['id'].upper()}",
            "label": "Abrir configuración",
            "view": "companies",
            "company_id": company_id,
            "step_id": missing["id"],
            "owner": "W50_SETUP_READINESS",
        }
    return {
        "code": f"COMPLETE_{missing['id'].upper()}",
        "label": f"Completar: {missing['label']}",
        "view": missing["view"],
        "company_id": company_id,
        "step_id": missing["id"],
        "owner": "W50_COMMAND_CENTER",
    }


def build_portfolio_companies(companies: Iterable[Any], command_centers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    errors = 0
    total_ready = 0
    total_steps = 0
    fully_ready = 0

    for company in companies:
        identity = _company_identity(company)
        center = command_centers.get(company.id) or {}
        if center.get("_local_state_error"):
            errors += 1
            items.append({
                "company": identity,
                "status": "LOCAL_STATE_ERROR",
                "readiness": {"ready": 0, "total": 0, "percent": 0, "steps": []},
                "next_action": {
                    "code": "OPEN_COMPANY",
                    "label": "Abrir empresa",
                    "view": "companies",
                    "company_id": company.id,
                    "owner": "COMPANY_WORKSPACE",
                },
            })
            continue

        readiness = center.get("readiness") or {}
        steps = _safe_steps(readiness)
        ready = sum(1 for row in steps if row["ready"])
        total = len(steps)
        percent = round(ready * 100 / total) if total else 0
        total_ready += ready
        total_steps += total
        if total and ready == total:
            fully_ready += 1
        items.append({
            "company": identity,
            "status": "READY" if total and ready == total else "NEEDS_SETUP",
            "readiness": {"ready": ready, "total": total, "percent": percent, "steps": steps},
            "next_action": _next_action(company.id, steps),
        })

    items.sort(key=lambda row: (row["status"] == "READY", row["readiness"]["percent"], row["company"]["name"].casefold()))
    company_count = len(items)
    average = round(sum(row["readiness"]["percent"] for row in items) / company_count) if company_count else 0
    return {
        "schema": SCHEMA,
        "summary": {
            "companies": company_count,
            "fully_ready": fully_ready,
            "needs_setup": max(0, company_count - fully_ready - errors),
            "local_state_errors": errors,
            "readiness_ready": total_ready,
            "readiness_total": total_steps,
            "average_percent": average,
        },
        "items": items,
        "contracts": {
            "w50_command_center_is_readiness_authority": True,
            "owner_module_retains_setup_mutation_authority": True,
            "no_duplicate_readiness_engine": True,
            "explicit_company_handoff_for_provider_setup": True,
        },
        "safety": {
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "company_mutation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }
