from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path

from .pilot_data_safety import PilotDataSafety, SNAPSHOT_ID_RE


RECOVERY_REHEARSAL_SCHEMA = "binario.marketing.pilot-recovery-rehearsal.v1"
_SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class PilotRecoveryRehearsal:
    """Prove a verified pilot snapshot is readable without restoring live data.

    The rehearsal is deliberately narrower than restore authority: it verifies the
    existing snapshot, copies it into a fresh sibling workspace, validates the
    isolated copy, performs structural reads, proves active data did not change,
    and removes the temporary workspace before returning.
    """

    def __init__(self, data_root: Path, pilot_data_safety: PilotDataSafety):
        self.data_root = Path(data_root).expanduser().resolve()
        self.pilot_data_safety = pilot_data_safety
        self.backup_root = pilot_data_safety.backup_root
        self.rehearsal_root = self.data_root.parent / f"{self.data_root.name} Recovery Rehearsal"
        if self.rehearsal_root == self.data_root or self.data_root in self.rehearsal_root.parents:
            raise ValueError("recovery rehearsal root must be outside active application data")
        self._lock = threading.RLock()

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _active_fingerprint(self) -> dict[str, tuple[int, int, str]]:
        inventory = self.pilot_data_safety._scan()
        result: dict[str, tuple[int, int, str]] = {}
        for relative, expected in inventory.items():
            source = self.data_root / Path(relative)
            if source.is_symlink() or not source.is_file():
                raise ValueError("active application data changed during recovery rehearsal")
            before = source.stat()
            if (int(before.st_size), int(before.st_mtime_ns)) != expected:
                raise ValueError("active application data changed during recovery rehearsal")
            digest = self._digest(source)
            after = source.stat()
            if (int(after.st_size), int(after.st_mtime_ns)) != expected:
                raise ValueError("active application data changed during recovery rehearsal")
            result[relative] = (expected[0], expected[1], digest)
        return result

    @staticmethod
    def _validate_manifest_row(row: object, seen: set[str]) -> tuple[str, int, str]:
        if not isinstance(row, dict):
            raise ValueError("invalid pilot snapshot file record")
        relative = str(row.get("path") or "")
        rel = Path(relative)
        if not relative or rel.is_absolute() or ".." in rel.parts or relative in seen:
            raise ValueError("invalid pilot snapshot relative path")
        expected_bytes = int(row.get("bytes") or 0)
        expected_digest = str(row.get("sha256") or "").lower()
        if expected_bytes < 0 or len(expected_digest) != 64:
            raise ValueError("invalid pilot snapshot file record")
        seen.add(relative)
        return relative, expected_bytes, expected_digest

    @staticmethod
    def _copy_verified(source: Path, target: Path, expected_bytes: int, expected_digest: str) -> None:
        if source.is_symlink() or not source.is_file():
            raise ValueError("pilot snapshot changed before isolated recovery rehearsal")
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        written = 0
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        source_fd = os.open(source, flags)
        try:
            with os.fdopen(source_fd, "rb", closefd=True) as src, target.open("xb") as dst:
                source_fd = -1
                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                    dst.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                dst.flush()
                os.fsync(dst.fileno())
        finally:
            if source_fd >= 0:
                os.close(source_fd)
        if written != expected_bytes or digest.hexdigest().lower() != expected_digest:
            raise ValueError("isolated recovery copy verification failed")

    @staticmethod
    def _readability(data_root: Path, relatives: list[str]) -> dict:
        structured = 0
        json_documents = 0
        jsonl_documents = 0
        sqlite_databases = 0
        for relative in relatives:
            target = data_root / Path(relative)
            suffix = target.suffix.casefold()
            try:
                if suffix == ".json":
                    structured += 1
                    json_documents += 1
                    with target.open("r", encoding="utf-8") as handle:
                        json.load(handle)
                elif suffix == ".jsonl":
                    structured += 1
                    with target.open("r", encoding="utf-8") as handle:
                        for line in handle:
                            if line.strip():
                                json.loads(line)
                                jsonl_documents += 1
                elif suffix in _SQLITE_SUFFIXES:
                    structured += 1
                    sqlite_databases += 1
                    connection = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
                    try:
                        rows = connection.execute("PRAGMA quick_check").fetchall()
                    finally:
                        connection.close()
                    if not rows or any(str(row[0]).casefold() != "ok" for row in rows):
                        raise ValueError("sqlite quick check failed")
            except (OSError, UnicodeError, json.JSONDecodeError, sqlite3.Error, ValueError) as exc:
                raise ValueError("isolated recovery data is not structurally readable") from exc
        return {
            "status": "PASS",
            "files_checked": len(relatives),
            "structured_files_checked": structured,
            "json_documents": json_documents,
            "jsonl_documents": jsonl_documents,
            "sqlite_databases": sqlite_databases,
        }

    def rehearse(self, snapshot_id: str) -> dict:
        value = str(snapshot_id or "").strip()
        if not SNAPSHOT_ID_RE.fullmatch(value):
            raise ValueError("invalid pilot snapshot id")
        with self._lock:
            snapshot_root = self.backup_root / value
            # Defense in depth for the known root-link edge case: reject before the
            # inherited verifier can follow a directory symlink.
            if snapshot_root.is_symlink():
                raise ValueError("pilot snapshot root cannot be a symbolic link")
            self.pilot_data_safety.verify_snapshot(value)
            manifest_path = snapshot_root / "manifest.json"
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise KeyError(value)
            payload = self.pilot_data_safety._manifest(manifest_path)
            if payload.get("id") != value:
                raise ValueError("pilot snapshot identity mismatch")

            active_before = self._active_fingerprint()
            root_existed = self.rehearsal_root.exists()
            if root_existed and self.rehearsal_root.is_symlink():
                raise ValueError("recovery rehearsal root must not be a symbolic link")
            if root_existed and not self.rehearsal_root.is_dir():
                raise ValueError("recovery rehearsal root must be a directory")
            self.rehearsal_root.mkdir(parents=True, exist_ok=True)
            if self.rehearsal_root.is_symlink():
                raise ValueError("recovery rehearsal root must not be a symbolic link")

            workspace = Path(tempfile.mkdtemp(prefix="rehearsal_", dir=self.rehearsal_root))
            result: dict | None = None
            operation_error: Exception | None = None
            cleanup_error = False
            try:
                seen: set[str] = set()
                relatives: list[str] = []
                copied_bytes = 0
                for row in payload.get("files") or []:
                    relative, expected_bytes, expected_digest = self._validate_manifest_row(row, seen)
                    source = snapshot_root / "data" / Path(relative)
                    target = workspace / "data" / Path(relative)
                    self._copy_verified(source, target, expected_bytes, expected_digest)
                    relatives.append(relative)
                    copied_bytes += expected_bytes

                if len(relatives) != int(payload.get("file_count") or 0) or copied_bytes != int(payload.get("total_bytes") or 0):
                    raise ValueError("isolated recovery copy inventory mismatch")

                self.pilot_data_safety._verify_directory(workspace, dict(payload))
                readability = self._readability(workspace / "data", relatives)
                result = {
                    "schema": RECOVERY_REHEARSAL_SCHEMA,
                    "snapshot_id": value,
                    "status": "PASS",
                    "verified_source": True,
                    "copied_to_isolated_workspace": True,
                    "isolated_copy_verified": True,
                    "readability": readability,
                    "active_data_unchanged": False,
                    "workspace_cleaned": False,
                    "restore_performed": False,
                    "delete_performed": False,
                    "provider_reads": False,
                    "provider_mutations": False,
                    "workers_started": False,
                }
            except Exception as exc:  # preserve the safe local failure after cleanup/evidence checks
                operation_error = exc
            finally:
                try:
                    shutil.rmtree(workspace)
                    if workspace.exists():
                        cleanup_error = True
                    if not root_existed:
                        try:
                            self.rehearsal_root.rmdir()
                        except OSError:
                            pass
                except OSError:
                    cleanup_error = True

            active_after = self._active_fingerprint()
            if active_before != active_after:
                raise ValueError("active application data changed during recovery rehearsal")
            if cleanup_error:
                raise ValueError("isolated recovery rehearsal cleanup failed")
            if operation_error is not None:
                if isinstance(operation_error, (KeyError, ValueError, OSError)):
                    raise operation_error
                raise ValueError("isolated recovery rehearsal failed") from operation_error
            if result is None:
                raise ValueError("isolated recovery rehearsal failed")
            result["active_data_unchanged"] = True
            result["workspace_cleaned"] = True
            return result


__all__ = ["PilotRecoveryRehearsal", "RECOVERY_REHEARSAL_SCHEMA"]
