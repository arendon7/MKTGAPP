from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .render import AudioRenderSpec, OverlayRenderSpec, preferred_video_codec, resolve_ffmpeg


@dataclass(frozen=True)
class SequenceClipSpec:
    input_path: Path
    start: float
    end: float
    has_audio: bool
    clip_id: str

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class SequenceRenderSpec:
    clips: tuple[SequenceClipSpec, ...]
    output_path: Path
    width: int
    height: int
    fps: int = 30
    overlays: tuple[OverlayRenderSpec, ...] = field(default_factory=tuple)
    audio: AudioRenderSpec | None = None
    video_codec: str | None = None
    audio_codec: str = "aac"
    progress: bool = False

    @property
    def duration(self) -> float:
        return sum(clip.duration for clip in self.clips)


def _codec_args(codec: str, audio_codec: str) -> list[str]:
    args = ["-c:v", codec]
    if codec == "h264_videotoolbox":
        args += ["-allow_sw", "1"]
    return args + ["-pix_fmt", "yuv420p", "-c:a", audio_codec, "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]


def sequence_ffmpeg_command(spec: SequenceRenderSpec, ffmpeg: str | None = None) -> list[str]:
    if not spec.clips:
        raise ValueError("sequence requires at least one clip")
    if spec.width <= 0 or spec.height <= 0:
        raise ValueError("sequence dimensions must be positive")
    if spec.fps < 1 or spec.fps > 120:
        raise ValueError("sequence fps is outside supported bounds")
    for clip in spec.clips:
        if clip.start < 0 or clip.end <= clip.start:
            raise ValueError("sequence contains invalid clip bounds")

    binary = resolve_ffmpeg(ffmpeg)
    codec = spec.video_codec or preferred_video_codec(binary)
    command = [binary, "-y"]

    for clip in spec.clips:
        command += ["-ss", f"{clip.start:.6f}", "-t", f"{clip.duration:.6f}", "-i", str(clip.input_path)]

    overlays = sorted(spec.overlays, key=lambda row: (not row.behind_subject, row.z_index))
    overlay_base_index = len(spec.clips)
    for overlay in overlays:
        command += ["-i", str(overlay.input_path)]

    audio_index: int | None = None
    if spec.audio is not None and spec.audio.enabled:
        audio_index = len(spec.clips) + len(overlays)
        command += ["-i", str(spec.audio.input_path)]

    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, clip in enumerate(spec.clips):
        filters.append(
            f"[{index}:v]fps={spec.fps},scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,"
            f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
        if clip.has_audio:
            filters.append(
                f"[{index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            filters.append(
                f"anullsrc=r=48000:cl=stereo,atrim=duration={clip.duration:.6f},asetpts=PTS-STARTPTS[a{index}]"
            )
        concat_inputs += [f"[v{index}]", f"[a{index}]"]

    filters.append("".join(concat_inputs) + f"concat=n={len(spec.clips)}:v=1:a=1[seqv][seqa]")
    current_video = "seqv"

    total_duration = spec.duration
    for offset, overlay in enumerate(overlays):
        active_start = max(0.0, float(overlay.start))
        active_end = min(total_duration, float(overlay.end))
        if active_end <= active_start:
            continue
        input_index = overlay_base_index + offset
        prepared = f"seqov{offset}"
        output = f"seqv{offset}"
        filters.append(
            f"[{input_index}:v]scale=iw*{overlay.scale:.6f}:ih*{overlay.scale:.6f},format=rgba,"
            f"colorchannelmixer=aa={overlay.opacity:.6f},setpts=PTS-STARTPTS+{active_start:.6f}/TB[{prepared}]"
        )
        filters.append(
            f"[{current_video}][{prepared}]overlay=x='(main_w-overlay_w)*{overlay.x:.6f}':"
            f"y='(main_h-overlay_h)*{overlay.y:.6f}':enable='between(t,{active_start:.6f},{active_end:.6f})'[{output}]"
        )
        current_video = output

    current_audio = "seqa"
    if audio_index is not None and spec.audio is not None:
        audio_filters = [f"[{audio_index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"]
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
        audio_filters.append(f"atrim=duration={total_duration:.6f}")
        filters.append(",".join(audio_filters) + "[seqext]")
        if spec.audio.replace_original:
            current_audio = "seqext"
        else:
            filters.append("[seqa][seqext]amix=inputs=2:duration=first:dropout_transition=0[seqmix]")
            current_audio = "seqmix"

    command += ["-filter_complex", ";".join(filters)]
    command += ["-map", f"[{current_video}]", "-map", f"[{current_audio}]", "-t", f"{total_duration:.6f}"]
    command += _codec_args(codec, spec.audio_codec)
    if spec.progress:
        command += ["-progress", "pipe:1", "-nostats"]
    command.append(str(spec.output_path))
    return command
