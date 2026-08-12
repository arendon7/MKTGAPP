from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryBeat:
    label: str
    start: float
    end: float
    purpose: str


@dataclass(frozen=True)
class CutVariant:
    name: str
    pace: str
    target_seconds: float | None
    preserve_full_narrative: bool


def validate_story_map(beats: list[StoryBeat]) -> None:
    previous_end = 0.0
    for beat in beats:
        if beat.start < previous_end or beat.end <= beat.start:
            raise ValueError("story beats must be ordered and non-overlapping")
        previous_end = beat.end


def ab_variants(objective_duration: float | None = None) -> tuple[CutVariant, CutVariant]:
    return (
        CutVariant("Equilibrado", "balanced", objective_duration, objective_duration is None),
        CutVariant("Dinámico", "fast", objective_duration, objective_duration is None),
    )
