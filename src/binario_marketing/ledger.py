from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LedgerEntry:
    seq: int
    at: str
    kind: str
    payload: dict[str, Any]
    previous_hash: str
    hash: str


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class JsonlLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def entries(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(LedgerEntry(**json.loads(line)))
        return rows

    def append(self, kind: str, payload: dict[str, Any]) -> LedgerEntry:
        existing = self.entries()
        previous_hash = existing[-1].hash if existing else "GENESIS"
        base = {
            "seq": len(existing) + 1,
            "at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        digest = hashlib.sha256(_canonical(base)).hexdigest()
        entry = LedgerEntry(**base, hash=digest)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.__dict__, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
        return entry

    def verify(self) -> bool:
        previous = "GENESIS"
        expected_seq = 1
        for entry in self.entries():
            base = {
                "seq": entry.seq,
                "at": entry.at,
                "kind": entry.kind,
                "payload": entry.payload,
                "previous_hash": entry.previous_hash,
            }
            if entry.seq != expected_seq or entry.previous_hash != previous:
                return False
            if hashlib.sha256(_canonical(base)).hexdigest() != entry.hash:
                return False
            previous = entry.hash
            expected_seq += 1
        return True
