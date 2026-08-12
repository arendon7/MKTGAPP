from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class OverlayRenderSpec:
    input_path: Path
    start: float
    end: float
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    opacity: float = 1.0
    z_index: int = 10
    behind_subject: bool = False


@dataclass(frozen=True)
class AudioRenderSpec:
    input_path: Path
    enabled: bool = True
    offset_seconds: float = 0.0
    gain_db: float = 0.0
    normalize: bool = True
    target_lufs: float = -16.0
    replace_original: bool = True


@dataclass(frozen=True)
class CompositeRenderSpec:
    input_path: Path
    output_path: Path
    width: int
    height: int
    start: float = 0.0
    duration: float | None = None
    overlays: tuple[OverlayRenderSpec, ...] = field(default_factory=tuple)
    audio: AudioRenderSpec | None = None
    video_codec: str | None = None
    audio_codec: str = "aac"
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


def _validate_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("render dimensions must be positive")


def _codec_args(codec: str, audio_codec: str) -> list[str]:
    args = ["-c:v", codec]
    if codec == "h264_videotoolbox":
        args += ["-allow_sw", "1"]
    return args + ["-pix_fmt", "yuv420p", "-c:a", audio_codec, "-movflags", "+faststart"]


def ffmpeg_command(spec: RenderSpec, ffmpeg: str | None = None) -> list[str]:
    binary = resolve_ffmpeg(ffmpeg)
    codec = spec.video_codec or preferred_video_codec(binary)
    _validate_dimensions(spec.width, spec.height)
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
    command += ["-vf", f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2"]
    command += _codec_args(codec, spec.audio_codec)
    if spec.progress:
        command += ["-progress", "pipe:1", "-nostats"]
    command.append(str(spec.output_path))
    return command


def _overlay_filter(index: int, label: str, item: OverlayRenderSpec, render_start: float, render_duration: float | None) -> tuple[str, float, float] | None:
    active_start = max(0.0, item.start - render_start)
    active_end = item.end - render_start
    if render_duration is not None:
        active_end = min(active_end, render_duration)
    if active_end <= 0 or active_end <= active_start:
        return None
    prep = f"[{index}:v]scale=iw*{item.scale:.6f}:ih*{item.scale:.6f},format=rgba,colorchannelmixer=aa={item.opacity:.6f}[{label}]"
    return prep, active_start, active_end


def composite_ffmpeg_command(spec: CompositeRenderSpec, ffmpeg: str | None = None) -> list[str]:
    binary = resolve_ffmpeg(ffmpeg)
    codec = spec.video_codec or preferred_video_codec(binary)
    _validate_dimensions(spec.width, spec.height)
    if spec.start < 0:
        raise ValueError("render start must be >= 0")
    if spec.duration is not None and spec.duration <= 0:
        raise ValueError("render duration must be > 0")

    command = [binary, "-y"]
    if spec.start > 0:
        command += ["-ss", f"{spec.start:.6f}"]
    command += ["-i", str(spec.input_path)]

    overlays = sorted(spec.overlays, key=lambda row: (not row.behind_subject, row.z_index))
    for item in overlays:
        command += ["-i", str(item.input_path)]

    audio_index: int | None = None
    if spec.audio is not None and spec.audio.enabled:
        audio_index = 1 + len(overlays)
        command += ["-i", str(spec.audio.input_path)]

    if spec.duration is not None:
        command += ["-t", f"{spec.duration:.6f}"]

    filters: list[str] = [f"[0:v]scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2[vbase]"]
    current = "vbase"
    used_overlay = False
    for position, item in enumerate(overlays, start=1):
        prepared = _overlay_filter(position, f"ov{position}", item, spec.start, spec.duration)
        if prepared is None:
            continue
        prep, active_start, active_end = prepared
        filters.append(prep)
        output = f"vout{position}"
        filters.append(
            f"[{current}][ov{position}]overlay=x='(main_w-overlay_w)*{item.x:.6f}':y='(main_h-overlay_h)*{item.y:.6f}':enable='between(t,{active_start:.6f},{active_end:.6f})'[{output}]"
        )
        current = output
        used_overlay = True

    audio_label: str | None = None
    if audio_index is not None and spec.audio is not None:
        audio_filters = [f"[{audio_index}:a]aresample=async=1:first_pts=0"]
        if spec.audio.offset_seconds > 0:
            delay_ms = int(round(spec.audio.offset_seconds * 1000))
            audio_filters.append(f"adelay={delay_ms}:all=1")
        elif spec.audio.offset_seconds < 0:
            audio_filters.append(f"atrim=start={abs(spec.audio.offset_seconds):.6f}")
            audio_filters.append("asetpts=PTS-STARTPTS")
        if abs(spec.audio.gain_db) > 1e-9:
            audio_filters.append(f"volume={spec.audio.gain_db:.3f}dB")
        if spec.audio.normalize:
            audio_filters.append(f"loudnorm=I={spec.audio.target_lufs:.1f}:TP=-1.5:LRA=11")
        filters.append(",".join(audio_filters) + "[aext]")
        if spec.audio.replace_original:
            audio_label = "aext"
        else:
            filters.append("[0:a]aresample=async=1:first_pts=0[aorig]")
            filters.append("[aorig][aext]amix=inputs=2:duration=first:dropout_transition=0[aout]")
            audio_label = "aout"

    command += ["-filter_complex", ";".join(filters)]
    command += ["-map", f"[{current}]" if used_overlay else "[vbase]"]
    if audio_label is not None:
        command += ["-map", f"[{audio_label}]"]
    else:
        command += ["-map", "0:a?"]
    command += _codec_args(codec, spec.audio_codec)
    if spec.progress:
        command += ["-progress", "pipe:1", "-nostats"]
    command.append(str(spec.output_path))
    return command


def probe_media(path: Path, ffprobe: str | None = None) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    binary = resolve_ffprobe(ffprobe)
    proc = subprocess.run([binary, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, timeout=30, check=True)
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


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def subtitles_to_srt(subtitles: list[dict], render_start: float, render_end: float) -> str:
    rows: list[str] = []
    sequence = 1
    for item in sorted(subtitles, key=lambda row: (float(row.get("start", 0)), str(row.get("id", "")))):
        start = max(render_start, float(item.get("start", 0)))
        end = min(render_end, float(item.get("end", 0)))
        text = str(item.get("text", "")).strip()
        if end <= start or not text:
            continue
        rows += [str(sequence), f"{_srt_time(start-render_start)} --> {_srt_time(end-render_start)}", text, ""]
        sequence += 1
    return "\n".join(rows)


def media_runtime_status(ffmpeg: str | None = None, ffprobe: str | None = None) -> dict:
    ffmpeg_bin = resolve_ffmpeg(ffmpeg)
    ffprobe_bin = resolve_ffprobe(ffprobe)
    version = subprocess.run([ffmpeg_bin, "-hide_banner", "-version"], capture_output=True, text=True, timeout=10, check=True).stdout.splitlines()[0]
    encoders = available_encoders(ffmpeg_bin)
    return {"ffmpeg": ffmpeg_bin, "ffprobe": ffprobe_bin, "version": version, "h264_videotoolbox": "h264_videotoolbox" in encoders, "preferred_video_codec": "h264_videotoolbox" if "h264_videotoolbox" in encoders else "mpeg4" if "mpeg4" in encoders else None}


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
