from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderSpec:
    input_path: Path
    output_path: Path
    width: int
    height: int
    video_codec: str = "libx264"
    audio_codec: str = "aac"


def ffmpeg_command(spec: RenderSpec, ffmpeg: str = "ffmpeg") -> list[str]:
    return [
        ffmpeg, "-y", "-i", str(spec.input_path),
        "-vf", f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", spec.video_codec, "-c:a", spec.audio_codec, str(spec.output_path),
    ]


class RenderJob:
    def __init__(self, command: list[str]):
        self.command = list(command)
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self.process is not None:
                raise RuntimeError("render already started")
            self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def cancel(self) -> bool:
        with self._lock:
            if self.process is None or self.process.poll() is not None:
                return False
            self.process.terminate()
            return True

    def status(self) -> str:
        with self._lock:
            if self.process is None:
                return "PENDING"
            code = self.process.poll()
            if code is None:
                return "RUNNING"
            return "PASS" if code == 0 else "FAIL"
