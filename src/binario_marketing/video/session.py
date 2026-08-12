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
class EditorState:
    clips: list[dict] = field(default_factory=list)
    subtitles: list[dict] = field(default_factory=list)
    overlays: list[dict] = field(default_factory=list)
    aspect_ratio: str = "16:9"


class EditorSession:
    def __init__(self):
        self.timeline = Timeline()
        self.subtitles: list[Subtitle] = []
        self.overlays: list[Overlay] = []
        self.aspect_ratio = "16:9"
        self._undo: list[EditorState] = []
        self._redo: list[EditorState] = []
        self._initial = self.snapshot()

    def snapshot(self) -> EditorState:
        return EditorState(
            clips=copy.deepcopy(self.timeline.to_dict()),
            subtitles=[asdict(item) for item in self.subtitles],
            overlays=[asdict(item) for item in self.overlays],
            aspect_ratio=self.aspect_ratio,
        )

    def _checkpoint(self) -> None:
        self._undo.append(self.snapshot())
        self._redo.clear()

    def _restore(self, state: EditorState) -> None:
        self.timeline = Timeline([Clip(**item) for item in copy.deepcopy(state.clips)])
        self.subtitles = [Subtitle(**item) for item in copy.deepcopy(state.subtitles)]
        self.overlays = [Overlay(**item) for item in copy.deepcopy(state.overlays)]
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
        clip.track = track

    def split(self, clip_id: str, at: float):
        self._checkpoint()
        return self.timeline.split(clip_id, at)

    def delete_clip(self, clip_id: str) -> bool:
        self._checkpoint()
        deleted = self.timeline.delete(clip_id)
        if not deleted:
            self._undo.pop()
        return deleted

    def set_aspect_ratio(self, value: str) -> None:
        if value not in ASPECT_RATIOS:
            raise ValueError(value)
        self._checkpoint()
        self.aspect_ratio = value

    def add_subtitle(self, subtitle: Subtitle) -> None:
        if subtitle.end <= subtitle.start:
            raise ValueError("invalid subtitle bounds")
        self._checkpoint()
        self.subtitles.append(subtitle)

    def edit_subtitle(self, subtitle_id: str, text: str) -> None:
        item = next((row for row in self.subtitles if row.id == subtitle_id), None)
        if item is None:
            raise KeyError(subtitle_id)
        self._checkpoint()
        item.text = text

    def add_overlay(self, overlay: Overlay) -> None:
        if overlay.end <= overlay.start or not 0 <= overlay.opacity <= 1 or overlay.scale <= 0:
            raise ValueError("invalid overlay")
        self._checkpoint()
        self.overlays.append(overlay)

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
