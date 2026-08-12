import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from binario_marketing.projects import ProjectStore
from binario_marketing.transcription_manager import TranscriptionManager
from binario_marketing.video.transcription import SpeechSegment,parse_whisper_json,transcript_sha256,whisper_command
from binario_marketing.workspace import Workspace


FAKE_FFMPEG=r'''#!__PYTHON__
import pathlib,sys,time
time.sleep(0.02)
pathlib.Path(sys.argv[-1]).write_bytes(b'wav-data')
'''
FAKE_WHISPER=r'''#!__PYTHON__
import json,pathlib,sys,time
time.sleep(0.03)
prefix=pathlib.Path(sys.argv[sys.argv.index('-of')+1])
payload={"result":{"language":"es"},"transcription":[
 {"timestamps":{"from":"00:00:00,000","to":"00:00:04,000"},"text":"Cómo mejorar tus campañas"},
 {"offsets":{"from":4000,"to":9000},"text":"La clave es medir el resultado"},
 {"start":9.0,"end":14.0,"text":"Cierra con una llamada a la acción","confidence":0.91}
]}
prefix.with_suffix('.json').write_text(json.dumps(payload),encoding='utf-8')
'''


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.projects=ProjectStore(self.root/'projects');self.workspace=Workspace(self.root/'workspace');self.project=self.projects.create('Transcript')
        source=self.root/'video.mp4';source.write_bytes(b'video-source');self.asset=self.projects.add_asset(self.project.id,source,'video')
        self.ffmpeg=self.root/'ffmpeg';self.ffmpeg.write_text(FAKE_FFMPEG.replace('__PYTHON__',sys.executable),encoding='utf-8');self.ffmpeg.chmod(0o755)
        self.whisper=self.root/'whisper-cli';self.whisper.write_text(FAKE_WHISPER.replace('__PYTHON__',sys.executable),encoding='utf-8');self.whisper.chmod(0o755)
        self.model=self.root/'ggml-tiny.bin';self.model.write_bytes(b'model-v1')
        self.manager=TranscriptionManager(self.root/'state',self.projects,self.workspace,ffmpeg=str(self.ffmpeg),whisper_cli=str(self.whisper),model=str(self.model))

    def tearDown(self):
        self.manager.shutdown();self.tmp.cleanup()

    def wait_terminal(self,timeout=3):
        deadline=time.time()+timeout
        while time.time()<deadline:
            row=self.manager.get(self.project.id,self.asset.id)
            if row and row.status in {'PASS','FAIL','CANCELLED','INTERRUPTED'}:return row
            time.sleep(0.02)
        self.fail('transcription did not finish')

    def test_parser_accepts_whisper_cpp_timestamp_variants(self):
        payload={"result":{"language":"es"},"transcription":[
            {"timestamps":{"from":"00:00:01,250","to":"00:00:02,500"},"text":"uno"},
            {"offsets":{"from":2500,"to":5000},"text":"dos"},
            {"start":5,"end":7.25,"text":"tres"},
        ]}
        language,segments=parse_whisper_json(payload)
        self.assertEqual(language,'es');self.assertEqual([(s.start,s.end,s.text) for s in segments],[(1.25,2.5,'uno'),(2.5,5.0,'dos'),(5.0,7.25,'tres')])

    def test_whisper_command_is_local_and_language_optional(self):
        command=whisper_command(Path('/tmp/a.wav'),Path('/tmp/out'),str(self.whisper),str(self.model),'es')
        self.assertEqual(command[0],str(self.whisper));self.assertIn('-oj',command);self.assertIn('-l',command);self.assertIn('es',command)
        automatic=whisper_command(Path('/tmp/a.wav'),Path('/tmp/out'),str(self.whisper),str(self.model),'auto')
        self.assertNotIn('-l',automatic)

    def test_end_to_end_persists_managed_transcript_and_artifact(self):
        row=self.manager.ensure(self.project.id,self.asset.id,'auto');self.assertIn(row.status,{'PENDING','EXTRACTING_AUDIO','TRANSCRIBING','PASS'})
        row=self.wait_terminal();self.assertEqual(row.status,'PASS',row.error);self.assertEqual(row.language,'es');self.assertEqual(row.segments_count,3);self.assertAlmostEqual(row.duration,14.0)
        path=self.manager.transcript_path(self.project.id,self.asset.id);self.assertEqual(path.parent.name,'transcripts');self.assertTrue(path.is_file())
        segments=self.manager.segments(self.project.id,self.asset.id);self.assertEqual(len(segments),3);self.assertEqual(segments[1]['text'],'La clave es medir el resultado')
        expected=transcript_sha256([SpeechSegment(**segment) for segment in segments]);self.assertEqual(row.transcript_sha256,expected);self.assertTrue(row.artifact_ref);self.assertTrue(self.workspace.registries.verify_all())
        cached=self.manager.ensure(self.project.id,self.asset.id,'auto');self.assertEqual(cached.created_at,row.created_at)
        events=[e.kind for e in self.workspace.registries.timeline.entries()];self.assertIn('transcription.queued',events);self.assertIn('transcription.completed',events)

    def test_physical_source_change_forces_new_transcript(self):
        self.manager.ensure(self.project.id,self.asset.id);first=self.wait_terminal();path=self.projects.asset_path(self.project.id,self.asset.id);path.write_bytes(b'changed-video-source')
        queued=self.manager.ensure(self.project.id,self.asset.id);self.assertNotEqual(queued.source_sha256,first.source_sha256);second=self.wait_terminal();self.assertEqual(second.status,'PASS')

    def test_missing_runtime_fails_closed(self):
        other=TranscriptionManager(self.root/'missing',self.projects,self.workspace,ffmpeg=str(self.ffmpeg),whisper_cli=str(self.root/'missing-whisper'),model=str(self.model))
        row=other.ensure(self.project.id,self.asset.id);self.assertEqual(row.status,'FAIL');self.assertIn('whisper',row.error.lower());other.shutdown()


if __name__=='__main__':unittest.main()
