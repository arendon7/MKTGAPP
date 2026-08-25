from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from binario_marketing.service_post_w99_operator_work_plan_app import compose_operator_work_plan


ROOT = Path(__file__).resolve().parents[1]


def _action(identifier: str, urgency: str, *, blocking: bool = False, due_at: str | None = None) -> dict:
    return {
        "id": identifier,
        "rank": {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}[urgency],
        "urgency": urgency,
        "source": "OPERATIONS",
        "kind": "test",
        "title": f"Action {identifier}",
        "detail": f"Detail {identifier}",
        "blocking": blocking,
        "due_at": due_at,
        "reason": {"code": f"R_{identifier}", "explanation": "Canonical Action Center reason"},
        "action": {
            "label": "Open owner",
            "view": "today",
            "tab": "work",
            "entity_id": identifier,
            "lead_id": None,
            "contact_id": None,
            "opportunity_id": None,
            "campaign_id": None,
            "media_id": None,
        },
    }


def _cockpit(state: str = "BLOCKED") -> dict:
    return {
        "status": {"state": state, "headline": "Executive context only"},
        "lanes": [
            {"key": "operations", "label": "Operations", "state": state, "headline": "Context"},
            {"key": "commercial", "label": "Commercial", "state": "STABLE", "headline": "Context"},
        ],
    }


def test_work_plan_preserves_exact_action_center_order_and_actions() -> None:
    queue = [
        _action("high-first", "HIGH"),
        _action("critical-second", "CRITICAL", blocking=True),
        _action("medium-third", "MEDIUM"),
        _action("low-fourth", "LOW"),
    ]
    action_center = {"schema": "binario.marketing.action-center.v1", "queue": queue}
    before = deepcopy(action_center)

    result = compose_operator_work_plan(
        company={"id": "COMP-1", "name": "Acme"},
        action_center=action_center,
        cockpit=_cockpit(),
        generated_at="2026-08-24T20:00:00+00:00",
    )

    assert result["schema"] == "binario.marketing.operator-work-plan.v1"
    assert [row["action_center_id"] for row in result["sequence"]] == [row["id"] for row in queue]
    assert [row["sequence"] for row in result["sequence"]] == [1, 2, 3, 4]
    assert [row["action"] for row in result["sequence"]] == [row["action"] for row in queue]
    assert action_center == before
    assert result["contracts"]["exact_action_center_order_preserved"] is True
    assert result["contracts"]["action_center_is_priority_authority"] is True


def test_work_plan_only_maps_existing_urgency_into_now_next_later() -> None:
    queue = [
        _action("critical", "CRITICAL"),
        _action("high", "HIGH"),
        _action("medium", "MEDIUM"),
        _action("low", "LOW"),
    ]
    result = compose_operator_work_plan(
        company={"id": "COMP-1", "name": "Acme"},
        action_center={"queue": queue},
        cockpit=_cockpit("STABLE"),
        generated_at="2026-08-24T20:00:00+00:00",
    )

    assert [row["action_center_id"] for row in result["sections"]["now"]] == ["critical", "high"]
    assert [row["action_center_id"] for row in result["sections"]["next"]] == ["medium"]
    assert [row["action_center_id"] for row in result["sections"]["later"]] == ["low"]
    assert result["summary"] == {
        "total": 4,
        "now": 2,
        "next": 1,
        "later": 1,
        "blocking": 0,
        "by_source": {"OPERATIONS": 4},
    }
    assert all(row["priority_recomputed"] is False for row in result["sequence"])


def test_work_plan_never_invents_due_dates_tasks_or_capacity() -> None:
    queue = [
        _action("undated", "HIGH"),
        _action("dated", "MEDIUM", due_at="2026-08-25T12:00:00+00:00"),
    ]
    result = compose_operator_work_plan(
        company={"id": "COMP-1", "name": "Acme"},
        action_center={"queue": queue},
        cockpit=_cockpit(),
        generated_at="2026-08-24T20:00:00+00:00",
    )

    undated, dated = result["sequence"]
    assert undated["schedule"] == {
        "due_at": None,
        "explicit_due_at_present": False,
        "due_at_invented": False,
    }
    assert dated["schedule"]["due_at"] == "2026-08-25T12:00:00+00:00"
    assert dated["schedule"]["due_at_invented"] is False
    assert all(row["task_created"] is False for row in result["sequence"])
    assert result["contracts"]["no_task_store_created"] is True
    assert result["contracts"]["no_task_ownership_invented"] is True
    assert result["contracts"]["no_due_dates_invented"] is True
    assert result["contracts"]["no_capacity_assumption"] is True


def test_executive_cockpit_is_context_only_and_cannot_reorder_plan() -> None:
    queue = [_action("first", "LOW"), _action("second", "CRITICAL", blocking=True)]
    result = compose_operator_work_plan(
        company={"id": "COMP-1", "name": "Acme"},
        action_center={"queue": queue},
        cockpit={
            "status": {"state": "BLOCKED", "headline": "Executive state"},
            "lanes": [
                {"key": "decisions", "label": "Decisions", "state": "BLOCKED", "headline": "Review now"}
            ],
            "top_actions": list(reversed(queue)),
        },
        generated_at="2026-08-24T20:00:00+00:00",
    )

    assert [row["action_center_id"] for row in result["sequence"]] == ["first", "second"]
    assert result["executive_context"]["state"] == "BLOCKED"
    assert result["executive_context"]["affects_priority_order"] is False
    assert result["first_action"]["action_center_id"] == "first"


def test_empty_action_center_is_valid_and_non_authoritative() -> None:
    result = compose_operator_work_plan(
        company={"id": "COMP-1", "name": "Acme"},
        action_center={"queue": []},
        cockpit=_cockpit("STABLE"),
        generated_at="2026-08-24T20:00:00+00:00",
    )

    assert result["first_action"] is None
    assert result["sequence"] == []
    assert result["summary"]["total"] == 0
    assert result["safety"] == {
        "read_only_projection": True,
        "business_mutation_performed": False,
        "provider_read_performed": False,
        "provider_mutation_performed": False,
        "ai_generation_performed": False,
        "automatic_execution": False,
        "background_polling": False,
        "cloud_required": False,
    }


def test_service_surface_is_get_only_and_chained_after_cockpit() -> None:
    source = (ROOT / "src/binario_marketing/service_post_w99_operator_work_plan_app.py").read_text(encoding="utf-8")
    web = (ROOT / "web/operator-work-plan.js").read_text(encoding="utf-8")

    assert "service_post_w99_integrated_cockpit_app as base" in source
    assert 'parts[3] == "operator-work-plan"' in source
    assert "def do_POST" not in source
    assert "loadPostW99OperatorWorkPlanAfterCockpit" in source
    assert "provider_mutation_performed\": False" in source
    assert "/api/companies/${encodeURIComponent(company.id)}/operator-work-plan" in web
    assert "Action Center sigue siendo la única autoridad de prioridad" in web


def test_dev_entrypoint_advances_to_operator_work_plan_without_touching_release_runtime() -> None:
    dev = (ROOT / "src/binario_marketing/service_post_w99_dev_app.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/binario_marketing/cli.py").read_text(encoding="utf-8")
    version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")

    assert "service_post_w99_operator_work_plan_app" in dev
    assert "service_post_w99_integrated_cockpit_app" not in dev
    assert "service_post_w99_dev_app" in cli
    assert 'RELEASE_TAG: str | None = "v0.9.0"' in version
    assert "RELEASE_READY = True" in version
