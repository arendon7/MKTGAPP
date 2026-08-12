from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioSource:
    id: str
    label: str
    intelligibility: float
    noise: float
    clipping: float


def quality_score(source: AudioSource) -> float:
    return source.intelligibility * 2.0 - source.noise - source.clipping * 2.0


def choose_best_audio(sources: list[AudioSource]) -> AudioSource:
    if not sources:
        raise ValueError("at least one audio source is required")
    return max(sources, key=quality_score)


def normalization_plan(source: AudioSource, target_lufs: float = -16.0) -> dict:
    return {
        "source_id": source.id,
        "target_lufs": target_lufs,
        "true_peak_db": -1.5,
        "preserve_sync": True,
        "replace_original_when_rendering": True,
    }
