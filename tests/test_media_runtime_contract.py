import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.video.render import RenderSpec, ffmpeg_command, preferred_video_codec


ROOT = Path(__file__).resolve().parents[1]


class MediaRuntimeContractTests(unittest.TestCase):
    def test_ffmpeg_source_is_exactly_pinned(self):
        pin = (ROOT / "scripts/full_mac_media_runtime.env").read_text(encoding="utf-8")
        self.assertIn("FULL_MAC_FFMPEG_VERSION='8.1.2'", pin)
        self.assertRegex(pin, r"FULL_MAC_FFMPEG_TAG_OBJECT_SHA='[0-9a-f]{40}'")
        self.assertRegex(pin, r"FULL_MAC_FFMPEG_COMMIT_SHA='[0-9a-f]{40}'")
        self.assertIn("https://github.com/FFmpeg/FFmpeg.git", pin)

    def test_media_builder_verifies_source_and_rejects_host_linkage(self):
        script = (ROOT / "scripts/build_embedded_ffmpeg.sh").read_text(encoding="utf-8")
        self.assertIn('ACTUAL_COMMIT=', script)
        self.assertIn('FULL_MAC_FFMPEG_COMMIT_SHA', script)
        self.assertIn("--disable-autodetect", script)
        self.assertIn("--enable-videotoolbox", script)
        self.assertIn("--enable-audiotoolbox", script)
        self.assertIn("/opt/homebrew", script)
        self.assertIn("/usr/local", script)
        self.assertNotIn("--enable-gpl", script)
        self.assertNotIn("--enable-nonfree", script)

    def test_otool_header_is_not_misclassified_as_linked_dependency(self):
        builder = (ROOT / "scripts/build_embedded_ffmpeg.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts/audit_full_mac_app.sh").read_text(encoding="utf-8")
        for text in (builder, audit):
            self.assertIn("OTOOL_OUTPUT=", text)
            self.assertIn("LINKED_DEPS=", text)
            self.assertIn("OTOOL_OUTPUT#*$'\\n'", text)
            self.assertIn('<<<"$LINKED_DEPS"', text)

    def test_pipefail_sensitive_checks_use_files_not_early_closing_pipelines(self):
        builder = (ROOT / "scripts/build_embedded_ffmpeg.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts/audit_full_mac_app.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertNotIn("-encoders 2>/dev/null | /usr/bin/grep -q", builder)
        self.assertNotIn("-encoders 2>/dev/null | /usr/bin/grep -q", audit)
        self.assertNotIn("-version | head", workflow)
        self.assertIn('ENCODERS_FILE=', builder)
        self.assertIn('ENCODERS_FILE=', audit)
        self.assertIn("Preserve build diagnostics", workflow)
        self.assertIn("Upload build diagnostics", workflow)

    def test_full_mac_builder_bundles_and_prioritizes_media_runtime(self):
        builder = (ROOT / "scripts/build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("build_embedded_ffmpeg.sh", builder)
        self.assertIn('MEDIA_BIN="$RESOURCES/runtime/media/bin"', builder)
        self.assertIn('BINARIO_FFMPEG="$MEDIA_BIN/ffmpeg"', builder)
        self.assertIn('BINARIO_FFPROBE="$MEDIA_BIN/ffprobe"', builder)
        self.assertIn('export PATH="$MEDIA_BIN:', builder)

    @patch("binario_marketing.video.render.available_encoders", return_value={"mpeg4", "h264_videotoolbox"})
    def test_videotoolbox_is_preferred(self, _encoders):
        self.assertEqual(preferred_video_codec("/embedded/ffmpeg"), "h264_videotoolbox")

    def test_render_command_has_no_libx264_default(self):
        spec = RenderSpec(Path("in.mov"), Path("out.mp4"), 1080, 1920, video_codec="h264_videotoolbox")
        command = ffmpeg_command(spec, "/embedded/ffmpeg")
        self.assertIn("h264_videotoolbox", command)
        self.assertNotIn("libx264", command)
        self.assertIn("+faststart", command)

    def test_videotoolbox_render_allows_apple_software_fallback(self):
        spec = RenderSpec(Path("in.mov"), Path("out.mp4"), 1920, 1080, video_codec="h264_videotoolbox")
        command = ffmpeg_command(spec, "/embedded/ffmpeg")
        codec_index = command.index("h264_videotoolbox")
        allow_index = command.index("-allow_sw")
        self.assertGreater(allow_index, codec_index)
        self.assertEqual(command[allow_index + 1], "1")

    def test_non_videotoolbox_codec_does_not_receive_allow_sw(self):
        spec = RenderSpec(Path("in.mov"), Path("out.mp4"), 1920, 1080, video_codec="mpeg4")
        command = ffmpeg_command(spec, "/embedded/ffmpeg")
        self.assertNotIn("-allow_sw", command)


if __name__ == "__main__":
    unittest.main()
