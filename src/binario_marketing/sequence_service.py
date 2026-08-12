from __future__ import annotations

from dataclasses import asdict


RENDER_DIMENSIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


def start_sequence_render(runtime, project_id: str, payload: dict) -> dict:
    editor = runtime.editors.state(project_id)
    track = int(payload.get("track", 0))
    clips = [row for row in editor.get("clips", []) if int(row.get("track", 0)) == track]
    if not clips:
        raise ValueError(f"timeline track {track} has no clips")
    aspect = str(payload.get("aspect") or editor.get("aspect_ratio") or "16:9")
    if aspect not in RENDER_DIMENSIONS:
        raise ValueError(f"unsupported render aspect: {aspect}")
    width, height = RENDER_DIMENSIONS[aspect]
    composition = {
        "overlays": editor.get("overlays", []),
        "subtitles": editor.get("subtitles", []),
        "audio_track": editor.get("audio_track"),
    }
    row = runtime.renders.start_sequence(
        project_id,
        clips,
        width,
        height,
        str(payload.get("label") or f"timeline-track-{track}"),
        composition=composition,
    )
    return asdict(row)
