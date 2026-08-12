from __future__ import annotations

from dataclasses import asdict

from .video.clipper import TranscriptSegment,select_clips


def select_transcript_clips(runtime,project_id:str,asset_id:str,payload:dict)->list[dict]:
    rows=runtime.transcriptions.segments(project_id,asset_id)
    segments=[]
    for row in rows:
        if not isinstance(row,dict):continue
        text=str(row.get('text') or '').strip()
        if not text:continue
        segments.append(TranscriptSegment(float(row['start']),float(row['end']),text))
    if not segments:raise ValueError('transcript has no usable segments')
    target=int(payload.get('target_count',3));minimum=float(payload.get('min_duration',15));maximum=float(payload.get('max_duration',75))
    return [asdict(item) for item in select_clips(segments,target,minimum,maximum)]
