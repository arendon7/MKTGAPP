from __future__ import annotations

from dataclasses import asdict

from .quick_clip_store import QuickClipSelection, QuickClipStore


def _store(runtime) -> QuickClipStore:
    store = getattr(runtime, "_quick_clip_store", None)
    if store is None:
        store = QuickClipStore(runtime.data_root / "State" / "quick-clips")
        runtime._quick_clip_store = store
    return store


def selection_for_project(runtime, project_id: str) -> dict | None:
    row = _store(runtime).get(project_id)
    if row is None:
        return None
    try:
        runtime.projects.asset(project_id, row.asset_id)
    except KeyError:
        _store(runtime).clear(project_id)
        return None
    transcript = runtime.transcriptions.get(project_id, row.asset_id)
    if (
        transcript is None
        or transcript.status != "PASS"
        or not transcript.transcript_sha256
        or transcript.transcript_sha256 != row.transcript_sha256
    ):
        _store(runtime).clear(project_id)
        return None
    return asdict(row)


def save_selection(runtime, project_id: str, payload: dict) -> dict:
    asset_id = str(payload.get("asset_id") or "")
    asset = runtime.projects.asset(project_id, asset_id)
    if asset.kind != "video":
        raise ValueError("quick clip selection requires a video asset")
    transcript = runtime.transcriptions.get(project_id, asset_id)
    if transcript is None or transcript.status != "PASS" or not transcript.transcript_sha256:
        raise ValueError("quick clip selection requires a completed transcription")
    clips = payload.get("clips")
    if isinstance(clips, list) and transcript.duration is not None:
        limit = float(transcript.duration) + 0.5
        for row in clips:
            if isinstance(row, dict) and float(row.get("end", 0)) > limit:
                raise ValueError("quick clip exceeds transcript duration")
    canonical = dict(payload)
    canonical["asset_id"] = asset_id
    canonical["transcript_sha256"] = transcript.transcript_sha256
    row = _store(runtime).save(project_id, canonical)
    runtime.workspace.registries.timeline.append(
        "quick_clips.saved",
        {
            "project_id": project_id,
            "asset_id": row.asset_id,
            "transcript_sha256": row.transcript_sha256,
            "mode": row.mode,
            "aspect": row.aspect,
            "clips_count": len(row.clips),
        },
    )
    return asdict(row)


def clear_selection(runtime, project_id: str, *, reason: str = "user") -> bool:
    cleared = _store(runtime).clear(project_id)
    if cleared:
        runtime.workspace.registries.timeline.append(
            "quick_clips.cleared",
            {"project_id": project_id, "reason": reason},
        )
    return cleared


def clear_selection_for_asset(runtime, project_id: str, asset_id: str) -> bool:
    row: QuickClipSelection | None = _store(runtime).get(project_id)
    if row is None or row.asset_id != asset_id:
        return False
    return clear_selection(runtime, project_id, reason="asset_deleted")
