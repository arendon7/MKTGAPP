import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from binario_marketing.service_post_w99_navigator_app import AppRuntime, create_server, navigator_search

ROOT=Path(__file__).resolve().parents[1]


class PostW99NavigatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.runtime=AppRuntime.create(ROOT,Path(self.tmp.name)/"data"); self.company=self.runtime.create_company({"name":"Greenatics"}); self.other=self.runtime.create_company({"name":"Otra"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown();self.runtime.transcriptions.shutdown();self.runtime.renders.shutdown();self.tmp.cleanup()

    def _seed(self):
        contact=self.runtime.create_contact(self.company["id"],{"name":"José Álvarez","organization":"Acme Solar","email":"jose@example.com","tags":["VIP"]})
        opp=self.runtime.create_opportunity(self.company["id"],{"contact_id":contact["id"],"title":"Renovación Solar 2027","stage":"PROPOSAL","value":5000000,"currency":"COP","next_action":"Enviar propuesta final"})
        activity=self.runtime.create_activity(self.company["id"],{"contact_id":contact["id"],"opportunity_id":opp["id"],"kind":"CALL","summary":"Llamar por propuesta solar"})
        campaign=self.runtime.create_campaign(self.company["id"],{"name":"Solar Agosto","objective":"LEADS","status":"IN_PROGRESS","channels":["instagram"]})
        lead=self.runtime.intake_lead(self.company["id"],{"connector":"MANUAL","name":"María Prospecto","email":"maria@prospecto.co","organization":"Acme Solar"})
        media=self.runtime.company_media.add_uploaded(self.company["id"],"solar-hero.png","image",io.BytesIO(b"fake-png-bytes"),len(b"fake-png-bytes"))
        return contact,opp,activity,campaign,lead,media

    def test_accent_insensitive_contact_search_and_exact_navigation(self):
        contact,*_=self._seed(); payload=navigator_search(self.runtime,self.company["id"],"jose alv"); row=next(item for item in payload["results"] if item["entity_id"]==contact["id"])
        self.assertEqual(row["kind"],"CONTACT");self.assertEqual(row["action"]["tab"],"contacts");self.assertEqual(row["action"]["contact_id"],contact["id"]);self.assertTrue(payload["matching_contract"]["accent_insensitive"]);self.assertFalse(payload["matching_contract"]["fuzzy_matching"]);self.assertFalse(payload["matching_contract"]["ai_ranking"])

    def test_cross_module_query_finds_opportunity_campaign_activity_lead_and_media(self):
        contact,opp,activity,campaign,lead,media=self._seed(); solar=navigator_search(self.runtime,self.company["id"],"solar",limit=30); ids={row["entity_id"] for row in solar["results"]}
        self.assertIn(contact["id"],ids);self.assertIn(opp["id"],ids);self.assertIn(activity["id"],ids);self.assertIn(campaign["id"],ids);self.assertIn(media.id,ids)
        prospect=navigator_search(self.runtime,self.company["id"],"prospecto");self.assertIn(lead["id"],{row["entity_id"] for row in prospect["results"]})

    def test_company_scope_prevents_cross_company_results(self):
        self._seed(); other=self.runtime.create_contact(self.other["id"],{"name":"José Álvarez Otro","organization":"Acme Solar"}); payload=navigator_search(self.runtime,self.company["id"],"jose")
        self.assertNotIn(other["id"],{row["entity_id"] for row in payload["results"]});self.assertEqual(payload["company"]["id"],self.company["id"]);self.assertTrue(payload["safety"]["company_scoped"])

    def test_kind_filter_and_limits_are_explicit(self):
        self._seed(); payload=navigator_search(self.runtime,self.company["id"],"solar",limit=2,kind="CAMPAIGN")
        self.assertLessEqual(payload["returned"],2);self.assertTrue(all(row["kind"]=="CAMPAIGN" for row in payload["results"]));self.assertEqual(payload["kind_filter"],"CAMPAIGN")
        with self.assertRaises(ValueError):navigator_search(self.runtime,self.company["id"],"solar",kind="UNKNOWN")

    def test_query_validation_blocks_empty_and_oversized_searches(self):
        with self.assertRaises(ValueError):navigator_search(self.runtime,self.company["id"],"a")
        with self.assertRaises(ValueError):navigator_search(self.runtime,self.company["id"],"x"*121)

    def test_http_endpoint_and_ui_bootstrap_are_get_only(self):
        self._seed();server=create_server(self.runtime,"127.0.0.1",0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base+f"/api/companies/{self.company['id']}/navigator?q=solar",timeout=5) as response:payload=json.loads(response.read().decode())
            self.assertEqual(payload["schema"],"binario.marketing.navigator.v1");self.assertGreater(payload["returned"],0)
            with urlopen(base+"/action-center.js",timeout=5) as response:bootstrap=response.read().decode()
            self.assertIn("navigator.js",bootstrap);self.assertIn("data-post-w99-navigator",bootstrap)
            with urlopen(base+"/navigator.js",timeout=5) as response:ui=response.read().decode()
            self.assertIn("Ctrl+K",ui);self.assertIn("/navigator?q=",ui)
            with self.assertRaises(HTTPError) as error:urlopen(base+f"/api/companies/{self.company['id']}/navigator?q=x",timeout=5)
            self.assertEqual(error.exception.code,400)
        finally:server.shutdown();server.server_close();thread.join(timeout=3)

    def test_frontend_and_service_do_not_add_mutation_or_provider_calls(self):
        ui=(ROOT/"web"/"navigator.js").read_text();service=(ROOT/"src"/"binario_marketing"/"service_post_w99_navigator_app.py").read_text();doc=(ROOT/"docs"/"POST_W99_NAVIGATOR.md").read_text()
        for forbidden in ("method:'POST'","method:'PATCH'","method:'PUT'","method:'DELETE'","setInterval","sendBeacon","fetch('https://"):self.assertNotIn(forbidden,ui)
        self.assertNotIn("def do_POST",service);self.assertNotIn("def do_PATCH",service);self.assertNotIn("def do_DELETE",service);self.assertIn("fuzzy_matching\": False",service);self.assertIn("No modifica `main`",doc);self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",doc)


if __name__=="__main__":unittest.main()
