from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from dataclasses import asdict,dataclass,replace
from datetime import datetime,timezone
from pathlib import Path

from .atomic import write_json_atomic
from .projects import ProjectStore
from .video.transcription import SpeechSegment,extract_audio_command,load_whisper_output,resolve_whisper_model,transcript_sha256,whisper_command
from .workspace import Workspace


TRANSCRIPTION_ACTIVE={'PENDING','EXTRACTING_AUDIO','TRANSCRIBING','CANCELLING'}
TRANSCRIPTION_TERMINAL={'PASS','FAIL','CANCELLED','INTERRUPTED'}


def _now()->str:return datetime.now(timezone.utc).isoformat()

def _sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TranscriptRecord:
    project_id:str
    asset_id:str
    source_sha256:str
    status:str
    created_at:str
    updated_at:str
    language:str|None=None
    requested_language:str='auto'
    engine:str='whisper.cpp'
    model_sha256:str|None=None
    transcript_relative_path:str|None=None
    transcript_sha256:str|None=None
    segments_count:int=0
    duration:float|None=None
    artifact_ref:str|None=None
    error:str|None=None


class TranscriptionManager:
    def __init__(self,root:Path,projects:ProjectStore,workspace:Workspace,*,ffmpeg:str|None=None,whisper_cli:str|None=None,model:str|None=None):
        self.root=root;self.root.mkdir(parents=True,exist_ok=True)
        self.registry_path=self.root/'transcriptions.json'
        self.work=self.root/'work';self.work.mkdir(parents=True,exist_ok=True)
        self.logs=self.root/'logs';self.logs.mkdir(parents=True,exist_ok=True)
        self.projects=projects;self.workspace=workspace
        self.ffmpeg=ffmpeg;self.whisper_cli=whisper_cli;self.model=model
        self._lock=threading.RLock();self._processes={};self._threads={};self._cancelled=set();self._model_sha_cache=None
        self._recover_interrupted()

    def _load(self)->list[TranscriptRecord]:
        if not self.registry_path.exists():return []
        return [TranscriptRecord(**row) for row in json.loads(self.registry_path.read_text(encoding='utf-8'))]

    def _save(self,rows:list[TranscriptRecord])->None:write_json_atomic(self.registry_path,[asdict(row) for row in rows])

    def _replace(self,record:TranscriptRecord)->TranscriptRecord:
        key=(record.project_id,record.asset_id)
        with self._lock:
            rows=self._load();found=False;updated=[]
            for row in rows:
                if (row.project_id,row.asset_id)==key:updated.append(record);found=True
                else:updated.append(row)
            if not found:updated.append(record)
            self._save(updated)
        return record

    def _recover_interrupted(self)->None:
        rows=self._load();changed=False;updated=[]
        for row in rows:
            if row.status in TRANSCRIPTION_ACTIVE:
                row=replace(row,status='INTERRUPTED',updated_at=_now(),error='application stopped before transcription completed');changed=True
            updated.append(row)
        if changed:self._save(updated)

    def get(self,project_id:str,asset_id:str)->TranscriptRecord|None:
        with self._lock:return next((row for row in self._load() if row.project_id==project_id and row.asset_id==asset_id),None)

    def list(self,project_id:str|None=None)->list[TranscriptRecord]:
        with self._lock:rows=self._load()
        return [row for row in rows if project_id is None or row.project_id==project_id]

    def active_for_asset(self,project_id:str,asset_id:str)->bool:
        row=self.get(project_id,asset_id)
        return row is not None and row.status in TRANSCRIPTION_ACTIVE

    def _remove_record(self,project_id:str,asset_id:str)->None:
        with self._lock:self._save([row for row in self._load() if not (row.project_id==project_id and row.asset_id==asset_id)])

    def invalidate(self,project_id:str,asset_id:str)->None:
        row=self.get(project_id,asset_id)
        if row is None:return
        if row.status in TRANSCRIPTION_ACTIVE:raise ValueError('asset has an active transcription job')
        if row.transcript_relative_path:
            project_root=self.projects.path_for(project_id).resolve();path=(project_root/row.transcript_relative_path).resolve();root=self._transcripts_dir(project_id)
            if root not in path.parents:raise ValueError('transcript path escaped managed transcripts root')
            path.unlink(missing_ok=True)
        self._remove_record(project_id,asset_id)
        self.workspace.registries.timeline.append('transcription.invalidated',{'project_id':project_id,'asset_id':asset_id})

    def _transcripts_dir(self,project_id:str)->Path:
        root=self.projects.path_for(project_id).resolve();path=(root/'transcripts').resolve()
        if root not in path.parents:raise ValueError('transcripts path escaped project root')
        path.mkdir(parents=True,exist_ok=True);return path

    def transcript_path(self,project_id:str,asset_id:str)->Path:
        row=self.get(project_id,asset_id)
        if row is None or row.status!='PASS' or not row.transcript_relative_path:raise ValueError('transcript is not available until transcription passes')
        project_root=self.projects.path_for(project_id).resolve();path=(project_root/row.transcript_relative_path).resolve();root=self._transcripts_dir(project_id)
        if root not in path.parents:raise ValueError('transcript path escaped managed transcripts root')
        if not path.is_file():raise FileNotFoundError(path)
        return path

    def segments(self,project_id:str,asset_id:str)->list[dict]:
        path=self.transcript_path(project_id,asset_id);payload=json.loads(path.read_text(encoding='utf-8'))
        rows=payload.get('segments',[]) if isinstance(payload,dict) else []
        if not isinstance(rows,list):raise ValueError('stored transcript segments are invalid')
        return rows

    def _source_sha(self,project_id:str,asset_id:str)->tuple[str,Path]:
        asset=self.projects.asset(project_id,asset_id)
        if asset.kind not in {'video','audio'}:raise ValueError('automatic transcription requires a video or audio asset')
        path=self.projects.asset_path(project_id,asset_id)
        return _sha256_file(path),path

    def _model_sha(self)->str|None:
        if self._model_sha_cache:return self._model_sha_cache
        try:
            candidate=resolve_whisper_model(self.model)
        except FileNotFoundError:
            return None
        self._model_sha_cache=_sha256_file(Path(candidate))
        return self._model_sha_cache

    def ensure(self,project_id:str,asset_id:str,language:str='auto',force:bool=False)->TranscriptRecord:
        source_sha,source=self._source_sha(project_id,asset_id);requested=(language or 'auto').strip().lower() or 'auto';model_sha=self._model_sha()
        existing=self.get(project_id,asset_id)
        if existing and not force and existing.source_sha256==source_sha and existing.requested_language==requested and existing.model_sha256==model_sha:
            if existing.status in TRANSCRIPTION_ACTIVE:return existing
            if existing.status=='PASS':
                try:self.transcript_path(project_id,asset_id);return existing
                except (ValueError,FileNotFoundError):pass
        if existing and existing.status in TRANSCRIPTION_ACTIVE:raise ValueError('asset already has an active transcription job')
        record=TranscriptRecord(project_id,asset_id,source_sha,'PENDING',_now(),_now(),requested_language=requested,model_sha256=model_sha)
        self._replace(record)
        try:
            ffmpeg=extract_audio_command(source,self.work/f'{project_id}-{asset_id}.wav',self.ffmpeg)[0]
            whisper=whisper_command(self.work/f'{project_id}-{asset_id}.wav',self.work/f'{project_id}-{asset_id}',self.whisper_cli,self.model,requested)[0]
            for binary,label in ((ffmpeg,'ffmpeg'),(whisper,'whisper-cli')):
                candidate=Path(binary)
                if ('/' in binary or binary.startswith('.')) and (not candidate.is_file() or not os.access(candidate,os.X_OK)):raise FileNotFoundError(f'{label} executable unavailable: {binary}')
        except Exception as exc:
            return self._fail(record,exc)
        thread=threading.Thread(target=self._run,args=(record,source),daemon=True,name=f'transcribe-{asset_id}')
        with self._lock:self._threads[(project_id,asset_id)]=thread
        self.workspace.registries.timeline.append('transcription.queued',{'project_id':project_id,'asset_id':asset_id,'source_sha256':source_sha,'language':requested})
        thread.start();return self.get(project_id,asset_id) or record

    def _fail(self,row:TranscriptRecord,exc:Exception)->TranscriptRecord:
        failed=replace(row,status='FAIL',updated_at=_now(),error=f'{type(exc).__name__}: {exc}');self._replace(failed)
        self.workspace.registries.timeline.append('transcription.failed',{'project_id':row.project_id,'asset_id':row.asset_id,'exception':type(exc).__name__})
        return failed

    def _run_process(self,key:tuple[str,str],command:list[str],log)->int:
        process=subprocess.Popen(command,stdout=log,stderr=log,text=True)
        with self._lock:self._processes[key]=process;cancelled=key in self._cancelled
        if cancelled and process.poll() is None:process.terminate()
        return process.wait()

    def _run(self,row:TranscriptRecord,source:Path)->None:
        key=(row.project_id,row.asset_id);wav=self.work/f'{row.project_id}-{row.asset_id}.wav';prefix=self.work/f'{row.project_id}-{row.asset_id}';json_output=prefix.with_suffix('.json');log_path=self.logs/f'{row.project_id}-{row.asset_id}.log'
        try:
            for path in (wav,json_output):path.unlink(missing_ok=True)
            with log_path.open('w',encoding='utf-8') as log:
                self._replace(replace(row,status='EXTRACTING_AUDIO',updated_at=_now()))
                code=self._run_process(key,extract_audio_command(source,wav,self.ffmpeg),log)
                if self._is_cancelled(key):return self._finish_cancelled(row,wav,json_output)
                if code!=0 or not wav.is_file():raise RuntimeError(f'audio extraction failed with exit code {code}')
                current=self.get(*key) or row;self._replace(replace(current,status='TRANSCRIBING',updated_at=_now()))
                code=self._run_process(key,whisper_command(wav,prefix,self.whisper_cli,self.model,row.requested_language),log)
                if self._is_cancelled(key):return self._finish_cancelled(row,wav,json_output)
                if code!=0:raise RuntimeError(f'whisper.cpp exited with code {code}')
            language,segments=load_whisper_output(prefix);duration=max(item.end for item in segments);digest=transcript_sha256(segments)
            target=self._transcripts_dir(row.project_id)/f'{row.asset_id}-{row.source_sha256[:12]}.json'
            payload={'project_id':row.project_id,'asset_id':row.asset_id,'source_sha256':row.source_sha256,'engine':'whisper.cpp','language':language or row.requested_language,'model_sha256':row.model_sha256,'segments':[asdict(item) for item in segments]}
            write_json_atomic(target,payload)
            artifact=self.workspace.registries.record_artifact({'project_id':row.project_id,'asset_id':row.asset_id,'name':target.name,'kind':'transcript_json','relative_path':f'transcripts/{target.name}','source_sha256':row.source_sha256,'transcript_sha256':digest,'segments_count':len(segments),'duration':duration,'language':language or row.requested_language,'model_sha256':row.model_sha256})
            current=self.get(*key) or row;done=replace(current,status='PASS',updated_at=_now(),language=language or row.requested_language,transcript_relative_path=f'transcripts/{target.name}',transcript_sha256=digest,segments_count=len(segments),duration=duration,artifact_ref=artifact.hash,error=None)
            self.workspace.registries.timeline.append('transcription.completed',{'project_id':row.project_id,'asset_id':row.asset_id,'artifact_ref':artifact.hash,'segments_count':len(segments),'duration':duration})
            self._replace(done)
        except Exception as exc:self._fail(self.get(*key) or row,exc)
        finally:
            wav.unlink(missing_ok=True);json_output.unlink(missing_ok=True)
            with self._lock:self._processes.pop(key,None);self._threads.pop(key,None);self._cancelled.discard(key)

    def _is_cancelled(self,key)->bool:
        with self._lock:return key in self._cancelled

    def _finish_cancelled(self,row,wav,json_output):
        wav.unlink(missing_ok=True);json_output.unlink(missing_ok=True);current=self.get(row.project_id,row.asset_id) or row;self._replace(replace(current,status='CANCELLED',updated_at=_now(),error=None));self.workspace.registries.timeline.append('transcription.cancelled',{'project_id':row.project_id,'asset_id':row.asset_id})

    def cancel(self,project_id:str,asset_id:str)->TranscriptRecord:
        key=(project_id,asset_id);row=self.get(*key)
        if row is None:raise KeyError(asset_id)
        if row.status in TRANSCRIPTION_TERMINAL:return row
        with self._lock:
            self._cancelled.add(key);process=self._processes.get(key);self._replace(replace(row,status='CANCELLING',updated_at=_now()))
            if process is not None and process.poll() is None:process.terminate()
        return self.get(*key) or row

    def shutdown(self)->None:
        with self._lock:
            processes=list(self._processes.items());threads=list(self._threads.values())
            for key,process in processes:
                self._cancelled.add(key)
                if process.poll() is None:process.terminate()
        for thread in threads:thread.join(timeout=5)
