from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .atomic import write_json_atomic
from .company_media_store import MEDIA_ID_RE
from .company_store import COMPANY_ID_RE
from .social_store import _now

BRIDGE_SCHEMA = "binario.marketing.creative-bridge.v1"
BRIDGE_ID_RE = re.compile(r"^creative_[0-9a-f]{24}$")
_SOURCE_TYPES = {"project_asset", "render"}
_SOURCE_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CreativeBridgeRecord:
    schema: str
    id: str
    company_id: str
    project_id: str
    source_type: str
    source_id: str
    source_sha256: str
    company_media_id: str
    created_at: str


class CreativeBridgeStore:
    """Provenance only; media bytes continue to live in CompanyMediaStore."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _validated(row: CreativeBridgeRecord) -> CreativeBridgeRecord:
        if row.schema != BRIDGE_SCHEMA:
            raise ValueError("invalid creative bridge schema")
        if not BRIDGE_ID_RE.fullmatch(row.id):
            raise ValueError("invalid creative bridge id")
        if not COMPANY_ID_RE.fullmatch(row.company_id):
            raise ValueError("invalid company id")
        if not re.fullmatch(r"^[0-9a-f]{12}$", row.project_id):
            raise ValueError("invalid project id")
        if row.source_type not in _SOURCE_TYPES:
            raise ValueError("invalid creative bridge source type")
        if not _SOURCE_ID_RE.fullmatch(row.source_id):
            raise ValueError("invalid creative bridge source id")
        if not _SHA_RE.fullmatch(row.source_sha256):
            raise ValueError("invalid creative bridge SHA-256")
        if not MEDIA_ID_RE.fullmatch(row.company_media_id):
            raise ValueError("invalid company media id")
        return row

    def _path(self, bridge_id: str) -> Path:
        value = str(bridge_id or "").strip()
        if not BRIDGE_ID_RE.fullmatch(value):
            raise ValueError("invalid creative bridge id")
        return self.root / f"{value}.json"

    def _load(self, path: Path) -> CreativeBridgeRecord:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid creative bridge payload")
        return self._validated(CreativeBridgeRecord(**payload))

    def list(self, company_id: str | None = None) -> list[CreativeBridgeRecord]:
        company = str(company_id or "").strip() or None
        if company and not COMPANY_ID_RE.fullmatch(company):
            raise ValueError("invalid company id")
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("creative_*.json")]
        if company:
            rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.created_at, row.id), reverse=True)

    def find_source(self, company_id: str, project_id: str, source_type: str, source_id: str, source_sha256: str) -> CreativeBridgeRecord | None:
        for row in self.list(company_id):
            if (
                row.project_id == project_id
                and row.source_type == source_type
                and row.source_id == source_id
                and row.source_sha256 == source_sha256
            ):
                return row
        return None

    def create(self, *, company_id: str, project_id: str, source_type: str, source_id: str, source_sha256: str, company_media_id: str) -> CreativeBridgeRecord:
        with self._lock:
            existing = self.find_source(company_id, project_id, source_type, source_id, source_sha256)
            if existing is not None:
                return existing
            row = self._validated(CreativeBridgeRecord(
                schema=BRIDGE_SCHEMA,
                id=f"creative_{uuid.uuid4().hex[:24]}",
                company_id=company_id,
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                source_sha256=source_sha256,
                company_media_id=company_media_id,
                created_at=_now(),
            ))
            write_json_atomic(self._path(row.id), asdict(row))
            return row


__all__ = ["BRIDGE_SCHEMA", "CreativeBridgeRecord", "CreativeBridgeStore"]
