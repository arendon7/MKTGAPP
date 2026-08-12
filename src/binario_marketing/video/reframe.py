from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class FocusPoint:
    x: float
    y: float

    def __post_init__(self):
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError("focus coordinates must be normalized")


def face_tracker_available() -> bool:
    return importlib.util.find_spec("cv2") is not None


def smart_reframe_plan(source_width: int, source_height: int, aspect_ratio: tuple[int, int], focus: FocusPoint) -> dict:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("invalid source dimensions")
    target_ratio = aspect_ratio[0] / aspect_ratio[1]
    source_ratio = source_width / source_height
    if source_ratio > target_ratio:
        crop_height = source_height
        crop_width = round(crop_height * target_ratio)
    else:
        crop_width = source_width
        crop_height = round(crop_width / target_ratio)
    max_x = source_width - crop_width
    max_y = source_height - crop_height
    x = round(max(0, min(max_x, focus.x * source_width - crop_width / 2)))
    y = round(max(0, min(max_y, focus.y * source_height - crop_height / 2)))
    return {"x": x, "y": y, "width": crop_width, "height": crop_height, "face_tracker_optional": True}


def safe_zones(width: int, height: int) -> dict:
    return {
        "subtitle": {"left": round(width * 0.08), "right": round(width * 0.92), "top": round(height * 0.68), "bottom": round(height * 0.92)},
        "lower_third": {"left": round(width * 0.08), "right": round(width * 0.92), "top": round(height * 0.52), "bottom": round(height * 0.66)},
    }
