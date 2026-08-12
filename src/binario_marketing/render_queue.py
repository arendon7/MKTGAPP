from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .projects import ProjectStore
from .video.render import (
    AudioRenderSpec,
    CompositeRenderSpec,
    OverlayRenderSpec,
    RenderSpec,
    composite_ffmpeg_command,
    ffmpeg_command,
    probe_media,
    subtitles_to_srt,
)
from .video.sequence import SequenceClipSpec, SequenceRenderSpec, sequence_ffmpeg_command
from .workspace import Workspace


TERMINAL = {"PASS", "FAIL", "CANCELLED", "INTERRUPTED"}
ACTIVE = {"PENDING", "RUNNING", "CANCELLING"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _safe_label(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    return cleaned[:80] or "clip"


def _composition_hash(payload: dict | None) -> str | None:
    if not payload:
        return None
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class RenderRecord:
    id: str
    project_id: str
    asset_id: str
    output_name: str
    output_relative_path: str
    start: float
    end: float
    width: int
    height: int
    status: str
    progress: float
    created_at: str
    updated_at: str
    error: str | None = None
    sha256: str | None = None
    bytes: int | None = None
    artifact_ref: str | None = None
    composition_sha256: str | None = None
    source_asset_ids: list[str] | None = None
    subtitle_relative_path: str | None = None
    subtitle_artifact_ref: str | None = None
    kind: str = "clip"
    clip_ids: list[str] | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


class RenderQueue:
    def __init__(self, root: Path, projects: ProjectStore, workspace: Workspace, ffmpeg: str | None = None, video_codec: str | None = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "jobs.json"
        self.logs = self.root / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.projects = projects
        self.workspace = workspace
        self.ffmpeg = ffmpeg
        self.video_codec = video_codec
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancelled: set[str] = set()
        self._recover_interrupted()

    def _load(self) -> list[RenderRecord]:
        if not self.registry_path.exists():
            return []
        return [RenderRecord(**row) for row in json.loads(self.registry_path.read_text(encoding="utf-8"))]

    def _save(self, records: list[RenderRecord]) -> None:
        write_json_atomic(self.registry_path, [asdict(row) for row in records])

    def _replace(self, record: RenderRecord) -> RenderRecord:
        with self._lock:
            rows = self._load()
            found = False
            updated: list[RenderRecord] = []
            for row in rows:
                if row.id == record.id:
                    updated.append(record)
                    found = True
                else:
                    updated.append(row)
            if not found:
                updated.append(record)
            self._save(updated)
        return record

    def _recover_interrupted(self) -> None:
        rows = self._load()
        changed = False
        updated: list[RenderRecord] = []
        for row in rows:
            if row.status in ACTIVE:
                self.projects.export_path(row.project_id, row.output_name).unlink(missing_ok=True)
                row = replace(row, status="INTERRUPTED", updated_at=_now(), error="application stopped before render completed")
                changed = True
            updated.append(row)
        if changed:
            self._save(updated)

    def list(self, project_id: str | None = None) -> list[RenderRecord]:
        with self._lock:
            rows = self._load()
        if project_id is not None:
            rows = [row for row in rows if row.project_id == project_id]
        return sorted(rows, key=lambda row: row.created_at)

    def get(self, job_id: str) -> RenderRecord:
        match = next((row for row in self.list() if row.id == job_id), None)
        if match is None:
            raise KeyError(job_id)
        return match

    def output_path(self, job_id: str) -> Path:
        row = self.get(job_id)
        return self.projects.export_path(row.project_id, row.output_name)

    def subtitle_path(self, job_id: str) -> Path | None:
        row = self.get(job_id)
        if not row.subtitle_relative_path:
            return None
        return self.projects.export_path(row.project_id, Path(row.subtitle_relative_path).name)

    def _fail_before_thread(self, record: RenderRecord, exc: Exception) -> RenderRecord:
        failed = replace(record, status="FAIL", updated_at=_now(), error=f"{type(exc).__name__}: {exc}")
        self._replace(failed)
        self.workspace.registries.timeline.append("render.failed", {"job_id": record.id, "project_id": record.project_id, "exception": type(exc).__name__, "kind": record.kind})
        return failed

    def _composition_resources(self, project_id: str, composition: dict) -> tuple[list[OverlayRenderSpec], AudioRenderSpec | None, list[str]]:
        source_asset_ids: list[str] = []
        overlays: list[OverlayRenderSpec] = []
        for row in composition.get("overlays", []):
            asset_id = str(row["asset_id"])
            path = self.projects.asset_path(project_id, asset_id)
            source_asset_ids.append(asset_id)
            overlays.append(OverlayRenderSpec(
                input_path=path,
                start=float(row["start"]),
                end=float(row["end"]),
                x=float(row.get("x", 0.5)),
                y=float(row.get("y", 0.5)),
                scale=float(row.get("scale", 1.0)),
                opacity=float(row.get("opacity", 1.0)),
                z_index=int(row.get("z_index", 10)),
                behind_subject=bool(row.get("behind_subject", False)),
            ))
        audio = None
        row = composition.get("audio_track")
        if isinstance(row, dict) and bool(row.get("enabled", True)):
            asset_id = str(row["asset_id"])
            path = self.projects.asset_path(project_id, asset_id)
            source_asset_ids.append(asset_id)
            audio = AudioRenderSpec(
                input_path=path,
                enabled=True,
                offset_seconds=float(row.get("offset_seconds", 0.0)),
                gain_db=float(row.get("gain_db", 0.0)),
                normalize=bool(row.get("normalize", True)),
                target_lufs=float(row.get("target_lufs", -16.0)),
                replace_original=bool(row.get("replace_original", True)),
            )
        return overlays, audio, source_asset_ids

    def _composition_spec(self, project_id: str, input_path: Path, output: Path, start: float, duration: float, width: int, height: int, composition: dict) -> tuple[CompositeRenderSpec, list[str]]:
        overlays, audio, source_asset_ids = self._composition_resources(project_id, composition)
        return CompositeRenderSpec(
            input_path=input_path,
            output_path=output,
            width=width,
            height=height,
            start=start,
            duration=duration,
            overlays=tuple(overlays),
            audio=audio,
            video_codec=self.video_codec,
            progress=True,
        ), source_asset_ids

    def _validate_runtime(self, record: RenderRecord) -> RenderRecord | None:
        if self.ffmpeg is not None:
            candidate = Path(self.ffmpeg)
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                return self._fail_before_thread(record, FileNotFoundError(f"ffmpeg executable unavailable: {self.ffmpeg}"))
        return None

    def _launch(self, record: RenderRecord, command: list[str], subtitles: list[dict]) -> RenderRecord:
        thread = threading.Thread(target=self._run, args=(record.id, command, subtitles), daemon=True, name=f"render-{record.id}")
        with self._lock:
            self._threads[record.id] = thread
        thread.start()
        return self.get(record.id)

    def start(self, project_id: str, asset_id: str, start: float, end: float, width: int, height: int, label: str = "clip", composition: dict | None = None) -> RenderRecord:
        start = float(start)
        end = float(end)
        width, height = int(width), int(height)
        if start < 0 or end <= start:
            raise ValueError("render range must satisfy 0 <= start < end")
        if width < 64 or height < 64 or width > 7680 or height > 7680:
            raise ValueError("render dimensions are outside supported bounds")
        input_path = self.projects.asset_path(project_id, asset_id)
        job_id = uuid.uuid4().hex[:12]
        output_name = f"{job_id}-{_safe_label(label)}.mp4"
        output = self.projects.export_path(project_id, output_name)
        composition_payload = composition or {}
        record = RenderRecord(
            id=job_id,
            project_id=project_id,
            asset_id=asset_id,
            output_name=output_name,
            output_relative_path=f"exports/{output_name}",
            start=start,
            end=end,
            width=width,
            height=height,
            status="PENDING",
            progress=0.0,
            created_at=_now(),
            updated_at=_now(),
            composition_sha256=_composition_hash(composition_payload),
            source_asset_ids=[asset_id],
        )
        self._replace(record)
        self.workspace.registries.timeline.append("render.queued", {"job_id": job_id, "project_id": project_id, "asset_id": asset_id, "start": start, "end": end, "composition_sha256": record.composition_sha256})
        failed = self._validate_runtime(record)
        if failed is not None:
            return failed
        try:
            if composition_payload.get("overlays") or composition_payload.get("audio_track"):
                spec, extra_sources = self._composition_spec(project_id, input_path, output, start, end - start, width, height, composition_payload)
                record = replace(record, source_asset_ids=list(dict.fromkeys([asset_id, *extra_sources])))
                self._replace(record)
                command = composite_ffmpeg_command(spec, self.ffmpeg)
            else:
                spec = RenderSpec(input_path, output, width, height, video_codec=self.video_codec, start=start, duration=end - start, progress=True)
                command = ffmpeg_command(spec, self.ffmpeg)
        except Exception as exc:
            return self._fail_before_thread(record, exc)
        subtitles = composition_payload.get("subtitles", []) if isinstance(composition_payload.get("subtitles"), list) else []
        return self._launch(record, command, subtitles)

    def start_sequence(self, project_id: str, clips: list[dict], width: int, height: int, label: str = "timeline-master", composition: dict | None = None) -> RenderRecord:
        if not clips:
            raise ValueError("timeline sequence is empty")
        width, height = int(width), int(height)
        if width < 64 or height < 64 or width > 7680 or height > 7680:
            raise ValueError("render dimensions are outside supported bounds")

        sequence_specs: list[SequenceClipSpec] = []
        source_asset_ids: list[str] = []
        clip_ids: list[str] = []
        evidence_sequence: list[dict] = []
        for row in clips:
            clip_id = str(row["id"])
            asset_id = str(row["asset_id"])
            start = float(row["start"])
            end = float(row["end"])
            if start < 0 or end <= start:
                raise ValueError(f"invalid bounds for sequence clip: {clip_id}")
            path = self.projects.asset_path(project_id, asset_id)
            probe = probe_media(path)
            has_audio = any(isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in probe.get("streams", []))
            sequence_specs.append(SequenceClipSpec(path, start, end, has_audio, clip_id))
            source_asset_ids.append(asset_id)
            clip_ids.append(clip_id)
            evidence_sequence.append({"clip_id": clip_id, "asset_id": asset_id, "start": start, "end": end, "has_audio": has_audio})

        duration = sum(item.duration for item in sequence_specs)
        if duration <= 0:
            raise ValueError("timeline sequence duration must be positive")
        composition_payload = composition or {}
        overlays, audio, extra_sources = self._composition_resources(project_id, composition_payload)
        source_asset_ids = list(dict.fromkeys([*source_asset_ids, *extra_sources]))
        evidence = {"sequence": evidence_sequence, "composition": composition_payload}

        job_id = uuid.uuid4().hex[:12]
        output_name = f"{job_id}-{_safe_label(label)}.mp4"
        output = self.projects.export_path(project_id, output_name)
        record = RenderRecord(
            id=job_id,
            project_id=project_id,
            asset_id=str(clips[0]["asset_id"]),
            output_name=output_name,
            output_relative_path=f"exports/{output_name}",
            start=0.0,
            end=duration,
            width=width,
            height=height,
            status="PENDING",
            progress=0.0,
            created_at=_now(),
            updated_at=_now(),
            composition_sha256=_composition_hash(evidence),
            source_asset_ids=source_asset_ids,
            kind="sequence",
            clip_ids=clip_ids,
        )
        self._replace(record)
        self.workspace.registries.timeline.append("render.sequence_queued", {
            "job_id": job_id,
            "project_id": project_id,
            "clip_ids": clip_ids,
            "duration": duration,
            "composition_sha256": record.composition_sha256,
        })
        failed = self._validate_runtime(record)
        if failed is not None:
            return failed
        try:
            spec = SequenceRenderSpec(
                clips=tuple(sequence_specs),
                output_path=output,
                width=width,
                height=height,
                overlays=tuple(overlays),
                audio=audio,
                video_codec=self.video_codec,
                progress=True,
            )
            command = sequence_ffmpeg_command(spec, self.ffmpeg)
        except Exception as exc:
            return self._fail_before_thread(record, exc)
        subtitles = composition_payload.get("subtitles", []) if isinstance(composition_payload.get("subtitles"), list) else []
        return self._launch(record, command, subtitles)

    @staticmethod
    def _progress_seconds(line: str) -> float | None:
        key, sep, value = line.strip().partition("=")
        if not sep:
            return None
        try:
            if key in {"out_time_us", "out_time_ms"}:
                return float(value) / 1_000_000.0
            if key == "out_time":
                hours, minutes, seconds = value.split(":")
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except (TypeError, ValueError):
            return None
        return None

    def _write_subtitle_sidecar(self, row: RenderRecord, subtitles: list[dict]) -> tuple[str | None, str | None]:
        if not subtitles:
            return None, None
        content = subtitles_to_srt(subtitles, row.start, row.end)
        if not content.strip():
            return None, None
        name = f"{Path(row.output_name).stem}.srt"
        path = self.projects.export_path(row.project_id, name)
        path.write_text(content, encoding="utf-8")
        digest, size = _sha256_file(path)
        artifact = self.workspace.registries.record_artifact({
            "project_id": row.project_id,
            "render_job_id": row.id,
            "name": name,
            "kind": "subtitle_srt",
            "relative_path": f"exports/{name}",
            "sha256": digest,
            "bytes": size,
            "render_kind": row.kind,
        })
        return f"exports/{name}", artifact.hash

    def _run(self, job_id: str, command: list[str], subtitles: list[dict]) -> None:
        row = self.get(job_id)
        log_path = self.logs / f"{job_id}.log"
        output = self.output_path(job_id)
        process: subprocess.Popen | None = None
        try:
            with self._lock:
                if job_id in self._cancelled:
                    current = self.get(job_id)
                    self._replace(replace(current, status="CANCELLED", updated_at=_now(), error=None))
                    self.workspace.registries.timeline.append("render.cancelled", {"job_id": job_id, "project_id": row.project_id, "kind": row.kind})
                    return
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
                with self._lock:
                    self._processes[job_id] = process
                    cancelled_after_spawn = job_id in self._cancelled
                self._replace(replace(row, status="RUNNING", updated_at=_now()))
                if cancelled_after_spawn and process.poll() is None:
                    process.terminate()
                if process.stdout is None:
                    raise RuntimeError("ffmpeg progress pipe unavailable")
                last_progress = -1.0
                try:
                    for line in process.stdout:
                        seconds = self._progress_seconds(line)
                        if seconds is not None:
                            progress = max(0.0, min(0.999, seconds / max(row.duration, 0.001)))
                            if progress - last_progress >= 0.01:
                                current = self.get(job_id)
                                self._replace(replace(current, progress=progress, updated_at=_now()))
                                last_progress = progress
                finally:
                    process.stdout.close()
                code = process.wait()
            with self._lock:
                cancelled = job_id in self._cancelled
            if cancelled:
                output.unlink(missing_ok=True)
                current = self.get(job_id)
                self._replace(replace(current, status="CANCELLED", progress=current.progress, updated_at=_now(), error=None))
                self.workspace.registries.timeline.append("render.cancelled", {"job_id": job_id, "project_id": row.project_id, "kind": row.kind})
            elif code == 0 and output.is_file():
                digest, size = _sha256_file(output)
                artifact = self.workspace.registries.record_artifact({
                    "project_id": row.project_id,
                    "render_job_id": job_id,
                    "name": row.output_name,
                    "kind": "rendered_video",
                    "render_kind": row.kind,
                    "relative_path": row.output_relative_path,
                    "sha256": digest,
                    "bytes": size,
                    "composition_sha256": row.composition_sha256,
                    "clip_ids": row.clip_ids,
                })
                subtitle_path, subtitle_ref = self._write_subtitle_sidecar(row, subtitles)
                current = self.get(job_id)
                self._replace(replace(current, status="PASS", progress=1.0, updated_at=_now(), sha256=digest, bytes=size, artifact_ref=artifact.hash, subtitle_relative_path=subtitle_path, subtitle_artifact_ref=subtitle_ref, error=None))
                self.workspace.registries.timeline.append("render.completed", {"job_id": job_id, "project_id": row.project_id, "artifact_ref": artifact.hash, "subtitle_artifact_ref": subtitle_ref, "composition_sha256": row.composition_sha256, "kind": row.kind, "clip_ids": row.clip_ids})
            else:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:] if log_path.exists() else ""
                output.unlink(missing_ok=True)
                current = self.get(job_id)
                self._replace(replace(current, status="FAIL", updated_at=_now(), error=tail or f"ffmpeg exited with code {code}"))
                self.workspace.registries.timeline.append("render.failed", {"job_id": job_id, "project_id": row.project_id, "exit_code": code, "kind": row.kind})
        except Exception as exc:
            output.unlink(missing_ok=True)
            try:
                current = self.get(job_id)
            except KeyError:
                return
            self._replace(replace(current, status="FAIL", updated_at=_now(), error=f"{type(exc).__name__}: {exc}"))
            self.workspace.registries.timeline.append("render.failed", {"job_id": job_id, "project_id": row.project_id, "exception": type(exc).__name__, "kind": row.kind})
        finally:
            if process is not None and process.stdout is not None and not process.stdout.closed:
                process.stdout.close()
            with self._lock:
                self._processes.pop(job_id, None)
                self._threads.pop(job_id, None)
                self._cancelled.discard(job_id)

    def cancel(self, job_id: str) -> RenderRecord:
        with self._lock:
            row = self.get(job_id)
            if row.status in TERMINAL:
                return row
            self._cancelled.add(job_id)
            process = self._processes.get(job_id)
            self._replace(replace(row, status="CANCELLING", updated_at=_now()))
            if process is not None and process.poll() is None:
                process.terminate()
        return self.get(job_id)

    def shutdown(self) -> None:
        with self._lock:
            processes = list(self._processes.items())
            threads = list(self._threads.values())
            for job_id, process in processes:
                if process.poll() is None:
                    self._cancelled.add(job_id)
                    process.terminate()
        for thread in threads:
            thread.join(timeout=5)
