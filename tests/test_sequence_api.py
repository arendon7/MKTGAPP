import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT=Path(__file__).resolve().parents[1]
FAKE_FFMPEG=r'''#!__PYTHON__
import pathlib,sys,time
if '-encoders' in sys.argv:
    print(' V..... mpeg4 fake')
    raise SystemExit(0)
print('out_time_us=500000',flush=True)
time.sleep(0.03)
pathlib.Path(sys.argv[-1]).write_bytes(b'http-sequence-master')
print('out_time_us=2000000',flush=True)
print('progress=end',flush=True)
'''
FAKE_FFPROBE=r'''#!__PYTHON__
import json,pathlib,sys
name=pathlib.Path(sys.argv[-1]).name
streams=[{"codec_type":"video","width":640,"height":360}]
if 'audio' in name: streams.append({"codec_type":"audio"})
print(json.dumps({"streams":streams,"format":{"duration":"2.0"}}))
'''


class SequenceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ffmpeg=self.root/'ffmpeg';self.ffmpeg.write_text(FAKE_FFMPEG.replace('__PYTHON__',sys.executable),encoding='utf-8');self.ffmpeg.chmod(0o755)
        self.ffprobe=self.root/'ffprobe';self.ffprobe.write_text(FAKE_FFPROBE.replace('__PYTHON__',sys.executable),encoding='utf-8');self.ffprobe.chmod(0o755)
        self.old_ffmpeg=os.environ.get('BINARIO_FFMPEG');self.old_ffprobe=os.environ.get('BINARIO_FFPROBE')
        os.environ['BINARIO_FFMPEG']=str(self.ffmpeg);os.environ['BINARIO_FFPROBE']=str(self.ffprobe)
        self.runtime=AppRuntime.create(ROOT,self.root/'data')
        self.server=create_server(self.runtime,'127.0.0.1',0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown();self.runtime.proxies.shutdown();self.runtime.renders.shutdown();self.server.server_close();self.thread.join(timeout=3)
        if self.old_ffmpeg is None:os.environ.pop('BINARIO_FFMPEG',None)
        else:os.environ['BINARIO_FFMPEG']=self.old_ffmpeg
        if self.old_ffprobe is None:os.environ.pop('BINARIO_FFPROBE',None)
        else:os.environ['BINARIO_FFPROBE']=self.old_ffprobe
        self.tmp.cleanup()

    def json_request(self,method,path,payload=None):
        data=None if payload is None else json.dumps(payload).encode()
        req=Request(self.base+path,data=data,method=method,headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=5) as response:return response.status,json.loads(response.read())

    def upload(self,project_id,name,body):
        req=Request(self.base+f'/api/projects/{project_id}/assets/upload?filename={name}&kind=video',data=body,method='POST',headers={'Content-Type':'video/mp4'})
        with urlopen(req,timeout=5) as response:return json.loads(response.read())

    def test_track_zero_can_reorder_and_export_master(self):
        _,project=self.json_request('POST','/api/projects',{'name':'Sequence API'});pid=project['id']
        a=self.upload(pid,'audio-first.mp4',b'a');b=self.upload(pid,'silent-second.mp4',b'b')
        _,state=self.json_request('POST',f'/api/projects/{pid}/editor/actions',{'action':'add_clip','asset_id':a['id'],'start':0,'end':1,'track':0})
        first=state['clips'][0]['id']
        _,state=self.json_request('POST',f'/api/projects/{pid}/editor/actions',{'action':'add_clip','asset_id':b['id'],'start':0,'end':1,'track':0})
        second=state['clips'][1]['id']
        _,state=self.json_request('POST',f'/api/projects/{pid}/editor/actions',{'action':'reorder','clip_id':second,'direction':-1})
        self.assertEqual([row['id'] for row in state['clips']],[second,first])
        status,job=self.json_request('POST',f'/api/projects/{pid}/renders/sequence',{'track':0,'aspect':'16:9','label':'api-master'})
        self.assertEqual(status,202);self.assertEqual(job['kind'],'sequence');self.assertEqual(job['clip_ids'],[second,first])
        deadline=time.time()+3
        while time.time()<deadline:
            _,job=self.json_request('GET',f"/api/renders/{job['id']}")
            if job['status'] in {'PASS','FAIL','CANCELLED','INTERRUPTED'}:break
            time.sleep(0.02)
        self.assertEqual(job['status'],'PASS',job.get('error'));self.assertEqual(job['end'],2.0)
        with urlopen(self.base+f"/api/renders/{job['id']}/file",timeout=5) as response:
            self.assertEqual(response.read(),b'http-sequence-master')


if __name__=='__main__':unittest.main()
