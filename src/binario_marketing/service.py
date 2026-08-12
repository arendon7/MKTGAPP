from __future__ import annotations

import json
import mimetypes
import platform
import re
import subprocess
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import RECOVERY_STATUS, __version__
from .config import default_paths
from .editor_store import EditorStore
from .hub import discover_apps
from .projects import ProjectStore
from .providers import PROVIDERS, diagnose_provider
from .proxy_manager import ProxyManager
from .render_queue import ACTIVE, RenderQueue
from .runtime_center import diagnose
from .sequence_service import start_sequence_render
from .video.clipper import TranscriptSegment, select_clips
from .video.render import media_duration, probe_media
from .workspace import Workspace


MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_BYTES = 50 * 1024 * 1024 * 1024
STREAM_CHUNK_BYTES = 1024 * 1024 * 1024 // 1024
RENDER_DIMENSIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_byte_range(value: str, size: int) -> tuple[int, int]:
    if size < 0:
        raise ValueError("invalid resource size")
    match = _RANGE_RE.fullmatch(value.strip())
    if not match or "," in value:
        raise ValueError("unsupported Range header")
    first, last = match.groups()
    if not first and not last:
        raise ValueError("empty byte range")
    if size == 0:
        raise ValueError("range is unsatisfiable")
    if not first:
        suffix = int(last)
        if suffix <= 0:
            raise ValueError("invalid suffix range")
        return max(0, size - suffix), size - 1
    start = int(first)
    if start >= size:
        raise ValueError("range is unsatisfiable")
    end = size - 1 if not last else min(int(last), size - 1)
    if end < start:
        raise ValueError("range end precedes start")
    return start, end


