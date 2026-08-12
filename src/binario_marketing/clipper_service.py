from __future__ import annotations

from dataclasses import asdict

from .video.clipper import TranscriptSegment,select_clips
from .video.clipper_narrative import NarrativeSegment,select_narrative_clips


def _row_values(row)->tuple[float,float,str]:
    if isinstance(row,dict):return float(row['start']),float(row['end']),str(row['text'])
    return float(row.start),float(row.end),str(row.text)


def select_clips_payload(segments,payload:dict)->list[dict]:
    target=int(payload.get('target_count',3));minimum=float(payload.get('min_duration',15));maximum=float(payload.get('max_duration',75));mode=payload.get('mode')
    if mode in {'natural','objective'}:
        rows=[NarrativeSegment(*_row_values(row)) for row in segments]
        target_duration=payload.get('target_duration')
        clips=select_narrative_clips(rows,target,mode=str(mode),target_duration=float(target_duration) if target_duration is not None else None,min_duration=minimum,max_duration=maximum)
        return [asdict(item) for item in clips]
    legacy=[TranscriptSegment(*_row_values(row)) for row in segments]
    return [asdict(item) for item in select_clips(legacy,target,minimum,maximum)]
