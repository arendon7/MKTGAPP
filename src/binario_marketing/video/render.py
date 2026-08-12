from __future__ import annotations

import json
import os
import shutil
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
    video_codec: str | None = None
    audio_codec: str = "aac"
    start: float = 0.0
    duration: float | None = None
    progress: bool = False


def resolve_ffmpeg(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("BINARIO_FFMPEG") or shutil.which("ffmpeg")
    if not candidate:
        raise FileNotFoundError("ffmpeg runtime is unavailable")
    return candidate


def resolve_ffprobe(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("BINARIO_FFPROBE") or shutil.which("ffprobe")
    if not candidate:
        raise FileNotFoundError("ffprobe runtime is unavailable")
    return candidate


def available_encoders(ffmpeg: str | None = None) -> set[str]:
    binary = resolve_ffmpeg(ffmpeg)
    proc = subprocess.run([binary, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15, check=True)
    encoders: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in {"V", "A", "S", "."}:
            encoders.add(parts[1])
    return encoders


def preferred_video_codec(ffmpeg: str | None = None) -> str:
    encoders = available_encoders(ffmpeg)
    if "h264_videotoolbox" in encoders:
        return "h264_videotoolbox"
    if "mpeg4" in encoders:
        return "mpeg4"
    raise RuntimeError("no supported video encoder is available")


def ffmpeg_command(spec: RenderSpec, ffmpeg: str | None = None) -> list[str]:
    binary = resolve_ffmpeg(ffmpeg)
    codec = spec.video_codec or preferred_video_codec(binary)
    if spec.width <= 0 or spec.height <= 0:
        raise ValueError("render dimensions must be positive")
    if spec.start < 0:
        raise ValueError("render start must be >= 0")
    if spec.duration is not None and spec.duration <= 0:
        raise ValueError("render duration must be > 0")
    command = [binary, "-y"]
    if spec.start > 0:
        command += ["-ss", f"{spec.start:.6f}"]
    command += ["-i", str(spec.input_path)]
    if spec.duration is not None:
        command += ["-t", f"{spec.duration:.6f}"]
    command += [
        "-vf", f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", codec, "-pix_fmt", "yuv420p", "-c:a", spec.audio_codec,
        "-movflags", "+faststart",
    ]
    if spec.progress:
        command += ["-progress", "pipe:1", "-nostats"]
    command.append(str(spec.output_path))
    return command


def probe_media(path: Path, ffprobe: str | None = None) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    binary = resolve_ffprobe(ffprobe)
    proc = subprocess.run(
        [binary, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise ValueError("ffprobe returned invalid JSON")
    return payload


def media_duration(payload: dict) -> float | None:
    values: list[float] = []
    format_duration = payload.get("format", {}).get("duration") if isinstance(payload.get("format"), dict) else None
    if format_duration not in (None, "N/A"):
        try:
            values.append(float(format_duration))
        except (TypeError, ValueError):
            pass
    for stream in payload.get("streams", []) if isinstance(payload.get("streams"), list) else []:
        duration = stream.get("duration") if isinstance(stream, dict) else None
        if duration not in (None, "N/A"):
            try:
                values.append(float(duration))
            except (TypeError, ValueError):
                pass
    return max(values) if values else None


def media_runtime_status(ffmpeg: str | None = None, ffprobe: str | None = None) -> dict:
    ffmpeg_bin = resolve_ffmpeg(ffmpeg)
    ffprobe_bin = resolve_ffprobe(ffprobe)
    version = subprocess.run([ffmpeg_bin, "-hide_banner", "-version"], capture_output=True, text=True, timeout=10, check=True).stdout.splitlines()[0]
    encoders = available_encoders(ffmpeg_bin)
    return {
        "ffmpeg": ffmpeg_bin,
        "ffprobe": ffprobe_bin,
        "version": version,
        "h264_videotoolbox": "h264_videotoolbox" in encoders,
        "preferred_video_codec": "h264_videotoolbox" if "h264_videotoolbox" in encoders else "mpeg4" if "mpeg4" in encoders else None,
    }


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
