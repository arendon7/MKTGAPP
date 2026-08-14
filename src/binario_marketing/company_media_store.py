from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import BinaryIO

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now


MEDIA_ID_RE = re.compile(r"^media_[0-9a-f]{24}$")
MEDIA_KINDS = {"image", "video"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
MAX_COMPANY_MEDIA_BYTES = 5 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class CompanyMedia:
    id: str
    company_id: str
    kind: str
    original_name: str
    stored_name: str
    mime_type: str
    bytes: int
    sha256: str
    width: int | None
    height: int | None
    duration: float | None
    created_at: str
    updated_at: str


class CompanyMediaStore:
    """Durable company-scoped media library with app-managed, hash-addressed evidence."""

    def __init__(self, records_root: Path, files_root: Path):
        self.records_root = Path(records_root)
        self.files_root = Path(files_root)
        self.records_root.mkdir(parents=True, exist_ok=True)
        self.files_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _company_id(value: str) -> str:
        company_id = str(value or "").strip()
        if not COMPANY_ID_RE.fullmatch(company_id):
            raise ValueError("invalid company id")
        return company_id

    @staticmethod
    def _media_id(value: str) -> str:
        media_id = str(value or "").strip()
        if not MEDIA_ID_RE.fullmatch(media_id):
            raise ValueError("invalid media id")
        return media_id

    @staticmethod
    def _clean_filename(value: str) -> str:
        name = Path(str(value or "")).name.strip()
        if not name or name in {".", ".."}:
            raise ValueError("filename is required")
        if len(name) > 255:
            raise ValueError("filename is too long")
        return name

    @staticmethod
    def _validate_kind_filename(kind: str, filename: str) -> tuple[str, str]:
        media_kind = str(kind or "").strip().lower()
        if media_kind not in MEDIA_KINDS:
            raise ValueError("company media kind must be image or video")
        suffix = Path(filename).suffix.lower()
        allowed = IMAGE_SUFFIXES if media_kind == "image" else VIDEO_SUFFIXES
        if suffix not in allowed:
            raise ValueError(f"unsupported {media_kind} file type")
        mime_type = mimetypes.guess_type(filename)[0] or ("image/jpeg" if media_kind == "image" else "video/mp4")
        return suffix, mime_type

    def _record_path(self, media_id: str) -> Path:
        return self.records_root / f"{self._media_id(media_id)}.json"

    def _company_files_root(self, company_id: str) -> Path:
        company = self._company_id(company_id)
        root = (self.files_root / company).resolve()
        files_root = self.files_root.resolve()
        if files_root not in root.parents:
            raise ValueError("company media directory escaped managed root")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _load(self, path: Path) -> CompanyMedia:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid company media payload")
        row = CompanyMedia(**payload)
        self._media_id(row.id)
        self._company_id(row.company_id)
        return row

    def get(self, media_id: str) -> CompanyMedia:
        with self._lock:
            path = self._record_path(media_id)
            if not path.is_file():
                raise KeyError(media_id)
            return self._load(path)

    def get_for_company(self, company_id: str, media_id: str) -> CompanyMedia:
        company = self._company_id(company_id)
        row = self.get(media_id)
        if row.company_id != company:
            raise KeyError(media_id)
        return row

    def list(self, company_id: str | None = None) -> list[CompanyMedia]:
        company = self._company_id(company_id) if company_id else None
        with self._lock:
            rows = [self._load(path) for path in self.records_root.glob("media_*.json")]
        if company:
            rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.created_at, row.id), reverse=True)

    def path_for(self, company_id: str, media_id: str) -> Path:
        row = self.get_for_company(company_id, media_id)
        root = self._company_files_root(row.company_id)
        if Path(row.stored_name).name != row.stored_name:
            raise ValueError("invalid stored media name")
        candidate = (root / row.stored_name).resolve()
        if root not in candidate.parents:
            raise ValueError("company media path escaped managed root")
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    def add_uploaded(self, company_id: str, filename: str, kind: str, stream: BinaryIO, length: int) -> CompanyMedia:
        company = self._company_id(company_id)
        name = self._clean_filename(filename)
        suffix, mime_type = self._validate_kind_filename(kind, name)
        if length <= 0:
            raise ValueError("company media upload must not be empty")
        if length > MAX_COMPANY_MEDIA_BYTES:
            raise ValueError("company media upload exceeds 5 GiB limit")

        media_id = f"media_{uuid.uuid4().hex[:24]}"
        stored_name = f"{media_id}{suffix}"
        root = self._company_files_root(company)
        target = (root / stored_name).resolve()
        if root not in target.parents:
            raise ValueError("company media target escaped managed root")
        temporary = target.with_name(f".{stored_name}.part")
        digest = hashlib.sha256()
        remaining = length
        written = 0
        try:
            with temporary.open("xb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("upload body ended before Content-Length")
                    output.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        now = _now()
        row = CompanyMedia(
            id=media_id,
            company_id=company,
            kind=str(kind).strip().lower(),
            original_name=name,
            stored_name=stored_name,
            mime_type=mime_type,
            bytes=written,
            sha256=digest.hexdigest(),
            width=None,
            height=None,
            duration=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._record_path(row.id), asdict(row))
        return row

    def update_probe(self, company_id: str, media_id: str, *, width: int | None, height: int | None, duration: float | None) -> CompanyMedia:
        company = self._company_id(company_id)
        with self._lock:
            current = self.get_for_company(company, media_id)
            clean_width = int(width) if width is not None else None
            clean_height = int(height) if height is not None else None
            clean_duration = float(duration) if duration is not None else None
            if clean_width is not None and clean_width <= 0:
                clean_width = None
            if clean_height is not None and clean_height <= 0:
                clean_height = None
            if clean_duration is not None and clean_duration < 0:
                clean_duration = None
            updated = replace(
                current,
                width=clean_width,
                height=clean_height,
                duration=clean_duration,
                updated_at=_now(),
            )
            write_json_atomic(self._record_path(updated.id), asdict(updated))
            return updated

    def verify_file(self, company_id: str, media_id: str) -> Path:
        row = self.get_for_company(company_id, media_id)
        path = self.path_for(company_id, media_id)
        if path.stat().st_size != row.bytes:
            raise ValueError("company media size no longer matches its managed record")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != row.sha256.lower():
            raise ValueError("company media SHA-256 no longer matches its managed record")
        return path

    def remove(self, company_id: str, media_id: str) -> CompanyMedia:
        company = self._company_id(company_id)
        with self._lock:
            row = self.get_for_company(company, media_id)
            path = self.path_for(company, media_id)
            path.unlink(missing_ok=True)
            self._record_path(media_id).unlink(missing_ok=True)
            company_root = self._company_files_root(company)
            try:
                company_root.rmdir()
            except OSError:
                pass
            return row


__all__ = [
    "CompanyMedia",
    "CompanyMediaStore",
    "IMAGE_SUFFIXES",
    "MAX_COMPANY_MEDIA_BYTES",
    "MEDIA_ID_RE",
    "MEDIA_KINDS",
    "VIDEO_SUFFIXES",
]
