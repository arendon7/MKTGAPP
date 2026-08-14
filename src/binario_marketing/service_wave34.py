from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .company_media_store import CompanyMediaStore, MAX_COMPANY_MEDIA_BYTES, MEDIA_ID_RE
from . import service_wave32 as base
from .video.render import media_duration, probe_media
from .wave34_company_media import Wave34MetaSocialPublisher, company_reel_path, install_wave34_social


class AppRuntime(base.AppRuntime):
    """Wave 34 adds a company media library and local Reel publishing without fake video projects."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.company_media = CompanyMediaStore(
            runtime.data_root / "State" / "company_media" / "records",
            runtime.data_root / "CompanyMedia",
        )
        install_wave34_social(runtime)
        return runtime

    def company_detail(self, company_id: str) -> dict:
        payload = super().company_detail(company_id)
        payload["media"] = self.company_media_payload(company_id)
        return payload

    def ops_dashboard(self, company_id: str | None = None) -> dict:
        payload = super().ops_dashboard(company_id)
        media = self.company_media.list(company_id)
        payload["content"] = {
            "total": len(media),
            "images": sum(1 for row in media if row.kind == "image"),
            "videos": sum(1 for row in media if row.kind == "video"),
        }
        return payload

    def company_media_payload(self, company_id: str) -> list[dict]:
        self.companies.get(company_id)
        return [asdict(row) for row in self.company_media.list(company_id)]

    def company_media_file(self, company_id: str, media_id: str) -> tuple[Path, str, str]:
        self.companies.get(company_id)
        row = self.company_media.get_for_company(company_id, media_id)
        return self.company_media.verify_file(company_id, media_id), row.mime_type, row.original_name

    def upload_company_media(self, company_id: str, filename: str, kind: str, stream, length: int) -> dict:
        company = self.companies.get(company_id)
        row = self.company_media.add_uploaded(company.id, filename, kind, stream, length)
        try:
            row = self.probe_company_media(company.id, row.id)
        except Exception:
            row = asdict(self.company_media.get_for_company(company.id, row.id))
        self.workspace.registries.timeline.append("company.media.created", {
            "company_id": company.id,
            "media_id": row["id"],
            "kind": row["kind"],
            "bytes": row["bytes"],
            "sha256": row["sha256"],
        })
        return row

    def probe_company_media(self, company_id: str, media_id: str) -> dict:
        self.companies.get(company_id)
        row = self.company_media.get_for_company(company_id, media_id)
        path = self.company_media.verify_file(company_id, media_id)
        payload = probe_media(path)
        visual = next(
            (stream for stream in payload.get("streams", []) if str(stream.get("codec_type")) == "video"),
            None,
        )
        width = int(visual.get("width") or 0) if isinstance(visual, dict) else None
        height = int(visual.get("height") or 0) if isinstance(visual, dict) else None
        duration = None
        if row.kind == "video":
            duration = float(media_duration(payload))
        updated = self.company_media.update_probe(
            company_id,
            media_id,
            width=width,
            height=height,
            duration=duration,
        )
        return asdict(updated)

    def remove_company_media(self, company_id: str, media_id: str) -> dict:
        company = self.companies.get(company_id)
        self.company_media.get_for_company(company.id, media_id)
        referenced = [
            row for row in self.social.list(company.id)
            if row.asset_id == media_id and row.status != "CANCELLED"
        ]
        if referenced:
            raise ValueError("company media is referenced by a publication; cancel or retain that publication before deleting the file")
        row = self.company_media.remove(company.id, media_id)
        self.workspace.registries.timeline.append("company.media.deleted", {
            "company_id": company.id,
            "media_id": row.id,
        })
        return asdict(row)

    def create_company_publication(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("publication payload must be an object")
        clean = dict(payload)
        asset_id = str(clean.get("asset_id") or "").strip()
        if not asset_id:
            return super().create_company_publication(company.id, clean)
        if not MEDIA_ID_RE.fullmatch(asset_id):
            raise ValueError("invalid company media id")
        if clean.get("render_id") or clean.get("media_url"):
            raise ValueError("company local media publication cannot also use render_id or media_url")
        media = self.company_media.get_for_company(company.id, asset_id)
        channel = str(clean.get("channel") or "").strip().lower()
        kind = str(clean.get("kind") or "").strip().lower()
        if kind != "reel" or media.kind != "video":
            raise ValueError("direct local company media publishing currently supports video Reels only")
        if channel not in {"facebook_page", "instagram"}:
            raise ValueError("local company Reel supports Facebook or Instagram")
        company_reel_path(self.company_media, type("Intent", (), {
            "asset_id": asset_id,
            "project_id": company.id,
        })(), provider="instagram" if channel == "instagram" else "facebook")

        target_id = str(clean.get("target_id") or "").strip()
        target_name = str(clean.get("target_name") or "").strip()
        if not target_id:
            target_id, default_name = self._default_target(company, channel)
            if target_id:
                clean["target_id"] = target_id
                clean["target_name"] = target_name or default_name or target_id
        if not str(clean.get("target_id") or "").strip():
            raise ValueError("this company has no configured social account for the selected channel")
        clean["asset_id"] = asset_id
        clean["media_url"] = None
        clean["render_id"] = None
        row = self.social.create(company.id, clean)
        self.workspace.registries.timeline.append("company.publication.created", {
            "company_id": company.id,
            "publication_id": row.id,
            "channel": row.channel,
            "kind": row.kind,
            "asset_id": row.asset_id,
            "status": row.status,
            "scheduled_for": row.scheduled_for,
        })
        return asdict(row)

    def publish_company_publication_now(self, company_id: str, publication_id: str) -> dict:
        company, row = self._company_publication(company_id, publication_id)
        if row.status in {"DRAFT", "FAILED"}:
            row = self.social.queue(publication_id)
        if row.status != "QUEUED":
            raise ValueError("publication cannot be published from its current state")
        scheduler = self.social_scheduler
        if scheduler is None:
            raise RuntimeError("social scheduler is unavailable")
        result = asdict(Wave34MetaSocialPublisher(
            self.social,
            scheduler.client_factory(),
            media_store=self.company_media,
        ).publish(publication_id))
        self._record_social_results([result])
        self.workspace.registries.timeline.append("company.publication.attempted", {
            "company_id": company.id,
            "publication_id": publication_id,
            "asset_id": row.asset_id,
            "status": result.get("status"),
            "remote_id": result.get("remote_id"),
        })
        return result


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Company content API extension; every Wave 32 route delegates unchanged."""

    def _wave34_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, FileNotFoundError):
            self._error(HTTPStatus.NOT_FOUND, "managed company media file is missing")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _upload_company_media(self, company_id: str) -> None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required for file uploads")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_COMPANY_MEDIA_BYTES:
            raise ValueError("company media upload must be between 1 byte and 5 GiB")
        query = parse_qs(urlparse(self.path).query)
        filename = (query.get("filename") or [""])[0]
        kind = (query.get("kind") or [""])[0]
        if not filename.strip():
            raise ValueError("filename is required")
        with self.server.mutation_lock:
            payload = self.server.runtime.upload_company_media(company_id, filename, kind, self.rfile, length)
        self._json(payload, HTTPStatus.CREATED)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/company-content.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "media":
                self._json(self.server.runtime.company_media_payload(parts[2]))
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "media" and parts[5] == "file":
                media_path, content_type, _name = self.server.runtime.company_media_file(parts[2], parts[4])
                self._stream_file(media_path, content_type)
                return
        except Exception as exc:
            self._wave34_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["media", "upload"]:
                self._upload_company_media(parts[2])
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "media" and parts[5] == "probe":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.probe_company_media(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave34_error(exc)
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "media":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.remove_company_media(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave34_error(exc)
            return
        super().do_DELETE()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App: {url}")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
