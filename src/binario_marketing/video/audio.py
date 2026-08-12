from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioSource:
    id: str
    label: str
    intelligibility: float
    noise: float
    clipping: float


@dataclass(frozen=True)
class AudioSyncSample:
    video_time: float
    audio_time: float


def quality_score(source: AudioSource) -> float:
    return source.intelligibility * 2.0 - source.noise - source.clipping * 2.0


def choose_best_audio(sources: list[AudioSource]) -> AudioSource:
    if not sources:
        raise ValueError("at least one audio source is required")
    return max(sources, key=quality_score)


def alignment_plan(samples: list[AudioSyncSample]) -> dict:
    if not samples:
        return {"offset_seconds": 0.0, "drift_ratio": 1.0, "correction_required": False}
    first, last = samples[0], samples[-1]
    offset = first.video_time - first.audio_time
    video_span = last.video_time - first.video_time
    audio_span = last.audio_time - first.audio_time
    drift_ratio = (video_span / audio_span) if audio_span else 1.0
    return {
        "offset_seconds": round(offset, 6),
        "drift_ratio": round(drift_ratio, 9),
        "correction_required": abs(offset) > 0.02 or abs(drift_ratio - 1.0) > 0.0005,
    }


def normalization_plan(source: AudioSource, target_lufs: float = -16.0) -> dict:
    return {
        "source_id": source.id,
        "target_lufs": target_lufs,
        "true_peak_db": -1.5,
        "preserve_sync": True,
        "replace_original_when_rendering": True,
    }
