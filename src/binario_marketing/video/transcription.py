from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .render import resolve_ffmpeg


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    end: float
    text: str
    confidence: float | None = None


def _clock_seconds(value: str) -> float:
    text=value.strip().replace(',', '.')
    parts=text.split(':')
    if len(parts)!=3:
        raise ValueError(f'invalid transcript timestamp: {value}')
    return int(parts[0])*3600+int(parts[1])*60+float(parts[2])


def _segment_from_row(row: dict) -> SpeechSegment | None:
    text=str(row.get('text') or row.get('sentence') or '').strip()
    if not text:
        return None
    start=row.get('start');end=row.get('end')
    offsets=row.get('offsets') if isinstance(row.get('offsets'),dict) else {}
    timestamps=row.get('timestamps') if isinstance(row.get('timestamps'),dict) else {}
    if start is None:
        start=offsets.get('from')
        if isinstance(start,(int,float)) and start>1000:start=float(start)/1000.0
    if end is None:
        end=offsets.get('to')
        if isinstance(end,(int,float)) and end>1000:end=float(end)/1000.0
    if start is None and timestamps.get('from') is not None:start=_clock_seconds(str(timestamps['from']))
    if end is None and timestamps.get('to') is not None:end=_clock_seconds(str(timestamps['to']))
    if start is None or end is None:
        return None
    start=float(start);end=float(end)
    if start<0 or end<=start:
        return None
    confidence=row.get('confidence')
    if confidence is None and isinstance(row.get('avg_logprob'),(int,float)):
        confidence=max(0.0,min(1.0,1.0+float(row['avg_logprob'])))
    return SpeechSegment(start,end,text,float(confidence) if confidence is not None else None)


def parse_whisper_json(payload: dict) -> tuple[str | None,list[SpeechSegment]]:
    language=None
    result=payload.get('result') if isinstance(payload.get('result'),dict) else {}
    if result.get('language'):language=str(result['language'])
    elif payload.get('language'):language=str(payload['language'])
    rows=payload.get('transcription')
    if not isinstance(rows,list):rows=payload.get('segments')
    if not isinstance(rows,list):rows=[]
    segments=[]
    for row in rows:
        if not isinstance(row,dict):continue
        segment=_segment_from_row(row)
        if segment is not None:segments.append(segment)
    segments.sort(key=lambda item:(item.start,item.end))
    return language,segments


def transcript_sha256(segments:list[SpeechSegment]) -> str:
    encoded=json.dumps([asdict(item) for item in segments],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def resolve_whisper_cli(explicit:str|None=None) -> str:
    candidate=explicit or os.environ.get('BINARIO_WHISPER_CLI') or shutil.which('whisper-cli')
    if not candidate:raise FileNotFoundError('whisper.cpp CLI runtime is unavailable')
    return candidate


def resolve_whisper_model(explicit:str|None=None) -> str:
    candidate=explicit or os.environ.get('BINARIO_WHISPER_MODEL')
    if not candidate:raise FileNotFoundError('whisper.cpp model is unavailable')
    path=Path(candidate)
    if not path.is_file():raise FileNotFoundError(path)
    return str(path)


def extract_audio_command(input_path:Path,output_wav:Path,ffmpeg:str|None=None) -> list[str]:
    return [resolve_ffmpeg(ffmpeg),'-y','-hide_banner','-loglevel','error','-i',str(input_path),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(output_wav)]


def whisper_command(audio_wav:Path,output_prefix:Path,whisper_cli:str|None=None,model:str|None=None,language:str|None=None) -> list[str]:
    command=[resolve_whisper_cli(whisper_cli),'-m',resolve_whisper_model(model),'-f',str(audio_wav),'-oj','-of',str(output_prefix)]
    if language and language.lower() not in {'auto','automatic'}:command+=['-l',language]
    return command


def load_whisper_output(output_prefix:Path) -> tuple[str|None,list[SpeechSegment]]:
    path=output_prefix.with_suffix('.json')
    if not path.is_file():raise FileNotFoundError(path)
    payload=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload,dict):raise ValueError('whisper output JSON must be an object')
    language,segments=parse_whisper_json(payload)
    if not segments:raise ValueError('transcription produced no speech segments')
    return language,segments
