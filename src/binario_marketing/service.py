from __future__ import annotations

import json
import mimetypes
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import RECOVERY_STATUS, __version__
from .config import default_paths
from .editor_store import EditorStore
from .hub import discover_apps
from .projects import ProjectStore
from .providers import PROVIDERS, diagnose_provider
from .runtime_center import diagnose
from .video.clipper import TranscriptSegment, select_clips
from .workspace import Workspace


MAX_JSON_BYTES = 2 * 1024 * 1024


@dataclass
class AppRuntime:
    repo_root: Path
    data_root: Path
    projects: ProjectStore
    workspace: Workspace
    editors: EditorStore

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        user_root = (data_root or default_paths().home).expanduser().resolve()
        user_root.mkdir(parents=True, exist_ok=True)
        return cls(
            root,
            user_root,
            ProjectStore(user_root / "Projects"),
            Workspace(user_root / "State" / "workspace"),
            EditorStore(user_root / "State" / "editor"),
        )

    def apps_payload(self) -> list[dict]:
        return [
            {
                "id": app.app_id,
                "name": app.name,
                "service": app.service,
                "entrypoint": app.entrypoint,
                "capabilities": list(app.capabilities),
            }
            for app in discover_apps(self.repo_root)
        ]

    def projects_payload(self) -> list[dict]:
        return [asdict(item) for item in self.projects.list_projects()]

    def project_detail(self, project_id: str) -> dict:
        project = next((item for item in self.projects.list_projects() if item.id == project_id), None)
        if project is None:
            raise KeyError(project_id)
        return {
            "project": asdict(project),
            "assets": [asdict(item) for item in self.projects.assets(project_id)],
            "editor": self.editors.state(project_id),
            "handoffs": [asdict(item) for item in self.workspace.handoffs() if item.project_id == project_id],
        }

    def create_project(self, name: str) -> dict:
        if not name.strip():
            raise ValueError("project name is required")
        project = self.projects.create(name)
        self.workspace.upsert_project(project.id, project.name, "05-editor-video-ia")
        self.workspace.registries.timeline.append("project.created", {"project_id": project.id, "name": project.name})
        return asdict(project)

    def add_asset(self, project_id: str, source_path: str, kind: str) -> dict:
        asset = self.projects.add_asset(project_id, Path(source_path).expanduser(), kind.strip() or "file")
        artifact = self.workspace.registries.record_artifact({
            "project_id": project_id,
            "asset_id": asset.id,
            "name": asset.name,
            "kind": asset.kind,
            "relative_path": asset.relative_path,
        })
        payload = asdict(asset)
        payload["artifact_ref"] = artifact.hash
        return payload

    def remove_asset(self, project_id: str, asset_id: str) -> None:
        editor = self.editors.state(project_id)
        if any(row.get("asset_id") == asset_id for row in editor.get("clips", [])):
            raise ValueError("asset is referenced by the editor timeline")
        if any(row.get("asset_id") == asset_id for row in editor.get("overlays", [])):
            raise ValueError("asset is referenced by an editor overlay")
        if not self.projects.remove_asset(project_id, asset_id):
            raise KeyError(asset_id)
        self.workspace.registries.timeline.append("asset.deleted", {"project_id": project_id, "asset_id": asset_id})

    def editor_action(self, project_id: str, payload: dict) -> dict:
        action = str(payload.get("action", ""))
        if action == "add_clip":
            asset_ids = {item.id for item in self.projects.assets(project_id)}
            if str(payload.get("asset_id", "")) not in asset_ids:
                raise ValueError("asset_id is not part of this project")
        if action == "overlay_add":
            asset_ids = {item.id for item in self.projects.assets(project_id)}
            if str(payload.get("asset_id", "")) not in asset_ids:
                raise ValueError("overlay asset_id is not part of this project")
        state = self.editors.apply(project_id, action, payload)
        self.workspace.registries.timeline.append("editor.action", {"project_id": project_id, "action": action})
        return state

    def create_handoff(self, project_id: str, payload: dict) -> dict:
        to_app = str(payload.get("to_app") or "")
        known_apps = {item["id"] for item in self.apps_payload()}
        if to_app not in known_apps:
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

    def _headers(self, status: int, content_type: str, length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'")
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
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_JSON_BYTES:
            raise ValueError("request body too large")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _segments(self) -> list[str]:
        return [part for part in urlparse(self.path).path.split("/") if part]

    def do_GET(self) -> None:
        try:
            path = urlparse(self.path).path
            if path in {"/", "/index.html", "/app.js", "/styles.css"}:
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
            elif parts == ["api", "timeline"]:
                self._json([entry.__dict__ for entry in self.server.runtime.workspace.registries.timeline.entries()])
            else:
                self._error(HTTPStatus.NOT_FOUND, "not found")
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_POST(self) -> None:
        try:
            payload = self._body()
            parts = self._segments()
            with self.server.mutation_lock:
                if parts == ["api", "projects"]:
                    self._json(self.server.runtime.create_project(str(payload.get("name", ""))), HTTPStatus.CREATED)
                elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "assets":
                    self._json(self.server.runtime.add_asset(parts[2], str(payload["source_path"]), str(payload.get("kind", "file"))), HTTPStatus.CREATED)
                elif len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["editor", "actions"]:
                    self._json(self.server.runtime.editor_action(parts[2], payload))
                elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "handoffs":
                    self._json(self.server.runtime.create_handoff(parts[2], payload), HTTPStatus.CREATED)
                elif parts == ["api", "clipper", "select"]:
                    segments = [TranscriptSegment(float(row["start"]), float(row["end"]), str(row["text"])) for row in payload.get("segments", [])]
                    clips = select_clips(segments, int(payload.get("target_count", 3)), float(payload.get("min_duration", 15)), float(payload.get("max_duration", 75)))
                    self._json([asdict(item) for item in clips])
                else:
                    self._error(HTTPStatus.NOT_FOUND, "not found")
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found or missing field: {exc.args[0]}")
        except FileNotFoundError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"file not found: {exc.filename or exc}")
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
        server.server_close()
