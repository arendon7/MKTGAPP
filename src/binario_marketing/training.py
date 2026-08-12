from __future__ import annotations

import csv
import json
from pathlib import Path


def _normalize(item: dict) -> dict:
    question = str(item.get("question") or item.get("input") or item.get("prompt") or "").strip()
    answer = str(item.get("answer") or item.get("output") or item.get("response") or "").strip()
    if not question and not answer:
        raise ValueError("empty training row")
    return {"input": question, "output": answer}


def load_training_source(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        blocks = [part.strip() for part in path.read_text(encoding="utf-8").split("\n\n") if part.strip()]
        return [{"input": block, "output": ""} for block in blocks]
    if suffix == ".jsonl":
        return [_normalize(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("items", [])
        return [_normalize(item) for item in rows]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [_normalize(row) for row in csv.DictReader(handle)]
    raise ValueError(f"unsupported training source: {suffix}")
