from __future__ import annotations

import math
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic


PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ASPECTS = {"16:9", "9:16", "1:1", "4:5"}
MODES = {"natural", "objective"}
MAX_CLIPS = 50
MAX_REASONS = 16


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _clip(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ValueError("quick clip rows must be objects")
    start = _finite(row.get("start"), "clip start")
    end = _finite(row.get("end"), "clip end")
    text = str(row.get("text") or "").strip()
    if start < 0 or end <= start:
        raise ValueError("invalid quick clip bounds")
    if not text:
        raise ValueError("quick clip text is required")
    result = {"start": start, "end": end, "text": text}
    for key in ("score", "hook_score", "closure_score", "duration_fit"):
        if row.get(key) is not None:
            result[key] = _finite(row[key], key)
    if row.get("tone") is not None:
        tone = str(row["tone"]).strip()
        if tone:
            result["tone"] = tone[:64]
    reasons = row.get("reasons")
    if reasons is not None:
        if not isinstance(reasons, list):
            raise ValueError("quick clip reasons must be a list")
        result["reasons"] = [str(item).strip()[:160] for item in reasons[:MAX_REASONS] if str(item).strip()]
    return result


@dataclass(frozen=True)
class QuickClipSelection:
    project_id: str
    asset_id: str
    transcript_sha256: str
    mode: str
    target_count: int
    min_duration: float
    max_duration: float
    target_duration: float | None
    aspect: str
    clips: list[dict]
    updated_at: str


class QuickClipStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, project_id: str) -> Path:
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("invalid project id")
        return self.root / f"{project_id}.json"

    def get(self, project_id: str) -> QuickClipSelection | None:
        import json
        with self._lock:
            path = self._path(project_id)
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("invalid quick clip selection payload")
            return QuickClipSelection(**payload)

    def save(self, project_id: str, payload: dict) -> QuickClipSelection:
        if not isinstance(payload, dict):
            raise ValueError("quick clip selection must be an object")
        asset_id = str(payload.get("asset_id") or "").strip()
        transcript_sha256 = str(payload.get("transcript_sha256") or "").strip().lower()
        mode = str(payload.get("mode") or "natural").strip().lower()
        aspect = str(payload.get("aspect") or "9:16").strip()
        if not asset_id or len(asset_id) > 128:
            raise ValueError("quick clip asset id is required")
        if not SHA256_RE.fullmatch(transcript_sha256):
            raise ValueError("invalid transcript sha256")
        if mode not in MODES:
            raise ValueError("quick clip mode must be natural or objective")
        if aspect not in ASPECTS:
            raise ValueError("unsupported quick clip aspect")
        target_count = int(payload.get("target_count", 3))
        if target_count < 1 or target_count > MAX_CLIPS:
            raise ValueError("quick clip target_count must be between 1 and 50")
        minimum = _finite(payload.get("min_duration", 15), "min_duration")
        maximum = _finite(payload.get("max_duration", 75), "max_duration")
        if minimum <= 0 or maximum < minimum:
            raise ValueError("invalid quick clip duration bounds")
        raw_target = payload.get("target_duration")
        target = None if raw_target is None else _finite(raw_target, "target_duration")
        if mode == "objective":
            if target is None or not minimum <= target <= maximum:
                raise ValueError("objective quick clip target must stay inside duration bounds")
        clips_raw = payload.get("clips")
        if not isinstance(clips_raw, list) or not clips_raw:
            raise ValueError("quick clip selection requires at least one clip")
        if len(clips_raw) > MAX_CLIPS:
            raise ValueError("quick clip selection exceeds 50 clips")
        clips = [_clip(row) for row in clips_raw]
        selection = QuickClipSelection(
            project_id=project_id,
            asset_id=asset_id,
            transcript_sha256=transcript_sha256,
            mode=mode,
            target_count=target_count,
            min_duration=minimum,
            max_duration=maximum,
            target_duration=target,
            aspect=aspect,
            clips=clips,
            updated_at=_now(),
        )
        with self._lock:
            write_json_atomic(self._path(project_id), asdict(selection))
        return selection

    def clear(self, project_id: str) -> bool:
        with self._lock:
            path = self._path(project_id)
            existed = path.exists()
            path.unlink(missing_ok=True)
            return existed
