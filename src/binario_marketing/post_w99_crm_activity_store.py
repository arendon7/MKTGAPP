from __future__ import annotations

from dataclasses import asdict, replace

from .atomic import write_json_atomic
from .crm_store import ACTIVITY_ID_RE, Activity, CRMStore, _now, _when


class PostW99ActivityCRMStore(CRMStore):
    """Narrow post-W99 extension for scheduling an existing pending activity.

    The operation deliberately changes only ``due_at``. Identity, relationship,
    kind, summary and completion state stay owned by the original CRM record.
    """

    def reschedule_activity(self, company_id: str, activity_id: str, payload: dict) -> Activity:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("activity reschedule payload must be an object")
        unknown = set(payload) - {"due_at"}
        if unknown:
            raise ValueError(f"unsupported activity reschedule fields: {', '.join(sorted(unknown))}")
        if "due_at" not in payload:
            raise ValueError("activity due_at is required")
        due_at = _when(payload.get("due_at"))
        if not due_at:
            raise ValueError("activity due_at must be a valid timestamp")

        with self._lock:
            current = self.get_activity(activity_id)
            if current.company_id != company:
                raise KeyError(activity_id)
            if current.completed_at:
                raise ValueError("completed activity cannot be rescheduled")
            if current.due_at == due_at:
                return current
            row = replace(current, due_at=due_at, updated_at=_now())
            write_json_atomic(self._path(self.activities_root, row.id, ACTIVITY_ID_RE), asdict(row))
            return row


__all__ = ["PostW99ActivityCRMStore"]
