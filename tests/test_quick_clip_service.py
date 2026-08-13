import io
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from binario_marketing.quick_clip_service import save_selection
from binario_marketing.quick_clip_store import QuickClipStore
from binario_marketing.service import AppRuntime
from binario_marketing.transcription_manager import TranscriptRecord


ROOT=Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def selection(asset_id):
    return {
        "asset_id":asset_id,
        "mode":"natural",
        "target_count":2,
        "min_duration":10,
        "max_duration":40,
        "target_duration":None,
        "aspect":"9:16",
        "clips":[
            {"start":0,"end":18,"text":"Idea uno completa.","score":4.0},
            {"start":22,"end":45,"text":"Idea dos completa.","score":3.5},
        ],
    }


class QuickClipServiceTests(unittest.TestCase):
    def _runtime(self, root):
        return AppRuntime.create(ROOT, Path(root))

    def _close(self, runtime):
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_project_detail_restores_selection_and_stale_transcript_clears_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self._runtime(tmp)
            try:
                project=runtime.create_project("Persistent clips")
                data=b"not-a-real-video-but-managed"
                asset=runtime.add_uploaded_asset(project["id"],"source.mp4","video",io.BytesIO(data),len(data))
                transcript=TranscriptRecord(
                    project_id=project["id"],
                    asset_id=asset["id"],
                    source_sha256=asset["sha256"],
                    status="PASS",
                    created_at=now(),
                    updated_at=now(),
                    language="es",
                    requested_language="es",
                    transcript_sha256="b"*64,
                    segments_count=4,
                    duration=60.0,
                )
                runtime.transcriptions._replace(transcript)
                saved=save_selection(runtime,project["id"],selection(asset["id"]))
                self.assertEqual(saved["transcript_sha256"],"b"*64)
                detail=runtime.project_detail(project["id"])
                self.assertEqual(detail["quick_clips"]["asset_id"],asset["id"])
                self.assertEqual(len(detail["quick_clips"]["clips"]),2)
            finally:
                self._close(runtime)

            reopened=self._runtime(tmp)
            try:
                detail=reopened.project_detail(project["id"])
                self.assertEqual(detail["quick_clips"]["aspect"],"9:16")
                current=reopened.transcriptions.get(project["id"],asset["id"])
                reopened.transcriptions._replace(replace(current,transcript_sha256="c"*64,updated_at=now()))
                stale=reopened.project_detail(project["id"])
                self.assertIsNone(stale["quick_clips"])
                self.assertIsNone(QuickClipStore(Path(tmp)/"State"/"quick-clips").get(project["id"]))
            finally:
                self._close(reopened)

    def test_save_rejects_clip_beyond_transcript_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self._runtime(tmp)
            try:
                project=runtime.create_project("Bounds")
                data=b"video"
                asset=runtime.add_uploaded_asset(project["id"],"bounds.mp4","video",io.BytesIO(data),len(data))
                runtime.transcriptions._replace(TranscriptRecord(
                    project_id=project["id"],asset_id=asset["id"],source_sha256=asset["sha256"],status="PASS",
                    created_at=now(),updated_at=now(),language="es",requested_language="es",transcript_sha256="d"*64,duration=20.0,
                ))
                bad=selection(asset["id"])
                bad["clips"]=[{"start":0,"end":30,"text":"Fuera del transcript"}]
                with self.assertRaises(ValueError):
                    save_selection(runtime,project["id"],bad)
            finally:
                self._close(runtime)


if __name__=="__main__":unittest.main()
