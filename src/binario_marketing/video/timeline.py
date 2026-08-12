from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass
class Clip:
    id: str
    asset_id: str
    start: float
    end: float
    track: int = 0
    locked: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


class Timeline:
    def __init__(self, clips: list[Clip] | None = None):
        self.clips = clips or []

    def add(self, asset_id: str, start: float, end: float, track: int = 0) -> Clip:
        if start < 0 or end <= start:
            raise ValueError("invalid clip bounds")
        clip = Clip(uuid.uuid4().hex[:12], asset_id, start, end, track)
        self.clips.append(clip)
        return clip

    def delete(self, clip_id: str) -> bool:
        clip = next((c for c in self.clips if c.id == clip_id), None)
        if clip is None:
            return False
        if clip.locked:
            raise ValueError("clip is locked")
        self.clips = [c for c in self.clips if c.id != clip_id]
        return True

    def split(self, clip_id: str, at: float) -> tuple[Clip, Clip]:
        clip = next((c for c in self.clips if c.id == clip_id), None)
        if clip is None:
            raise KeyError(clip_id)
        if clip.locked:
            raise ValueError("clip is locked")
        if not clip.start < at < clip.end:
            raise ValueError("split point must be inside clip")
        left = Clip(uuid.uuid4().hex[:12], clip.asset_id, clip.start, at, clip.track)
        right = Clip(uuid.uuid4().hex[:12], clip.asset_id, at, clip.end, clip.track)
        index = self.clips.index(clip)
        self.clips[index:index + 1] = [left, right]
        return left, right

    def lock(self, clip_id: str, value: bool = True) -> None:
        clip = next((c for c in self.clips if c.id == clip_id), None)
        if clip is None:
            raise KeyError(clip_id)
        clip.locked = value

    def reorder(self, clip_id: str, direction: int) -> None:
        if direction not in {-1, 1}:
            raise ValueError("reorder direction must be -1 or 1")
        clip = next((c for c in self.clips if c.id == clip_id), None)
        if clip is None:
            raise KeyError(clip_id)
        if clip.locked:
            raise ValueError("clip is locked")
        same_track = [c for c in self.clips if c.track == clip.track]
        position = same_track.index(clip)
        target_position = position + direction
        if target_position < 0 or target_position >= len(same_track):
            raise ValueError("clip is already at the track boundary")
        target = same_track[target_position]
        left = self.clips.index(clip)
        right = self.clips.index(target)
        self.clips[left], self.clips[right] = self.clips[right], self.clips[left]

    def track(self, track: int = 0) -> list[Clip]:
        return [clip for clip in self.clips if clip.track == int(track)]

    def to_dict(self) -> list[dict]:
        return [asdict(clip) for clip in self.clips]
