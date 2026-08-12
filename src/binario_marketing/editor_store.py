from __future__ import annotations

import re
import threading
from dataclasses import asdict
from pathlib import Path

from .atomic import write_json_atomic
from .video.session import AudioTrack, EditorSession, Overlay, Subtitle


PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class EditorStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._sessions: dict[str, EditorSession] = {}

    def _path(self, project_id: str) -> Path:
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("invalid project id")
        return self.root / f"{project_id}.json"

    def load(self, project_id: str) -> EditorSession:
        with self._lock:
            if project_id in self._sessions:
                return self._sessions[project_id]
            path = self._path(project_id)
            if path.exists():
                import json
                session = EditorSession.from_export(json.loads(path.read_text(encoding="utf-8")))
            else:
                session = EditorSession()
            self._sessions[project_id] = session
            return session

    def save(self, project_id: str) -> None:
        with self._lock:
            session = self.load(project_id)
            write_json_atomic(self._path(project_id), session.export())

    def state(self, project_id: str) -> dict:
        with self._lock:
            return asdict(self.load(project_id).snapshot())

    def apply(self, project_id: str, action: str, payload: dict) -> dict:
        with self._lock:
            session = self.load(project_id)
            if action == "add_clip":
                session.add_clip(str(payload["asset_id"]), float(payload["start"]), float(payload["end"]), int(payload.get("track", 0)))
            elif action == "trim":
                session.trim(str(payload["clip_id"]), float(payload["start"]), float(payload["end"]))
            elif action == "move":
                session.move(str(payload["clip_id"]), int(payload["track"]))
            elif action == "reorder":
                session.reorder_clip(str(payload["clip_id"]), int(payload["direction"]))
            elif action == "split":
                session.split(str(payload["clip_id"]), float(payload["at"]))
            elif action == "lock":
                session.lock(str(payload["clip_id"]), bool(payload.get("value", True)))
            elif action == "delete_clip":
                if not session.delete_clip(str(payload["clip_id"])):
                    raise KeyError(str(payload["clip_id"]))
            elif action == "aspect":
                session.set_aspect_ratio(str(payload["value"]))
            elif action == "subtitle_add":
                session.add_subtitle(Subtitle(str(payload["id"]), float(payload["start"]), float(payload["end"]), str(payload["text"])))
            elif action == "subtitle_edit":
                session.edit_subtitle(
                    str(payload["id"]),
                    start=float(payload["start"]) if "start" in payload else None,
                    end=float(payload["end"]) if "end" in payload else None,
                    text=str(payload["text"]) if "text" in payload else None,
                )
            elif action == "subtitle_delete":
                if not session.delete_subtitle(str(payload["id"])):
                    raise KeyError(str(payload["id"]))
            elif action == "overlay_add":
                session.add_overlay(Overlay(
                    id=str(payload["id"]), asset_id=str(payload["asset_id"]), start=float(payload["start"]), end=float(payload["end"]),
                    x=float(payload.get("x", 0.5)), y=float(payload.get("y", 0.5)), scale=float(payload.get("scale", 1.0)),
                    opacity=float(payload.get("opacity", 1.0)), z_index=int(payload.get("z_index", 10)), behind_subject=bool(payload.get("behind_subject", False)),
                ))
            elif action == "overlay_edit":
                session.edit_overlay(
                    str(payload["id"]),
                    start=float(payload["start"]) if "start" in payload else None,
                    end=float(payload["end"]) if "end" in payload else None,
                    x=float(payload["x"]) if "x" in payload else None,
                    y=float(payload["y"]) if "y" in payload else None,
                    scale=float(payload["scale"]) if "scale" in payload else None,
                    opacity=float(payload["opacity"]) if "opacity" in payload else None,
                    z_index=int(payload["z_index"]) if "z_index" in payload else None,
                    behind_subject=bool(payload["behind_subject"]) if "behind_subject" in payload else None,
                )
            elif action == "overlay_delete":
                if not session.delete_overlay(str(payload["id"])):
                    raise KeyError(str(payload["id"]))
            elif action == "audio_set":
                session.set_audio_track(AudioTrack(
                    asset_id=str(payload["asset_id"]),
                    enabled=bool(payload.get("enabled", True)),
                    offset_seconds=float(payload.get("offset_seconds", 0.0)),
                    gain_db=float(payload.get("gain_db", 0.0)),
                    normalize=bool(payload.get("normalize", True)),
                    target_lufs=float(payload.get("target_lufs", -16.0)),
                    replace_original=bool(payload.get("replace_original", True)),
                ))
            elif action == "audio_clear":
                if not session.clear_audio_track():
                    raise ValueError("no external audio track configured")
            elif action == "undo":
                if not session.undo():
                    raise ValueError("nothing to undo")
            elif action == "redo":
                if not session.redo():
                    raise ValueError("nothing to redo")
            elif action == "reset":
                session.reset()
            else:
                raise ValueError(f"unsupported editor action: {action}")
            self.save(project_id)
            return asdict(session.snapshot())
