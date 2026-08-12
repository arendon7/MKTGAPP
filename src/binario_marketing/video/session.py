from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field

from .timeline import Clip, Timeline


ASPECT_RATIOS = {"9:16": (9, 16), "16:9": (16, 9), "1:1": (1, 1), "4:5": (4, 5)}


@dataclass
class Subtitle:
    id: str
    start: float
    end: float
    text: str


@dataclass
class Overlay:
    id: str
    asset_id: str
    start: float
    end: float
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    opacity: float = 1.0
    z_index: int = 10
    behind_subject: bool = False


@dataclass
class AudioTrack:
    asset_id: str
    enabled: bool = True
    offset_seconds: float = 0.0
    gain_db: float = 0.0
    normalize: bool = True
    target_lufs: float = -16.0
    replace_original: bool = True


@dataclass
class EditorState:
    clips: list[dict] = field(default_factory=list)
    subtitles: list[dict] = field(default_factory=list)
    overlays: list[dict] = field(default_factory=list)
    audio_track: dict | None = None
    aspect_ratio: str = "16:9"


class EditorSession:
    def __init__(self):
        self.timeline = Timeline()
        self.subtitles: list[Subtitle] = []
        self.overlays: list[Overlay] = []
        self.audio_track: AudioTrack | None = None
        self.aspect_ratio = "16:9"
        self._undo: list[EditorState] = []
        self._redo: list[EditorState] = []
        self._initial = self.snapshot()

    @staticmethod
    def _state_from_dict(payload: dict) -> EditorState:
        audio = payload.get("audio_track")
        return EditorState(
            clips=copy.deepcopy(payload.get("clips", [])),
            subtitles=copy.deepcopy(payload.get("subtitles", [])),
            overlays=copy.deepcopy(payload.get("overlays", [])),
            audio_track=copy.deepcopy(audio) if isinstance(audio, dict) else None,
            aspect_ratio=str(payload.get("aspect_ratio", "16:9")),
        )

    @classmethod
    def from_export(cls, payload: dict) -> "EditorSession":
        session = cls()
        session._restore(cls._state_from_dict(payload.get("state", {})))
        session._undo = [cls._state_from_dict(row) for row in payload.get("undo", [])]
        session._redo = [cls._state_from_dict(row) for row in payload.get("redo", [])]
        session._initial = cls._state_from_dict(payload.get("initial", {}))
        return session

    def export(self) -> dict:
        return {
            "state": asdict(self.snapshot()),
            "undo": [asdict(item) for item in self._undo],
            "redo": [asdict(item) for item in self._redo],
            "initial": asdict(self._initial),
        }

    def snapshot(self) -> EditorState:
        return EditorState(
            clips=copy.deepcopy(self.timeline.to_dict()),
            subtitles=[asdict(item) for item in self.subtitles],
            overlays=[asdict(item) for item in self.overlays],
            audio_track=asdict(self.audio_track) if self.audio_track is not None else None,
            aspect_ratio=self.aspect_ratio,
        )

    def _checkpoint(self) -> None:
        self._undo.append(self.snapshot())
        self._redo.clear()

    @staticmethod
    def _validate_subtitle(item: Subtitle) -> None:
        if item.start < 0 or item.end <= item.start:
            raise ValueError("invalid subtitle bounds")
        if not item.text.strip():
            raise ValueError("subtitle text is required")

    @staticmethod
    def _validate_overlay(item: Overlay) -> None:
        if item.start < 0 or item.end <= item.start:
            raise ValueError("invalid overlay bounds")
        if not 0 <= item.x <= 1 or not 0 <= item.y <= 1:
            raise ValueError("overlay position must be normalized between 0 and 1")
        if not 0 <= item.opacity <= 1:
            raise ValueError("overlay opacity must be between 0 and 1")
        if item.scale <= 0 or item.scale > 8:
            raise ValueError("overlay scale is outside supported bounds")
        if item.z_index < -1000 or item.z_index > 1000:
            raise ValueError("overlay z-index is outside supported bounds")

    @staticmethod
    def _validate_audio(item: AudioTrack) -> None:
        if not item.asset_id:
            raise ValueError("audio asset is required")
        if item.offset_seconds < -3600 or item.offset_seconds > 3600:
            raise ValueError("audio offset is outside supported bounds")
        if item.gain_db < -60 or item.gain_db > 24:
            raise ValueError("audio gain is outside supported bounds")
        if item.target_lufs < -36 or item.target_lufs > -5:
            raise ValueError("target LUFS is outside supported bounds")

    def _restore(self, state: EditorState) -> None:
        if state.aspect_ratio not in ASPECT_RATIOS:
            raise ValueError(f"invalid aspect ratio: {state.aspect_ratio}")
        self.timeline = Timeline([Clip(**item) for item in copy.deepcopy(state.clips)])
        self.subtitles = [Subtitle(**item) for item in copy.deepcopy(state.subtitles)]
        self.overlays = [Overlay(**item) for item in copy.deepcopy(state.overlays)]
        self.audio_track = AudioTrack(**copy.deepcopy(state.audio_track)) if state.audio_track else None
        for item in self.subtitles:
            self._validate_subtitle(item)
        for item in self.overlays:
            self._validate_overlay(item)
        if self.audio_track is not None:
            self._validate_audio(self.audio_track)
        self.aspect_ratio = state.aspect_ratio

    def add_clip(self, asset_id: str, start: float, end: float, track: int = 0) -> Clip:
        self._checkpoint()
        return self.timeline.add(asset_id, start, end, track)

    def trim(self, clip_id: str, start: float, end: float) -> None:
        clip = next((item for item in self.timeline.clips if item.id == clip_id), None)
        if clip is None:
            raise KeyError(clip_id)
        if clip.locked:
            raise ValueError("clip is locked")
        if start < 0 or end <= start:
            raise ValueError("invalid trim")
        self._checkpoint()
        clip.start, clip.end = start, end

    def move(self, clip_id: str, track: int) -> None:
        clip = next((item for item in self.timeline.clips if item.id == clip_id), None)
        if clip is None:
            raise KeyError(clip_id)
        if clip.locked:
            raise ValueError("clip is locked")
        self._checkpoint()
        clip.track = int(track)

    def split(self, clip_id: str, at: float):
        self._checkpoint()
        try:
            return self.timeline.split(clip_id, at)
        except Exception:
            self._undo.pop()
            raise

    def lock(self, clip_id: str, value: bool = True) -> None:
        clip = next((item for item in self.timeline.clips if item.id == clip_id), None)
        if clip is None:
            raise KeyError(clip_id)
        self._checkpoint()
        self.timeline.lock(clip_id, value)

    def delete_clip(self, clip_id: str) -> bool:
        self._checkpoint()
        try:
            deleted = self.timeline.delete(clip_id)
        except Exception:
            self._undo.pop()
            raise
        if not deleted:
            self._undo.pop()
        return deleted

    def set_aspect_ratio(self, value: str) -> None:
        if value not in ASPECT_RATIOS:
            raise ValueError(value)
        self._checkpoint()
        self.aspect_ratio = value

    def add_subtitle(self, subtitle: Subtitle) -> None:
        self._validate_subtitle(subtitle)
        if any(item.id == subtitle.id for item in self.subtitles):
            raise ValueError("subtitle id already exists")
        self._checkpoint()
        self.subtitles.append(subtitle)

    def edit_subtitle(self, subtitle_id: str, *, start: float | None = None, end: float | None = None, text: str | None = None) -> None:
        item = next((row for row in self.subtitles if row.id == subtitle_id), None)
        if item is None:
            raise KeyError(subtitle_id)
        updated = Subtitle(item.id, item.start if start is None else float(start), item.end if end is None else float(end), item.text if text is None else str(text))
        self._validate_subtitle(updated)
        self._checkpoint()
        item.start, item.end, item.text = updated.start, updated.end, updated.text

    def delete_subtitle(self, subtitle_id: str) -> bool:
        index = next((i for i, item in enumerate(self.subtitles) if item.id == subtitle_id), None)
        if index is None:
            return False
        self._checkpoint()
        del self.subtitles[index]
        return True

    def add_overlay(self, overlay: Overlay) -> None:
        self._validate_overlay(overlay)
        if any(item.id == overlay.id for item in self.overlays):
            raise ValueError("overlay id already exists")
        self._checkpoint()
        self.overlays.append(overlay)

    def edit_overlay(self, overlay_id: str, **changes) -> None:
        item = next((row for row in self.overlays if row.id == overlay_id), None)
        if item is None:
            raise KeyError(overlay_id)
        payload = asdict(item)
        for key in {"start", "end", "x", "y", "scale", "opacity", "z_index", "behind_subject"}:
            if key in changes and changes[key] is not None:
                payload[key] = changes[key]
        updated = Overlay(**payload)
        self._validate_overlay(updated)
        self._checkpoint()
        for key, value in asdict(updated).items():
            setattr(item, key, value)

    def delete_overlay(self, overlay_id: str) -> bool:
        index = next((i for i, item in enumerate(self.overlays) if item.id == overlay_id), None)
        if index is None:
            return False
        self._checkpoint()
        del self.overlays[index]
        return True

    def set_audio_track(self, track: AudioTrack) -> None:
        self._validate_audio(track)
        self._checkpoint()
        self.audio_track = track

    def clear_audio_track(self) -> bool:
        if self.audio_track is None:
            return False
        self._checkpoint()
        self.audio_track = None
        return True

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self._restore(self._redo.pop())
        return True

    def reset(self) -> None:
        self._checkpoint()
        self._restore(self._initial)
