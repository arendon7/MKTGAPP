import hashlib
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from binario_marketing.service import AppRuntime, create_server
from binario_marketing.transcription_manager import TranscriptRecord


ROOT=Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


class QuickClipApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.runtime=AppRuntime.create(ROOT,Path(self.tmp.name)/"data")
        self.server=create_server(self.runtime,"127.0.0.1",0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
        self.runtime.proxies.shutdown();self.runtime.transcriptions.shutdown();self.runtime.renders.shutdown();self.tmp.cleanup()

    def request(self,method,path,payload=None,content_type="application/json"):
        if payload is None:data=None
        elif content_type=="application/json":data=json.dumps(payload).encode("utf-8")
        else:data=payload
        req=Request(self.base+path,data=data,method=method,headers={"Content-Type":content_type})
        with urlopen(req,timeout=5) as response:
            body=response.read();return response.status,json.loads(body) if body else None

    def test_post_project_detail_and_delete_round_trip(self):
        status,project=self.request("POST","/api/projects",{"name":"Quick clip API"});self.assertEqual(status,201)
        body=b"managed-video"
        status,asset=self.request("POST",f"/api/projects/{project['id']}/assets/upload?filename={quote('demo.mp4')}&kind=video",body,"video/mp4");self.assertEqual(status,201)
        digest=hashlib.sha256(body).hexdigest()
        self.runtime.transcriptions._replace(TranscriptRecord(
            project_id=project["id"],asset_id=asset["id"],source_sha256=digest,status="PASS",created_at=now(),updated_at=now(),
            language="es",requested_language="es",transcript_sha256="e"*64,segments_count=3,duration=45.0,
        ))
        selection={
            "asset_id":asset["id"],"mode":"objective","target_count":1,"min_duration":10,"max_duration":30,"target_duration":20,
            "aspect":"9:16","clips":[{"start":2,"end":22,"text":"Una idea completa.","tone":"educativo","reasons":["unidad narrativa"]}],
            "transcript_sha256":"0"*64,
        }
        status,saved=self.request("POST",f"/api/projects/{project['id']}/quick-clips",selection);self.assertEqual(status,201)
        self.assertEqual(saved["transcript_sha256"],"e"*64)
        _,detail=self.request("GET",f"/api/projects/{project['id']}")
        self.assertEqual(detail["quick_clips"]["clips"][0]["text"],"Una idea completa.")
        status,deleted=self.request("DELETE",f"/api/projects/{project['id']}/quick-clips");self.assertEqual(status,200);self.assertTrue(deleted["deleted"])
        _,detail=self.request("GET",f"/api/projects/{project['id']}");self.assertIsNone(detail["quick_clips"])


if __name__=="__main__":unittest.main()
