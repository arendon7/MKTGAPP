import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from binario_marketing.editor_store import EditorStore
from binario_marketing.projects import ProjectStore
from binario_marketing.render_queue import RenderQueue
from binario_marketing.video.sequence import SequenceClipSpec, SequenceRenderSpec, sequence_ffmpeg_command
from binario_marketing.workspace import Workspace


FAKE_FFMPEG = r'''#!__PYTHON__
import pathlib, sys, time
if '-encoders' in sys.argv:
    print(' V..... mpeg4 fake')
    raise SystemExit(0)
out=pathlib.Path(sys.argv[-1])
print('out_time_us=500000', flush=True)
time.sleep(0.03)
out.write_bytes(b'sequence-master')
print('out_time_us=3000000', flush=True)
print('progress=end', flush=True)
'''

FAKE_FFPROBE = r'''#!__PYTHON__
import json, pathlib, sys
name=pathlib.Path(sys.argv[-1]).name
streams=[{"codec_type":"video","width":640,"height":360}]
if 'with-audio' in name:
    streams.append({"codec_type":"audio","sample_rate":"48000"})
print(json.dumps({"streams":streams,"format":{"duration":"4.0"}}))
'''


class SequenceRenderTests(unittest.TestCase):
    def test_timeline_reorder_is_undoable_and_track_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=EditorStore(Path(tmp))
            p='sequence-project'
            state=store.apply(p,'add_clip',{'asset_id':'a','start':0,'end':1,'track':0})
            first=state['clips'][0]['id']
            state=store.apply(p,'add_clip',{'asset_id':'b','start':0,'end':1,'track':0})
            second=state['clips'][1]['id']
            state=store.apply(p,'add_clip',{'asset_id':'overlay-track','start':0,'end':1,'track':1})
            third=state['clips'][2]['id']
            state=store.apply(p,'reorder',{'clip_id':second,'direction':-1})
            self.assertEqual([row['id'] for row in state['clips']], [second,first,third])
            state=store.apply(p,'undo',{})
            self.assertEqual([row['id'] for row in state['clips']], [first,second,third])
            with self.assertRaises(ValueError):
                store.apply(p,'reorder',{'clip_id':first,'direction':-1})

    def test_sequence_command_normalizes_video_and_synthesizes_missing_audio(self):
        spec=SequenceRenderSpec(
            clips=(
                SequenceClipSpec(Path('/managed/a.mp4'),1,2,True,'c1'),
                SequenceClipSpec(Path('/managed/b.mp4'),0,2,False,'c2'),
            ),
            output_path=Path('/managed/master.mp4'),width=1920,height=1080,
            video_codec='mpeg4',progress=True,
        )
        command=sequence_ffmpeg_command(spec,ffmpeg='/usr/local/bin/ffmpeg')
        text=' '.join(command)
        self.assertIn('-ss 1.000000 -t 1.000000 -i /managed/a.mp4',text)
        self.assertIn('fps=30',text)
        self.assertIn('anullsrc=r=48000:cl=stereo,atrim=duration=2.000000',text)
        self.assertIn('concat=n=2:v=1:a=1[seqv][seqa]',text)
        self.assertIn('-t 3.000000',text)
        self.assertIn('-progress pipe:1',text)

    def test_managed_sequence_job_preserves_clip_order_and_artifact_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            projects=ProjectStore(root/'projects')
            workspace=Workspace(root/'workspace')
            project=projects.create('Master')
            src1=root/'with-audio.mp4';src1.write_bytes(b'a')
            src2=root/'silent.mp4';src2.write_bytes(b'b')
            a1=projects.add_asset(project.id,src1,'video')
            a2=projects.add_asset(project.id,src2,'video')
            ffmpeg=root/'fake-ffmpeg';ffmpeg.write_text(FAKE_FFMPEG.replace('__PYTHON__',sys.executable),encoding='utf-8');ffmpeg.chmod(0o755)
            ffprobe=root/'fake-ffprobe';ffprobe.write_text(FAKE_FFPROBE.replace('__PYTHON__',sys.executable),encoding='utf-8');ffprobe.chmod(0o755)
            old=os.environ.get('BINARIO_FFPROBE');os.environ['BINARIO_FFPROBE']=str(ffprobe)
            queue=RenderQueue(root/'renders',projects,workspace,str(ffmpeg),video_codec='mpeg4')
            try:
                clips=[
                    {'id':'clip-b','asset_id':a2.id,'start':0,'end':2,'track':0},
                    {'id':'clip-a','asset_id':a1.id,'start':1,'end':2,'track':0},
                ]
                row=queue.start_sequence(project.id,clips,640,360,'master',composition={'subtitles':[{'id':'s','start':0.2,'end':1.5,'text':'Master subtitle'}]})
                deadline=time.time()+3
                while time.time()<deadline:
                    row=queue.get(row.id)
                    if row.status in {'PASS','FAIL','CANCELLED','INTERRUPTED'}:break
                    time.sleep(0.02)
                self.assertEqual(row.status,'PASS',row.error)
                self.assertEqual(row.kind,'sequence')
                self.assertEqual(row.clip_ids,['clip-b','clip-a'])
                self.assertEqual(row.duration,3.0)
                self.assertEqual(row.source_asset_ids,[a2.id,a1.id])
                self.assertTrue(row.composition_sha256)
                self.assertTrue(row.artifact_ref)
                self.assertTrue(row.subtitle_artifact_ref)
                self.assertEqual(queue.output_path(row.id).read_bytes(),b'sequence-master')
                self.assertIn('Master subtitle',queue.subtitle_path(row.id).read_text(encoding='utf-8'))
                events=[entry.kind for entry in workspace.registries.timeline.entries()]
                self.assertIn('render.sequence_queued',events)
                self.assertIn('render.completed',events)
            finally:
                queue.shutdown()
                if old is None:os.environ.pop('BINARIO_FFPROBE',None)
                else:os.environ['BINARIO_FFPROBE']=old


if __name__=='__main__':
    unittest.main()
