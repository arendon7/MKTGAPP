from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ledger import JsonlLedger, LedgerEntry


@dataclass(frozen=True)
class Registries:
    evidence: JsonlLedger
    artifacts: JsonlLedger
    decisions: JsonlLedger
    timeline: JsonlLedger

    @classmethod
    def at(cls, root: Path) -> "Registries":
        return cls(
            JsonlLedger(root / "evidence.jsonl"),
            JsonlLedger(root / "artifacts.jsonl"),
            JsonlLedger(root / "decisions.jsonl"),
            JsonlLedger(root / "timeline.jsonl"),
        )

    def record_evidence(self, payload: dict[str, Any]) -> LedgerEntry:
        entry = self.evidence.append("evidence", payload)
        self.timeline.append("evidence.recorded", {"ref": entry.hash, "summary": payload.get("summary", "")})
        return entry

    def record_artifact(self, payload: dict[str, Any]) -> LedgerEntry:
        entry = self.artifacts.append("artifact", payload)
        self.timeline.append("artifact.recorded", {"ref": entry.hash, "name": payload.get("name", "")})
        return entry

    def record_decision(self, payload: dict[str, Any]) -> LedgerEntry:
        entry = self.decisions.append("decision", payload)
        self.timeline.append("decision.recorded", {"ref": entry.hash, "title": payload.get("title", "")})
        return entry

    def verify_all(self) -> bool:
        return all(ledger.verify() for ledger in (self.evidence, self.artifacts, self.decisions, self.timeline))
