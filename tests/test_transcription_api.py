import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request,urlopen

from binario_marketing.service import AppRuntime,create_server


ROOT=Path(__file__).resolve().parents[1]
FAKE_FFMPEG=r'''#!__PYTHON__
import pathlib,sys
if '-encoders' in sys.argv:
 print(' V..... mpeg4 fake');raise SystemExit(0)
pathlib.Path(sys.argv[-1]).write_bytes(b'wav')
'''
FAKE_WHISPER=r'''#!__PYTHON__
import json,pathlib,sys
prefix=pathlib.Path(sys.argv[sys.argv.index('-of')+1])
prefix.with_suffix('.json').write_text(json.dumps({"result":{"language":"es"},"transcription":[
 {"start":0,"end":6,"text":"¿Cómo mejorar el contenido?"},
 {"start":6,"end":13,"text":"La clave es entender a la audiencia."},
 {"start":13,"end":20,"text":"Después mide el resultado y ajusta."},
 {"start":20,"end":27,"text":"Cierra con una llamada a la acción."}
]}),encoding='utf-8')
'''


class TranscriptionApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        ffmpeg=root/'ffmpeg';ffmpeg.write_text(FAKE_FFMPEG.replace('__PYTHON__',sys.executable),encoding='utf-8');ffmpeg.chmod(0o755)
        whisper=root/'whisper-cli';whisper.write_text(FAKE_WHISPER.replace('__PYTHON__',sys.executable),encoding='utf-8');whisper.chmod(0o755)
        model=root/'model.bin';model.write_bytes(b'model')
        self.old={key:os.environ.get(key) for key in ('BINARIO_FFMPEG','BINARIO_WHISPER_CLI','BINARIO_WHISPER_MODEL')}
        os.environ['BINARIO_FFMPEG']=str(ffmpeg);os.environ['BINARIO_WHISPER_CLI']=str(whisper);os.environ['BINARIO_WHISPER_MODEL']=str(model)
        self.runtime=AppRuntime.create(ROOT,root/'data');self.server=create_server(self.runtime,'127.0.0.1',0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base=f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown();self.runtime.proxies.shutdown();self.runtime.transcriptions.shutdown();self.runtime.renders.shutdown();self.server.server_close();self.thread.join(timeout=3)
        for key,value in self.old.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        self.tmp.cleanup()

    def json_request(self,method,path,payload=None):
        data=None if payload is None else json.dumps(payload).encode();req=Request(self.base+path,data=data,method=method,headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=5) as response:return response.status,json.loads(response.read())

    def test_video_transcribes_then_drives_clipper(self):
        _,project=self.json_request('POST','/api/projects',{'name':'Auto Clipper'});pid=project['id']
        req=Request(self.base+f'/api/projects/{pid}/assets/upload?filename=long-video.mp4&kind=video',data=b'video-data',method='POST',headers={'Content-Type':'video/mp4'})
        with urlopen(req,timeout=5) as response:asset=json.loads(response.read())
        aid=asset['id']
        status,row=self.json_request('POST',f'/api/projects/{pid}/assets/{aid}/transcription',{'language':'auto'});self.assertEqual(status,202)
        deadline=time.time()+3
        while time.time()<deadline:
            _,row=self.json_request('GET',f'/api/projects/{pid}/assets/{aid}/transcription')
            if row['status'] in {'PASS','FAIL','CANCELLED','INTERRUPTED'}:break
            time.sleep(0.02)
        self.assertEqual(row['status'],'PASS',row.get('error'));self.assertEqual(row['language'],'es');self.assertEqual(row['segments_count'],4)
        _,segments=self.json_request('GET',f'/api/projects/{pid}/assets/{aid}/transcription/segments');self.assertEqual(len(segments),4)
        status,clips=self.json_request('POST',f'/api/projects/{pid}/assets/{aid}/transcription/clips',{'target_count':2,'min_duration':8,'max_duration':20});self.assertEqual(status,200);self.assertEqual(len(clips),2);self.assertLessEqual(clips[0]['end'],clips[1]['start'])
        with urlopen(self.base+f'/api/projects/{pid}/assets/{aid}/transcription/file',timeout=5) as response:
            payload=json.loads(response.read());self.assertEqual(payload['asset_id'],aid);self.assertEqual(len(payload['segments']),4)

    def test_project_detail_exposes_transcription_status(self):
        _,project=self.json_request('POST','/api/projects',{'name':'Status'});pid=project['id']
        req=Request(self.base+f'/api/projects/{pid}/assets/upload?filename=a.mp4&kind=video',data=b'a',method='POST',headers={'Content-Type':'video/mp4'})
        with urlopen(req,timeout=5) as response:asset=json.loads(response.read())
        _,detail=self.json_request('GET',f'/api/projects/{pid}');self.assertIn('transcriptions',detail);self.assertNotIn(asset['id'],detail['transcriptions'])


if __name__=='__main__':unittest.main()
