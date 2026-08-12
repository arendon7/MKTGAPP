from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    available: bool
    location: str | None


DEFAULT_TOOLS = (
    "ffmpeg", "ffprobe", "git", "node", "npm", "yt-dlp",
    "magick", "pandoc", "libreoffice", "code"
)


def diagnose(tools: tuple[str, ...] = DEFAULT_TOOLS) -> list[RuntimeCheck]:
    checks = [RuntimeCheck("python", True, sys.executable)]
    for name in tools:
        location = shutil.which(name)
        checks.append(RuntimeCheck(name, location is not None, location))
    return checks
