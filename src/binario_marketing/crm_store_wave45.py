from __future__ import annotations

from dataclasses import asdict, replace

from .atomic import write_json_atomic
from .crm_store import ACTIVITY_ID_RE, CRMStore
from .social_store import _now, _parse_when


class CRMStoreWave45(CRMStore):
    """Wave 45 adds one explicit mutation: move a pending follow-up to a future due date."""

    def reschedule_activity(self, company_id: str, activity_id: str, due_at: object):
        company = self._company_id(company_id)
        raw = str(due_at or "").strip()
        if not raw:
            raise ValueError("due_at is required")
        try:
            parsed = _parse_when(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("due_at must be an ISO timestamp with timezone") from exc
        if parsed is None:
            raise ValueError("invalid due_at")
        now_parsed = _parse_when(_now())
        if parsed <= now_parsed:
            raise ValueError("due_at must be in the future")
        with self._lock:
            current = self.get_activity(activity_id)
            if current.company_id != company:
                raise KeyError(activity_id)
            if current.completed_at:
                raise ValueError("completed activity cannot be rescheduled")
            now = _now()
            row = replace(current, due_at=parsed.isoformat(), updated_at=now)
            write_json_atomic(self._path(self.activities_root, row.id, ACTIVITY_ID_RE), asdict(row))
            return row


__all__ = ["CRMStoreWave45"]
