import tempfile
import unittest
from pathlib import Path

from binario_marketing.editor_store import EditorStore
from binario_marketing.video.render import (
    AudioRenderSpec,
    CompositeRenderSpec,
    OverlayRenderSpec,
    composite_ffmpeg_command,
    subtitles_to_srt,
)


class EditorProMediaTests(unittest.TestCase):
    def test_overlay_subtitle_and_audio_state_persist_and_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = EditorStore(root)
            project_id = "project-1"
            store.apply(project_id, "overlay_add", {
                "id": "logo-1", "asset_id": "asset-logo", "start": 1, "end": 8,
                "x": 0.8, "y": 0.1, "scale": 0.4, "opacity": 0.75, "z_index": 20,
            })
            store.apply(project_id, "subtitle_add", {"id": "sub-1", "start": 2, "end": 5, "text": "Hola mundo"})
            state = store.apply(project_id, "audio_set", {
                "asset_id": "audio-1", "offset_seconds": 0.12, "gain_db": -2.0,
                "normalize": True, "target_lufs": -16, "replace_original": True,
            })
            self.assertEqual(state["audio_track"]["asset_id"], "audio-1")
            self.assertEqual(len(state["overlays"]), 1)
            self.assertEqual(len(state["subtitles"]), 1)

            restarted = EditorStore(root)
            restored = restarted.state(project_id)
            self.assertEqual(restored["audio_track"]["offset_seconds"], 0.12)
            self.assertEqual(restored["overlays"][0]["opacity"], 0.75)
            self.assertEqual(restored["subtitles"][0]["text"], "Hola mundo")

            undone = restarted.apply(project_id, "undo", {})
            self.assertIsNone(undone["audio_track"])
            redone = restarted.apply(project_id, "redo", {})
            self.assertEqual(redone["audio_track"]["asset_id"], "audio-1")

    def test_edit_and_delete_overlay_and_subtitle(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EditorStore(Path(tmp))
            project_id = "project-2"
            store.apply(project_id, "overlay_add", {"id": "o", "asset_id": "a", "start": 0, "end": 10})
            state = store.apply(project_id, "overlay_edit", {"id": "o", "x": 0.2, "scale": 0.5, "opacity": 0.6})
            self.assertEqual(state["overlays"][0]["x"], 0.2)
            self.assertEqual(state["overlays"][0]["scale"], 0.5)
            store.apply(project_id, "subtitle_add", {"id": "s", "start": 1, "end": 4, "text": "Uno"})
            state = store.apply(project_id, "subtitle_edit", {"id": "s", "start": 1.5, "end": 4.5, "text": "Dos"})
            self.assertEqual(state["subtitles"][0]["text"], "Dos")
            self.assertEqual(state["subtitles"][0]["start"], 1.5)
            self.assertEqual(store.apply(project_id, "overlay_delete", {"id": "o"})["overlays"], [])
            self.assertEqual(store.apply(project_id, "subtitle_delete", {"id": "s"})["subtitles"], [])

    def test_composite_command_maps_overlay_and_normalized_external_audio(self):
        spec = CompositeRenderSpec(
            input_path=Path("/managed/main.mp4"),
            output_path=Path("/managed/out.mp4"),
            width=1080,
            height=1920,
            start=5,
            duration=20,
            overlays=(OverlayRenderSpec(Path("/managed/logo.png"), 7, 15, x=0.8, y=0.1, scale=0.5, opacity=0.7),),
            audio=AudioRenderSpec(Path("/managed/voice.wav"), offset_seconds=0.25, gain_db=-1.5, normalize=True, target_lufs=-16),
            video_codec="h264_videotoolbox",
            progress=True,
        )
        command = composite_ffmpeg_command(spec, ffmpeg="/usr/local/bin/ffmpeg")
        text = " ".join(command)
        self.assertIn("/managed/logo.png", text)
        self.assertIn("/managed/voice.wav", text)
        self.assertIn("overlay=", text)
        self.assertIn("colorchannelmixer=aa=0.700000", text)
        self.assertIn("adelay=250:all=1", text)
        self.assertIn("loudnorm=I=-16.0", text)
        self.assertIn("-allow_sw 1", text)
        self.assertIn("-progress pipe:1", text)

    def test_srt_is_clipped_and_rebased_to_render_range(self):
        srt = subtitles_to_srt([
            {"id": "a", "start": 2, "end": 8, "text": "Antes y dentro"},
            {"id": "b", "start": 9, "end": 12, "text": "Dentro"},
            {"id": "c", "start": 20, "end": 25, "text": "Fuera"},
        ], 5, 15)
        self.assertIn("00:00:00,000 --> 00:00:03,000", srt)
        self.assertIn("00:00:04,000 --> 00:00:07,000", srt)
        self.assertNotIn("Fuera", srt)

    def test_invalid_media_controls_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EditorStore(Path(tmp))
            with self.assertRaises(ValueError):
                store.apply("p", "overlay_add", {"id": "o", "asset_id": "a", "start": 0, "end": 1, "opacity": 1.5})
            with self.assertRaises(ValueError):
                store.apply("p", "audio_set", {"asset_id": "a", "target_lufs": -60})
            with self.assertRaises(ValueError):
                store.apply("p", "subtitle_add", {"id": "s", "start": 1, "end": 1, "text": "x"})


if __name__ == "__main__":
    unittest.main()
