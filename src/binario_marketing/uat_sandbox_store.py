from __future__ import annotations

import json
import threading
from pathlib import Path

from .atomic import write_json_atomic
from .social_store import _now


class UATSandboxStore:
    """Tracks synthetic UAT companies without granting them release-evidence authority."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.history_root = self.root / "history"
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def current_path(self) -> Path:
        return self.root / "current.json"

    def _load(self, path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid UAT sandbox manifest")
        if payload.get("schema") != "binario.marketing.uat-sandbox.v1":
            raise ValueError("unsupported UAT sandbox manifest")
        return payload

    def current(self) -> dict | None:
        with self._lock:
            if not self.current_path.is_file():
                return None
            return self._load(self.current_path)

    def history(self) -> list[dict]:
        with self._lock:
            rows = [self._load(path) for path in self.history_root.glob("sandbox-*.json")]
        return sorted(rows, key=lambda row: (int(row.get("generation") or 0), row.get("created_at") or ""), reverse=True)

    def next_generation(self) -> int:
        rows = self.history()
        return (max((int(row.get("generation") or 0) for row in rows), default=0) + 1)

    def save(self, *, generation: int, company_id: str, company_name: str, entities: dict) -> dict:
        if generation < 1:
            raise ValueError("sandbox generation must be positive")
        row = {
            "schema": "binario.marketing.uat-sandbox.v1",
            "generation": generation,
            "company_id": str(company_id),
            "company_name": str(company_name),
            "created_at": _now(),
            "synthetic_data": True,
            "functional_uat_only": True,
            "physical_release_evidence_allowed": False,
            "provider_evidence_seeded": False,
            "results_evidence_seeded": False,
            "entities": dict(entities or {}),
        }
        history_path = self.history_root / f"sandbox-{generation:04d}.json"
        with self._lock:
            write_json_atomic(history_path, row)
            write_json_atomic(self.current_path, row)
        return row

    def is_sandbox(self, company_id: str) -> bool:
        wanted = str(company_id or "").strip()
        if not wanted:
            return False
        current = self.current()
        if current and current.get("company_id") == wanted:
            return True
        return any(row.get("company_id") == wanted for row in self.history())


__all__ = ["UATSandboxStore"]