@dataclass
class AppRuntime:
    repo_root: Path
    data_root: Path
    projects: ProjectStore
    workspace: Workspace
    editors: EditorStore
    proxies: ProxyManager
    renders: RenderQueue

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        user_root = (data_root or default_paths().home).expanduser().resolve()
        user_root.mkdir(parents=True, exist_ok=True)
        projects = ProjectStore(user_root / "Projects")
        workspace = Workspace(user_root / "State" / "workspace")
        editors = EditorStore(user_root / "State" / "editor")
        proxies = ProxyManager(user_root / "State" / "proxies", projects, workspace)
        renders = RenderQueue(user_root / "State" / "renders", projects, workspace)
        return cls(root, user_root, projects, workspace, editors, proxies, renders)

    def apps_payload(self) -> list[dict]:
        return [{"id": app.app_id, "name": app.name, "service": app.service, "entrypoint": app.entrypoint, "capabilities": list(app.capabilities)} for app in discover_apps(self.repo_root)]

    def projects_payload(self) -> list[dict]:
        return [asdict(item) for item in self.projects.list_projects()]

    def project_detail(self, project_id: str) -> dict:
        project = next((item for item in self.projects.list_projects() if item.id == project_id), None)
        if project is None:
            raise KeyError(project_id)
        project_root = self.projects.path_for(project_id).resolve()
        assets = self.projects.assets(project_id)
        proxies = {}
        for asset in assets:
            record = self.proxies.get(project_id, asset.id)
            if record is not None:
                proxies[asset.id] = asdict(record)
        return {
            "project": asdict(project),
            "paths": {
                "project": str(project_root),
                "assets": str((project_root / "assets").resolve()),
                "exports": str(self.projects.exports_dir(project_id).resolve()),
                "proxies": str(self.projects.proxies_dir(project_id).resolve()),
            },
            "assets": [asdict(item) for item in assets],
            "proxies": proxies,
            "editor": self.editors.state(project_id),
            "renders": [asdict(item) for item in self.renders.list(project_id)],
            "handoffs": [asdict(item) for item in self.workspace.handoffs() if item.project_id == project_id],
        }

    def create_project(self, name: str) -> dict:
        if not name.strip():
            raise ValueError("project name is required")
        project = self.projects.create(name)
        self.workspace.upsert_project(project.id, project.name, "05-editor-video-ia")
        self.workspace.registries.timeline.append("project.created", {"project_id": project.id, "name": project.name})
        return asdict(project)

    def reveal_project(self, project_id: str) -> dict:
        project_root = self.projects.path_for(project_id).resolve()
        if platform.system() != "Darwin":
            raise ValueError("Abrir en Finder sólo está disponible en macOS")
        subprocess.run(["/usr/bin/open", str(project_root)], check=True, timeout=10)
        self.workspace.registries.timeline.append("project.revealed", {"project_id": project_id})
        return {"opened": True, "path": str(project_root)}

    def _record_asset(self, project_id: str, asset) -> dict:
        artifact = self.workspace.registries.record_artifact({
            "project_id": project_id,
            "asset_id": asset.id,
            "name": asset.name,
            "kind": asset.kind,
            "relative_path": asset.relative_path,
            "sha256": asset.sha256,
            "bytes": asset.bytes,
        })
        payload = asdict(asset)
        payload["artifact_ref"] = artifact.hash
        return payload

    def add_asset(self, project_id: str, source_path: str, kind: str) -> dict:
        return self._record_asset(project_id, self.projects.add_asset(project_id, Path(source_path).expanduser(), kind.strip() or "file"))

    def add_uploaded_asset(self, project_id: str, filename: str, kind: str, stream, length: int) -> dict:
        return self._record_asset(project_id, self.projects.add_uploaded_asset(project_id, filename, kind.strip() or "file", stream, length))

    def remove_asset(self, project_id: str, asset_id: str) -> None:
        editor = self.editors.state(project_id)
        if any(row.get("asset_id") == asset_id for row in editor.get("clips", [])):
            raise ValueError("asset is referenced by the editor timeline")
        if any(row.get("asset_id") == asset_id for row in editor.get("overlays", [])):
            raise ValueError("asset is referenced by an editor overlay")
        audio = editor.get("audio_track")
        if isinstance(audio, dict) and audio.get("asset_id") == asset_id:
            raise ValueError("asset is configured as the editor external audio track")
        if self.proxies.active_for_asset(project_id, asset_id):
            raise ValueError("asset is referenced by an active preview proxy job")
        for row in self.renders.list(project_id):
            sources = getattr(row, "source_asset_ids", None) or [row.asset_id]
            if row.status in ACTIVE and asset_id in sources:
                raise ValueError("asset is referenced by an active render job")
        self.proxies.invalidate(project_id, asset_id)
        if not self.projects.remove_asset(project_id, asset_id):
            raise KeyError(asset_id)
        self.workspace.registries.timeline.append("asset.deleted", {"project_id": project_id, "asset_id": asset_id})

    def probe_asset(self, project_id: str, asset_id: str) -> dict:
        payload = probe_media(self.projects.asset_path(project_id, asset_id))
        return {"asset_id": asset_id, "duration": media_duration(payload), "format": payload.get("format", {}), "streams": payload.get("streams", [])}

    def proxy_status(self, project_id: str, asset_id: str) -> dict:
        self.projects.asset(project_id, asset_id)
        row = self.proxies.get(project_id, asset_id)
        return asdict(row) if row is not None else {"project_id": project_id, "asset_id": asset_id, "status": "NONE"}

    def ensure_proxy(self, project_id: str, asset_id: str) -> dict:
        return asdict(self.proxies.ensure(project_id, asset_id))

    def editor_action(self, project_id: str, payload: dict) -> dict:
        action = str(payload.get("action", ""))
        if action in {"add_clip", "overlay_add", "audio_set"}:
            asset = self.projects.asset(project_id, str(payload.get("asset_id", "")))
            if action == "audio_set" and asset.kind != "audio":
                raise ValueError("external audio track must reference an audio asset")
            if action == "overlay_add" and asset.kind not in {"image", "logo", "video"}:
                raise ValueError("overlay must reference an image, logo or video asset")
        state = self.editors.apply(project_id, action, payload)
        self.workspace.registries.timeline.append("editor.action", {"project_id": project_id, "action": action})
        return state

    def start_render(self, project_id: str, payload: dict) -> dict:
        asset_id = str(payload.get("asset_id") or "")
        self.projects.asset(project_id, asset_id)
        editor = self.editors.state(project_id)
        aspect = str(payload.get("aspect") or editor.get("aspect_ratio") or "16:9")
        if aspect not in RENDER_DIMENSIONS:
            raise ValueError(f"unsupported render aspect: {aspect}")
        width, height = RENDER_DIMENSIONS[aspect]
        composition = {
            "overlays": editor.get("overlays", []),
            "subtitles": editor.get("subtitles", []),
            "audio_track": editor.get("audio_track"),
        }
        return asdict(self.renders.start(
            project_id,
            asset_id,
            float(payload.get("start", 0)),
            float(payload["end"]),
            width,
            height,
            str(payload.get("label") or "clip"),
            composition=composition,
        ))

    def create_handoff(self, project_id: str, payload: dict) -> dict:
        to_app = str(payload.get("to_app") or "")
        if to_app not in {item["id"] for item in self.apps_payload()}:
            raise ValueError("handoff destination is not a registered app")
        project = next((item for item in self.workspace.projects() if item.id == project_id), None)
        if project is None:
            raise KeyError(project_id)
        handoff = self.workspace.handoff(
            project_id,
            str(payload.get("from_app") or "05-editor-video-ia"),
            to_app,
            str(payload.get("summary") or ""),
            tuple(payload.get("artifact_refs") or ()),
            tuple(payload.get("evidence_refs") or ()),
        )
        self.workspace.upsert_project(project_id, project.name, handoff.to_app)
        return asdict(handoff)


class MarketingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, runtime: AppRuntime):
        super().__init__(address, handler)
        self.runtime = runtime
        self.mutation_lock = threading.RLock()


class MarketingHandler(BaseHTTPRequestHandler):
    server: MarketingHTTPServer

    def log_message(self, format: str, *args) -> None:
        return

    def _headers(self, status: int, content_type: str, length: int | None = None, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _json(self, payload, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message, "status": int(status)}, status)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_JSON_BYTES:
            raise ValueError("request body too large")
        if length == 0:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _segments(self) -> list[str]:
        return [part for part in urlparse(self.path).path.split("/") if part]

    def _upload(self, project_id: str) -> None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required for file uploads")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_UPLOAD_BYTES:
            raise ValueError("upload exceeds 50 GiB limit")
        query = parse_qs(urlparse(self.path).query)
        filename = (query.get("filename") or [""])[0]
        kind = (query.get("kind") or ["file"])[0]
        if not filename.strip():
            raise ValueError("filename is required")
        with self.server.mutation_lock:
            payload = self.server.runtime.add_uploaded_asset(project_id, filename, kind, self.rfile, length)
        self._json(payload, HTTPStatus.CREATED)

    def _stream_file(self, path: Path, content_type: str, *, attachment: str | None = None) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        extra = {"Accept-Ranges": "bytes"}
        if attachment:
            extra["Content-Disposition"] = f'attachment; filename="{attachment}"'
        range_header = self.headers.get("Range")
        if not range_header:
            self._headers(HTTPStatus.OK, content_type, size, extra)
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(STREAM_CHUNK_BYTES), b""):
                    self.wfile.write(chunk)
            return
        try:
            start, end = parse_byte_range(range_header, size)
        except ValueError:
            extra["Content-Range"] = f"bytes */{size}"
            self._headers(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "application/octet-stream", 0, extra)
            return
        length = end - start + 1
        extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._headers(HTTPStatus.PARTIAL_CONTENT, content_type, length, extra)
        remaining = length
        with path.open("rb") as handle:
            handle.seek(start)
            while remaining:
                chunk = handle.read(min(STREAM_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _asset_file(self, project_id: str, asset_id: str) -> None:
        asset = self.server.runtime.projects.asset(project_id, asset_id)
        path = self.server.runtime.projects.asset_path(project_id, asset_id)
        content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        self._stream_file(path, content_type)

    def _proxy_file(self, project_id: str, asset_id: str) -> None:
        path = self.server.runtime.proxies.file_path(project_id, asset_id)
        self._stream_file(path, "video/mp4")

    def _render_file(self, job_id: str) -> None:
        row = self.server.runtime.renders.get(job_id)
        if row.status != "PASS":
            raise ValueError("render output is not available until the job passes")
        path = self.server.runtime.renders.output_path(job_id)
        self._stream_file(path, "video/mp4", attachment=row.output_name)

    def _subtitle_file(self, job_id: str) -> None:
        row = self.server.runtime.renders.get(job_id)
        if row.status != "PASS":
            raise ValueError("subtitle output is not available until the render passes")
        path = self.server.runtime.renders.subtitle_path(job_id)
        if path is None or not path.is_file():
            raise FileNotFoundError("render has no subtitle sidecar")
        self._stream_file(path, "application/x-subrip; charset=utf-8", attachment=path.name)

    def do_GET(self) -> None:
        try:
            path = urlparse(self.path).path
            if path in {"/", "/index.html", "/app.js", "/pro-media.js", "/styles.css"}:
                self._static(path)
                return
            parts = self._segments()
            if parts == ["api", "health"]:
                self._json({"status": "ok", "version": __version__, "recovery_status": RECOVERY_STATUS, "data_root": str(self.server.runtime.data_root)})
            elif parts == ["api", "apps"]:
                self._json(self.server.runtime.apps_payload())
            elif parts == ["api", "runtime"]:
                self._json([asdict(item) for item in diagnose()])
            elif parts == ["api", "providers"]:
                self._json([diagnose_provider(item.id) for item in PROVIDERS])
            elif parts == ["api", "projects"]:
                self._json(self.server.runtime.projects_payload())
            elif len(parts) == 3 and parts[:2] == ["api", "projects"]:
                self._json(self.server.runtime.project_detail(parts[2]))
            elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "editor":
                self._json(self.server.runtime.editors.state(parts[2]))
            elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "renders":
                self._json([asdict(item) for item in self.server.runtime.renders.list(parts[2])])
            elif len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5] == "probe":
                self._json(self.server.runtime.probe_asset(parts[2], parts[4]))
            elif len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5] == "file":
                self._asset_file(parts[2], parts[4])
            elif len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5] == "proxy":
                self._json(self.server.runtime.proxy_status(parts[2], parts[4]))
            elif len(parts) == 7 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5:] == ["proxy", "file"]:
                self._proxy_file(parts[2], parts[4])
            elif len(parts) == 3 and parts[:2] == ["api", "renders"]:
                self._json(asdict(self.server.runtime.renders.get(parts[2])))
            elif len(parts) == 4 and parts[:2] == ["api", "renders"] and parts[3] == "file":
                self._render_file(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "renders"] and parts[3] == "subtitles":
                self._subtitle_file(parts[2])
            elif parts == ["api", "timeline"]:
                self._json([entry.__dict__ for entry in self.server.runtime.workspace.registries.timeline.entries()])
            else:
                self._error(HTTPStatus.NOT_FOUND, "not found")
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        except FileNotFoundError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"file not found: {exc.filename or exc}")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.CONFLICT if "not available until" in str(exc) else HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_POST(self) -> None:
        try:
            parts = self._segments()
            if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["assets", "upload"]:
                self._upload(parts[2])
                return
            payload = self._body()
            with self.server.mutation_lock:
                if parts == ["api", "projects"]:
                    self._json(self.server.runtime.create_project(str(payload.get("name", ""))), HTTPStatus.CREATED)
                elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "assets":
                    self._json(self.server.runtime.add_asset(parts[2], str(payload["source_path"]), str(payload.get("kind", "file"))), HTTPStatus.CREATED)
                elif len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5] == "proxy":
                    self._json(self.server.runtime.ensure_proxy(parts[2], parts[4]), HTTPStatus.ACCEPTED)
                elif len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["editor", "actions"]:
                    self._json(self.server.runtime.editor_action(parts[2], payload))
                elif len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["renders", "sequence"]:
                    self._json(start_sequence_render(self.server.runtime, parts[2], payload), HTTPStatus.ACCEPTED)
                elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "renders":
                    self._json(self.server.runtime.start_render(parts[2], payload), HTTPStatus.ACCEPTED)
                elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "handoffs":
                    self._json(self.server.runtime.create_handoff(parts[2], payload), HTTPStatus.CREATED)
                elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "reveal":
                    self._json(self.server.runtime.reveal_project(parts[2]))
                elif len(parts) == 4 and parts[:2] == ["api", "renders"] and parts[3] == "cancel":
                    self._json(asdict(self.server.runtime.renders.cancel(parts[2])))
                elif parts == ["api", "clipper", "select"]:
                    segments = [TranscriptSegment(float(row["start"]), float(row["end"]), str(row["text"])) for row in payload.get("segments", [])]
                    self._json([asdict(item) for item in select_clips(segments, int(payload.get("target_count", 3)), float(payload.get("min_duration", 15)), float(payload.get("max_duration", 75)))])
                else:
                    self._error(HTTPStatus.NOT_FOUND, "not found")
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found or missing field: {exc.args[0]}")
        except FileNotFoundError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"file not found: {exc.filename or exc}")
        except subprocess.CalledProcessError as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Finder failed with exit code {exc.returncode}")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_DELETE(self) -> None:
        try:
            parts = self._segments()
            if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "assets":
                with self.server.mutation_lock:
                    self.server.runtime.remove_asset(parts[2], parts[4])
                self._json({"deleted": True, "asset_id": parts[4]})
            else:
                self._error(HTTPStatus.NOT_FOUND, "not found")
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        except ValueError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        name = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
        target = self.server.runtime.repo_root / "web" / name
        if not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "text/javascript"}:
            content_type += "; charset=utf-8"
        self._headers(HTTPStatus.OK, content_type, len(body))
        self.wfile.write(body)


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
        runtime.proxies.shutdown()
        runtime.renders.shutdown()
        server.server_close()
