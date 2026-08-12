from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .projects import ProjectStore
from .video.render import RenderSpec, ffmpeg_command, probe_media
from .workspace import Workspace


PROXY_ACTIVE = {"PENDING", "RUNNING", "CANCELLING"}
PROXY_TERMINAL = {"PASS", "FAIL", "CANCELLED", "INTERRUPTED"}


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


@dataclass(frozen=True)
class ProxyRecord:
    project_id: str
    asset_id: str
    source_sha256: str
    filename: str
    relative_path: str
    status: str
    created_at: str
    updated_at: str
    error: str | None = None
    sha256: str | None = None
    bytes: int | None = None
    width: int | None = None
    height: int | None = None
    artifact_ref: str | None = None


class ProxyManager:
    def __init__(self, root: Path, projects: ProjectStore, workspace: Workspace, ffmpeg: str | None = None, video_codec: str | None = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "proxies.json"
        self.logs = self.root / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.projects = projects
        self.workspace = workspace
        self.ffmpeg = ffmpeg
        self.video_codec = video_codec
        self._lock = threading.RLock()
        self._processes: dict[tuple[str, str], subprocess.Popen] = {}
        self._threads: dict[tuple[str, str], threading.Thread] = {}
        self._recover_interrupted()

    def _load(self) -> list[ProxyRecord]:
        if not self.registry_path.exists():
            return []
        return [ProxyRecord(**row) for row in json.loads(self.registry_path.read_text(encoding="utf-8"))]

    def _save(self, rows: list[ProxyRecord]) -> None:
        write_json_atomic(self.registry_path, [asdict(row) for row in rows])

    def _replace(self, record: ProxyRecord) -> ProxyRecord:
        key = (record.project_id, record.asset_id)
        with self._lock:
            rows = self._load()
            found = False
            updated: list[ProxyRecord] = []
            for row in rows:
                if (row.project_id, row.asset_id) == key:
                    updated.append(record)
                    found = True
                else:
                    updated.append(row)
            if not found:
                updated.append(record)
            self._save(updated)
        return record

    def _remove_record(self, project_id: str, asset_id: str) -> None:
        with self._lock:
            self._save([row for row in self._load() if not (row.project_id == project_id and row.asset_id == asset_id)])

    def _recover_interrupted(self) -> None:
        rows = self._load()
        changed = False
        updated: list[ProxyRecord] = []
        for row in rows:
            if row.status in PROXY_ACTIVE:
                self.projects.proxy_path(row.project_id, row.filename).unlink(missing_ok=True)
                row = replace(row, status="INTERRUPTED", updated_at=_now(), error="application stopped before proxy completed")
                changed = True
            updated.append(row)
        if changed:
            self._save(updated)

    def get(self, project_id: str, asset_id: str) -> ProxyRecord | None:
        with self._lock:
            return next((row for row in self._load() if row.project_id == project_id and row.asset_id == asset_id), None)

    def active_for_asset(self, project_id: str, asset_id: str) -> bool:
        row = self.get(project_id, asset_id)
        return row is not None and row.status in PROXY_ACTIVE

    def file_path(self, project_id: str, asset_id: str) -> Path:
        row = self.get(project_id, asset_id)
        if row is None or row.status != "PASS":
            raise ValueError("proxy is not available until generation passes")
        path = self.projects.proxy_path(project_id, row.filename)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _source_sha(self, project_id: str, asset_id: str) -> tuple[str, Path]:
        asset = self.projects.asset(project_id, asset_id)
        if asset.kind != "video":
            raise ValueError("proxy generation is only supported for video assets")
        path = self.projects.asset_path(project_id, asset_id)
        digest, _ = _sha256_file(path)
        return digest, path

    @staticmethod
    def _proxy_dimensions(source: Path) -> tuple[int, int]:
        payload = probe_media(source)
        stream = next((row for row in payload.get("streams", []) if row.get("codec_type") == "video"), None)
        if not isinstance(stream, dict):
            raise ValueError("video stream is unavailable")
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            raise ValueError("video dimensions are unavailable")
        return (540, 960) if height > width else (960, 540)

    def ensure(self, project_id: str, asset_id: str) -> ProxyRecord:
        source_sha, source = self._source_sha(project_id, asset_id)
        existing = self.get(project_id, asset_id)
        if existing and existing.source_sha256 == source_sha:
            if existing.status in PROXY_ACTIVE:
                return existing
            path = self.projects.proxy_path(project_id, existing.filename)
            if existing.status == "PASS" and path.is_file():
                return existing
        if existing:
            self.projects.proxy_path(project_id, existing.filename).unlink(missing_ok=True)
        filename = f"{asset_id}-{source_sha[:12]}-proxy.mp4"
        record = ProxyRecord(project_id, asset_id, source_sha, filename, f"proxies/{filename}", "PENDING", _now(), _now())
        self._replace(record)
        if self.ffmpeg is not None:
            candidate = Path(self.ffmpeg)
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                failed = replace(record, status="FAIL", updated_at=_now(), error=f"ffmpeg executable unavailable: {self.ffmpeg}")
                return self._replace(failed)
        thread = threading.Thread(target=self._run, args=(record, source), daemon=True, name=f"proxy-{asset_id}")
        with self._lock:
            self._threads[(project_id, asset_id)] = thread
        self.workspace.registries.timeline.append("proxy.queued", {"project_id": project_id, "asset_id": asset_id, "source_sha256": source_sha})
        thread.start()
        return self.get(project_id, asset_id) or record

    def _run(self, row: ProxyRecord, source: Path) -> None:
        key = (row.project_id, row.asset_id)
        target = self.projects.proxy_path(row.project_id, row.filename)
        log_path = self.logs / f"{row.project_id}-{row.asset_id}.log"
        process: subprocess.Popen | None = None
        try:
            width, height = self._proxy_dimensions(source)
            spec = RenderSpec(source, target, width, height, video_codec=self.video_codec, progress=False)
            command = ffmpeg_command(spec, self.ffmpeg)
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=log, stderr=log, text=True)
                with self._lock:
                    self._processes[key] = process
                self._replace(replace(row, status="RUNNING", width=width, height=height, updated_at=_now()))
                code = process.wait()
            if code != 0 or not target.is_file():
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:] if log_path.exists() else f"ffmpeg exited with code {code}"
                target.unlink(missing_ok=True)
                self._replace(replace(self.get(*key) or row, status="FAIL", updated_at=_now(), error=tail))
                self.workspace.registries.timeline.append("proxy.failed", {"project_id": row.project_id, "asset_id": row.asset_id, "exit_code": code})
                return
            digest, size = _sha256_file(target)
            artifact = self.workspace.registries.record_artifact({
                "project_id": row.project_id,
                "asset_id": row.asset_id,
                "name": row.filename,
                "kind": "preview_proxy",
                "relative_path": row.relative_path,
                "source_sha256": row.source_sha256,
                "sha256": digest,
                "bytes": size,
            })
            current = self.get(*key) or row
            self._replace(replace(current, status="PASS", sha256=digest, bytes=size, artifact_ref=artifact.hash, updated_at=_now(), error=None))
            self.workspace.registries.timeline.append("proxy.completed", {"project_id": row.project_id, "asset_id": row.asset_id, "artifact_ref": artifact.hash})
        except Exception as exc:
            target.unlink(missing_ok=True)
            current = self.get(*key) or row
            self._replace(replace(current, status="FAIL", updated_at=_now(), error=f"{type(exc).__name__}: {exc}"))
            self.workspace.registries.timeline.append("proxy.failed", {"project_id": row.project_id, "asset_id": row.asset_id, "exception": type(exc).__name__})
        finally:
            with self._lock:
                self._processes.pop(key, None)
                self._threads.pop(key, None)

    def invalidate(self, project_id: str, asset_id: str) -> None:
        key = (project_id, asset_id)
        row = self.get(project_id, asset_id)
        if row is not None and row.status in PROXY_ACTIVE:
            raise ValueError("asset has an active preview proxy job")
        with self._lock:
            process = self._processes.get(key)
            if process is not None and process.poll() is None:
                raise ValueError("asset has an active preview proxy job")
        if row is not None:
            self.projects.proxy_path(project_id, row.filename).unlink(missing_ok=True)
            self._remove_record(project_id, asset_id)
            self.workspace.registries.timeline.append("proxy.invalidated", {"project_id": project_id, "asset_id": asset_id})

    def shutdown(self) -> None:
        with self._lock:
            processes = list(self._processes.values())
            threads = list(self._threads.values())
            for process in processes:
                if process.poll() is None:
                    process.terminate()
        for thread in threads:
            thread.join(timeout=5)
