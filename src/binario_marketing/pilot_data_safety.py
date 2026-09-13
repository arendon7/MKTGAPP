from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic


SNAPSHOT_SCHEMA = "binario.marketing.pilot-data-snapshot.v1"
SNAPSHOT_ID_RE = re.compile(r"^snapshot_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
EXCLUDED_DIR_NAMES = {"temp", "logs"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"snapshot_{stamp}_{uuid.uuid4().hex[:8]}"


def _is_transient_file(path: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.endswith(".part"):
        return True
    # write_json_atomic creates siblings such as companies.json.<random> before os.replace.
    if ".json." in name and not name.endswith(".json"):
        return True
    return False


class PilotDataSafety:
    """Operator-triggered, local-only snapshots for the post-W99 pilot.

    Snapshots are copies, not a second source of truth. Restore/delete authority is
    deliberately absent from this first safety increment.
    """

    def __init__(self, data_root: Path, backup_root: Path | None = None):
        self.data_root = Path(data_root).expanduser().resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.backup_root = Path(backup_root or (self.data_root.parent / f"{self.data_root.name} Backups")).expanduser().resolve()
        if self.backup_root == self.data_root or self.data_root in self.backup_root.parents:
            raise ValueError("backup root must be outside the application data root")
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _allowed_relative(relative: Path) -> bool:
        if any(part.casefold() in EXCLUDED_DIR_NAMES for part in relative.parts[:-1]):
            return False
        return not _is_transient_file(relative)

    def _scan(self) -> dict[str, tuple[int, int]]:
        """Return stable metadata for authoritative files and fail closed on symlinks."""
        if self.data_root.is_symlink():
            raise ValueError("application data root must not be a symbolic link")
        rows: dict[str, tuple[int, int]] = {}
        for dirpath, dirnames, filenames in os.walk(self.data_root, topdown=True, followlinks=False):
            directory = Path(dirpath)
            kept_dirs: list[str] = []
            for name in dirnames:
                child = directory / name
                relative = child.relative_to(self.data_root)
                if any(part.casefold() in EXCLUDED_DIR_NAMES for part in relative.parts):
                    continue
                if child.is_symlink():
                    raise ValueError("snapshot refused because application data contains a symbolic link")
                kept_dirs.append(name)
            dirnames[:] = kept_dirs
            for name in filenames:
                source = directory / name
                relative = source.relative_to(self.data_root)
                if not self._allowed_relative(relative):
                    continue
                if source.is_symlink():
                    raise ValueError("snapshot refused because application data contains a symbolic link")
                try:
                    stat = source.stat()
                except FileNotFoundError as exc:
                    raise ValueError("application data changed while preparing the snapshot; retry") from exc
                if not source.is_file():
                    raise ValueError("snapshot supports regular application files only")
                rows[relative.as_posix()] = (int(stat.st_size), int(stat.st_mtime_ns))
        return dict(sorted(rows.items()))

    @staticmethod
    def _copy_with_digest(source: Path, target: Path, expected: tuple[int, int]) -> tuple[int, str]:
        before = source.stat()
        if (int(before.st_size), int(before.st_mtime_ns)) != expected:
            raise ValueError("application data changed while creating the snapshot; retry")
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        written = 0
        with source.open("rb") as src, target.open("xb") as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(chunk)
                digest.update(chunk)
                written += len(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        after = source.stat()
        if (int(after.st_size), int(after.st_mtime_ns)) != expected or written != expected[0]:
            raise ValueError("application data changed while creating the snapshot; retry")
        shutil.copystat(source, target, follow_symlinks=False)
        return written, digest.hexdigest()

    @staticmethod
    def _manifest(path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != SNAPSHOT_SCHEMA:
            raise ValueError("invalid pilot snapshot manifest")
        snapshot_id = str(payload.get("id") or "")
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
            raise ValueError("invalid pilot snapshot id")
        files = payload.get("files")
        if not isinstance(files, list):
            raise ValueError("invalid pilot snapshot file inventory")
        return payload

    @staticmethod
    def _public(payload: dict, *, verified: bool | None = None) -> dict:
        result = {
            "schema": SNAPSHOT_SCHEMA,
            "id": payload["id"],
            "created_at": payload["created_at"],
            "file_count": int(payload.get("file_count") or 0),
            "total_bytes": int(payload.get("total_bytes") or 0),
            "excluded_transient": list(payload.get("excluded_transient") or []),
            "restore_available": False,
        }
        if verified is not None:
            result["verified"] = bool(verified)
        return result

    def create_snapshot(self) -> dict:
        with self._lock:
            before = self._scan()
            snapshot_id = _snapshot_id()
            final = self.backup_root / snapshot_id
            temporary = self.backup_root / f".{snapshot_id}.part"
            if final.exists() or temporary.exists():
                raise ValueError("snapshot id collision; retry")
            records: list[dict] = []
            total_bytes = 0
            try:
                data_target = temporary / "data"
                temporary.mkdir(parents=False, exist_ok=False)
                for relative, expected in before.items():
                    source = self.data_root / Path(relative)
                    target = data_target / Path(relative)
                    size, digest = self._copy_with_digest(source, target, expected)
                    records.append({"path": relative, "bytes": size, "sha256": digest})
                    total_bytes += size
                after = self._scan()
                if before != after:
                    raise ValueError("application data changed during snapshot creation; retry")
                payload = {
                    "schema": SNAPSHOT_SCHEMA,
                    "id": snapshot_id,
                    "created_at": _now(),
                    "file_count": len(records),
                    "total_bytes": total_bytes,
                    "excluded_transient": ["temp", "logs", "hidden/partial files"],
                    "files": records,
                }
                write_json_atomic(temporary / "manifest.json", payload)
                self._verify_directory(temporary, payload)
                os.replace(temporary, final)
                return self._public(payload, verified=True)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise

    def _verify_directory(self, snapshot_root: Path, payload: dict) -> None:
        data_root = snapshot_root / "data"
        expected = payload.get("files") or []
        seen: set[str] = set()
        total = 0
        for row in expected:
            if not isinstance(row, dict):
                raise ValueError("invalid pilot snapshot file record")
            relative = str(row.get("path") or "")
            rel = Path(relative)
            if not relative or rel.is_absolute() or ".." in rel.parts or relative in seen:
                raise ValueError("invalid pilot snapshot relative path")
            seen.add(relative)
            target = data_root / rel
            if target.is_symlink() or not target.is_file():
                raise ValueError("pilot snapshot verification failed")
            expected_bytes = int(row.get("bytes") or 0)
            if target.stat().st_size != expected_bytes:
                raise ValueError("pilot snapshot verification failed")
            digest = hashlib.sha256()
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest().lower() != str(row.get("sha256") or "").lower():
                raise ValueError("pilot snapshot verification failed")
            total += expected_bytes
        actual: set[str] = set()
        if data_root.is_dir():
            for path in data_root.rglob("*"):
                if path.is_symlink():
                    raise ValueError("pilot snapshot verification failed")
                if path.is_file():
                    actual.add(path.relative_to(data_root).as_posix())
        if actual != seen or total != int(payload.get("total_bytes") or 0) or len(seen) != int(payload.get("file_count") or 0):
            raise ValueError("pilot snapshot verification failed")

    def verify_snapshot(self, snapshot_id: str) -> dict:
        value = str(snapshot_id or "").strip()
        if not SNAPSHOT_ID_RE.fullmatch(value):
            raise ValueError("invalid pilot snapshot id")
        with self._lock:
            root = self.backup_root / value
            manifest = root / "manifest.json"
            if not manifest.is_file():
                raise KeyError(value)
            payload = self._manifest(manifest)
            if payload["id"] != value:
                raise ValueError("pilot snapshot identity mismatch")
            self._verify_directory(root, payload)
            return self._public(payload, verified=True)

    def list_snapshots(self) -> dict:
        rows: list[dict] = []
        with self._lock:
            for root in sorted(self.backup_root.glob("snapshot_*"), reverse=True):
                if not root.is_dir() or not SNAPSHOT_ID_RE.fullmatch(root.name):
                    continue
                manifest = root / "manifest.json"
                try:
                    payload = self._manifest(manifest)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if payload.get("id") == root.name:
                    rows.append(self._public(payload))
        return {
            "schema": "binario.marketing.pilot-data-safety.v1",
            "snapshots": rows,
            "count": len(rows),
            "restore_available": False,
            "credentials_included": False,
        }


__all__ = ["EXCLUDED_DIR_NAMES", "PilotDataSafety", "SNAPSHOT_ID_RE", "SNAPSHOT_SCHEMA"]
