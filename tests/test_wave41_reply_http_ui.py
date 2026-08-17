import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave41_app import AppRuntime, create_server

ROOT=Path(__file__).resolve().parents[1]


class Wave41ReplyHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.runtime=AppRuntime.create(ROOT,Path(self.tmp.name)/'data')
        self.company=self.runtime.create_company({'name':'Greenatics'}); self.server=create_server(self.runtime,'127.0.0.1',0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start(); self.base=f"http://127.0.0.1:{self.server.server_address[1]}"
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_static_bundle_and_server_payload_allowlist(self):
        with urlopen(self.base+'/inbox-replies.js',timeout=5) as response: self.assertIn('Enviar respuesta',response.read().decode())
        payload={'kind':'facebook_message','interaction_id':'msg-1','text':'Hola','recipient_id':'attacker'}
        request=Request(self.base+f"/api/companies/{self.company['id']}/inbox/reply",data=json.dumps(payload).encode(),method='POST',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as raised: urlopen(request,timeout=5)
        self.assertEqual(raised.exception.code,400)

    def test_path_like_interaction_id_is_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError,'invalid interaction_id'):
            self.runtime.reply_social_inbox(self.company['id'],{'kind':'facebook_message','interaction_id':'../../me','text':'Hola'})

    def test_ui_is_explicit_and_build_uses_wave41(self):
        ui=(ROOT/'web'/'inbox-replies.js').read_text(encoding='utf-8'); loader=(ROOT/'web'/'audiences-wave39-loader.js').read_text(encoding='utf-8'); build=(ROOT/'scripts'/'build_full_mac_app.sh').read_text(encoding='utf-8')
        for required in ('Responder en Messenger','Responder comentario','Enviar respuesta','/inbox/reply',"addEventListener('click'"): self.assertIn(required,ui)
        self.assertIn('/inbox-replies.js',loader); self.assertIn('service_wave41_app import serve',build); self.assertIn('audit_wave41_manual_replies.sh',build)
        for forbidden in ('setInterval(','MutationObserver(','recipient_id','access_token','page_id','instagram_id',"fetch('https://","method:'DELETE'","method:'PATCH'"): self.assertNotIn(forbidden,ui)


if __name__=='__main__': unittest.main()
