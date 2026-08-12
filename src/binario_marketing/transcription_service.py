from __future__ import annotations

from .clipper_service import select_clips_payload


def select_transcript_clips(runtime,project_id:str,asset_id:str,payload:dict)->list[dict]:
    rows=runtime.transcriptions.segments(project_id,asset_id)
    return select_clips_payload(rows,payload)
