from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .projects import ProjectStore
from .video.render import RenderSpec, ffmpeg_command
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

    @property
    def duration(self) -> float:
        return self.end - self.start


class RenderQueue:
    def __init__(
        self,
        root: Path,
        projects: ProjectStore,
        workspace: Workspace,
        ffmpeg: str | None = None,
        video_codec: str | None = None,
    ):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "jobs.json"
        self.logs = self.root / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.projects = projects
        self.workspace = workspace
        # Runtime resolution is deliberately lazy so the app can boot in source/dev mode
        # even when FFmpeg is not installed. A real render remains fail-closed.
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
                output = self.projects.export_path(row.project_id, row.output_name)
                output.unlink(missing_ok=True)
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

    def start(self, project_id: str, asset_id: str, start: float, end: float, width: int, height: int, label: str = "clip") -> RenderRecord:
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
        )
        self._replace(record)
        self.workspace.registries.timeline.append("render.queued", {"job_id": job_id, "project_id": project_id, "asset_id": asset_id, "start": start, "end": end})
        spec = RenderSpec(input_path, output, width, height, video_codec=self.video_codec, start=start, duration=end - start, progress=True)
        try:
            command = ffmpeg_command(spec, self.ffmpeg)
        except Exception as exc:
            failed = replace(record, status="FAIL", updated_at=_now(), error=f"{type(exc).__name__}: {exc}")
            self._replace(failed)
            self.workspace.registries.timeline.append("render.failed", {"job_id": job_id, "project_id": project_id, "exception": type(exc).__name__})
            return failed
        thread = threading.Thread(target=self._run, args=(job_id, command), daemon=True, name=f"render-{job_id}")
        with self._lock:
            self._threads[job_id] = thread
        thread.start()
        return self.get(job_id)

    @staticmethod
    def _progress_seconds(line: str) -> float | None:
        key, sep, value = line.strip().partition("=")
        if not sep:
            return None
        try:
            if key in {"out_time_us", "out_time_ms"}:
                # FFmpeg historically labels out_time_ms as milliseconds while reporting microseconds.
                return float(value) / 1_000_000.0
            if key == "out_time":
                hours, minutes, seconds = value.split(":")
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except (TypeError, ValueError):
            return None
        return None

    def _run(self, job_id: str, command: list[str]) -> None:
        row = self.get(job_id)
        log_path = self.logs / f"{job_id}.log"
        output = self.output_path(job_id)
        try:
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
                with self._lock:
                    self._processes[job_id] = process
                self._replace(replace(row, status="RUNNING", updated_at=_now()))
                if process.stdout is None:
                    raise RuntimeError("ffmpeg progress pipe unavailable")
                last_progress = -1.0
                for line in process.stdout:
                    seconds = self._progress_seconds(line)
                    if seconds is not None:
                        progress = max(0.0, min(0.999, seconds / max(row.duration, 0.001)))
                        if progress - last_progress >= 0.01:
                            current = self.get(job_id)
                            self._replace(replace(current, progress=progress, updated_at=_now()))
                            last_progress = progress
                code = process.wait()
            with self._lock:
                cancelled = job_id in self._cancelled
            if cancelled:
                output.unlink(missing_ok=True)
                current = self.get(job_id)
                self._replace(replace(current, status="CANCELLED", progress=current.progress, updated_at=_now(), error=None))
                self.workspace.registries.timeline.append("render.cancelled", {"job_id": job_id, "project_id": row.project_id})
            elif code == 0 and output.is_file():
                digest, size = _sha256_file(output)
                artifact = self.workspace.registries.record_artifact({
                    "project_id": row.project_id,
                    "render_job_id": job_id,
                    "name": row.output_name,
                    "kind": "rendered_video",
                    "relative_path": row.output_relative_path,
                    "sha256": digest,
                    "bytes": size,
                })
                current = self.get(job_id)
                self._replace(replace(current, status="PASS", progress=1.0, updated_at=_now(), sha256=digest, bytes=size, artifact_ref=artifact.hash, error=None))
                self.workspace.registries.timeline.append("render.completed", {"job_id": job_id, "project_id": row.project_id, "artifact_ref": artifact.hash})
            else:
                tail = ""
                if log_path.exists():
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                output.unlink(missing_ok=True)
                current = self.get(job_id)
                self._replace(replace(current, status="FAIL", updated_at=_now(), error=tail or f"ffmpeg exited with code {code}"))
                self.workspace.registries.timeline.append("render.failed", {"job_id": job_id, "project_id": row.project_id, "exit_code": code})
        except Exception as exc:
            output.unlink(missing_ok=True)
            current = self.get(job_id)
            self._replace(replace(current, status="FAIL", updated_at=_now(), error=f"{type(exc).__name__}: {exc}"))
            self.workspace.registries.timeline.append("render.failed", {"job_id": job_id, "project_id": row.project_id, "exception": type(exc).__name__})
        finally:
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
