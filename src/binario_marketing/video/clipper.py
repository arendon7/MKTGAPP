from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class ClipCandidate:
    start: float
    end: float
    text: str
    score: float

    @property
    def duration(self) -> float:
        return self.end - self.start


HOOK_WORDS = {"cómo", "porque", "por qué", "error", "secreto", "clave", "mejor", "nunca", "evita", "resultado"}


def _score(text: str, duration: float) -> float:
    normalized = text.lower()
    hooks = sum(1 for word in HOOK_WORDS if word in normalized)
    punctuation = normalized.count("?") * 1.5 + normalized.count("!")
    word_count = len(normalized.split())
    density = min(word_count / max(duration, 1.0), 3.0)
    return round(hooks * 2.0 + punctuation + density, 4)


def build_candidates(segments: list[TranscriptSegment], min_duration: float = 15.0, max_duration: float = 75.0) -> list[ClipCandidate]:
    if min_duration <= 0 or max_duration < min_duration:
        raise ValueError("invalid duration range")
    result: list[ClipCandidate] = []
    for start_index in range(len(segments)):
        text_parts: list[str] = []
        start = segments[start_index].start
        for end_index in range(start_index, len(segments)):
            segment = segments[end_index]
            text_parts.append(segment.text.strip())
            duration = segment.end - start
            if duration > max_duration:
                break
            if duration >= min_duration:
                text = " ".join(part for part in text_parts if part)
                result.append(ClipCandidate(start, segment.end, text, _score(text, duration)))
                if text.rstrip().endswith((".", "?", "!")):
                    break
    return result


def select_clips(segments: list[TranscriptSegment], target_count: int, min_duration: float = 15.0, max_duration: float = 75.0) -> list[ClipCandidate]:
    if target_count < 1:
        raise ValueError("target_count must be >= 1")
    ranked = sorted(build_candidates(segments, min_duration, max_duration), key=lambda item: (-item.score, item.start))
    chosen: list[ClipCandidate] = []
    for candidate in ranked:
        overlap = any(max(candidate.start, item.start) < min(candidate.end, item.end) for item in chosen)
        if not overlap:
            chosen.append(candidate)
        if len(chosen) == target_count:
            break
    return sorted(chosen, key=lambda item: item.start)
