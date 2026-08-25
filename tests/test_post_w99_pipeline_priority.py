import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_action_center_app import compose_action_center
from binario_marketing.service_post_w99_pipeline_priority_app import AppRuntime, create_server, enrich_action_center_with_pipeline

ROOT = Path(__file__).resolve().parents[1]


def base_inputs():
    return {"company":{"id":"company-1","name":"Greenatics"},"workdesk":{"queue":[],"product_gaps":[]},"commercial":{"lead_queue":[],"handoffs":[]},"execution":{"campaigns":[]},"results":{"campaigns":[]},"command":{"priorities":[]}}


def pipeline_card(*, opportunity_id="opp-1", code="OVERDUE_NEXT_ACTION", value=1_000_000):
    return {"id":opportunity_id,"title":"Renovación anual","stage":"PROPOSAL","value":value,"currency":"COP","next_action":"Llamar","next_action_at":"2026-08-20T15:00:00+00:00","contact":{"id":"contact-1","name":"Cliente A"},"followup":{"pending_activities":0,"overdue_activities":0,"next_due_at":None},"attention":{"code":code,"label":"Próxima acción vencida","requires_attention":True}}


class PostW99PipelinePriorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.runtime=AppRuntime.create(ROOT,Path(self.tmp.name)/"data"); self.company=self.runtime.create_company({"name":"Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def _empty_action_center(self):
        return compose_action_center(**base_inputs(),generated_at="2026-08-24T19:00:00-05:00")

    def test_overdue_next_action_enters_global_queue_as_deterministic_attention(self):
        payload=enrich_action_center_with_pipeline(payload=self._empty_action_center(),pipeline={"lanes":[{"stage":"PROPOSAL","opportunities":[pipeline_card()]}]},workdesk={"queue":[]},commercial={"handoffs":[]})
        row=next(item for item in payload["queue"] if item["kind"]=="pipeline_overdue_next_action")
        self.assertEqual(row["urgency"],"HIGH"); self.assertEqual(row["action"]["tab"],"pipeline"); self.assertEqual(row["action"]["opportunity_id"],"opp-1"); self.assertIn("No es una predicción",row["reason"]["explanation"]); self.assertTrue(payload["contracts"]["pipeline_attention_is_deterministic"]); self.assertTrue(payload["contracts"]["no_forecast_inference"]); self.assertTrue(payload["contracts"]["no_probability_of_close_inference"])

    def test_duplicate_overdue_followup_is_suppressed_when_workdesk_already_owns_it(self):
        card=pipeline_card(code="OVERDUE_FOLLOWUP"); card["attention"]["label"]="Seguimiento vencido"; workdesk={"queue":[{"kind":"crm_overdue","opportunity_id":"opp-1"}]}
        payload=enrich_action_center_with_pipeline(payload=self._empty_action_center(),pipeline={"lanes":[{"opportunities":[card]}]},workdesk=workdesk,commercial={"handoffs":[]})
        self.assertNotIn("pipeline_overdue_followup",{row["kind"] for row in payload["queue"]}); self.assertEqual(payload["summary"]["pipeline_attention"],0)

    def test_no_followup_is_suppressed_when_commercial_handoff_already_owns_it(self):
        card=pipeline_card(code="NO_FOLLOWUP"); card["next_action"]=None; card["next_action_at"]=None; commercial={"handoffs":[{"handoff_state":"NEEDS_FOLLOWUP","opportunity_id":"opp-1"}]}
        payload=enrich_action_center_with_pipeline(payload=self._empty_action_center(),pipeline={"lanes":[{"opportunities":[card]}]},workdesk={"queue":[]},commercial=commercial)
        self.assertNotIn("pipeline_no_followup",{row["kind"] for row in payload["queue"]})

    def test_opportunity_value_is_context_only_and_never_changes_priority(self):
        low=pipeline_card(opportunity_id="opp-low",value=100_000); high=pipeline_card(opportunity_id="opp-high",value=900_000_000)
        payload=enrich_action_center_with_pipeline(payload=self._empty_action_center(),pipeline={"lanes":[{"opportunities":[high,low]}]},workdesk={"queue":[]},commercial={"handoffs":[]})
        rows=[row for row in payload["queue"] if row["kind"]=="pipeline_overdue_next_action"]
        self.assertEqual({row["rank"] for row in rows},{19}); self.assertEqual({row["urgency"] for row in rows},{"HIGH"}); self.assertTrue(payload["contracts"]["opportunity_value_not_used_as_priority_score"])

    def test_runtime_surfaces_real_no_followup_opportunity_without_provider_side_effects(self):
        contact=self.runtime.create_contact(self.company["id"],{"name":"Cliente Real"}); opportunity=self.runtime.create_opportunity(self.company["id"],{"contact_id":contact["id"],"title":"Propuesta sin seguimiento","stage":"PROPOSAL","value":2500000,"currency":"COP"})
        payload=self.runtime.action_center(self.company["id"]); row=next(item for item in payload["queue"] if item["action"].get("opportunity_id")==opportunity["id"] and item["kind"]=="pipeline_no_followup")
        self.assertEqual(row["source"],"COMMERCIAL"); self.assertEqual(row["action"]["view"],"crm"); self.assertEqual(row["action"]["tab"],"pipeline"); self.assertFalse(payload["safety"]["provider_read_performed"]); self.assertFalse(payload["safety"]["provider_mutation_performed"]); self.assertFalse(payload["safety"]["ai_generation_performed"]); self.assertFalse(payload["safety"]["automatic_execution"])

    def test_http_route_inherits_action_center_endpoint_from_v1_handler(self):
        contact=self.runtime.create_contact(self.company["id"],{"name":"Cliente HTTP"}); self.runtime.create_opportunity(self.company["id"],{"contact_id":contact["id"],"title":"HTTP","stage":"PROPOSAL"}); server=create_server(self.runtime,"127.0.0.1",0); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base+f"/api/companies/{self.company['id']}/action-center",timeout=5) as response: payload=json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"],"binario.marketing.action-center.v1"); self.assertTrue(payload["contracts"]["pipeline_attention_is_deterministic"]); self.assertGreaterEqual(payload["summary"]["pipeline_attention"],1)
        finally: server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_source_and_docs_preserve_release_and_no_forecast_boundary(self):
        source=(ROOT/"src"/"binario_marketing"/"service_post_w99_pipeline_priority_app.py").read_text(); doc=(ROOT/"docs"/"POST_W99_PIPELINE_PRIORITY.md").read_text()
        self.assertIn("service_post_w99_action_center_app as base",source); self.assertNotIn("def do_POST",source); self.assertNotIn("def do_PATCH",source); self.assertNotIn("def do_DELETE",source); self.assertIn("NO se calcula probabilidad de cierre",doc); self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",doc); self.assertIn("dev/post-w99-action-center",doc); self.assertIn("W99",doc)


if __name__=="__main__": unittest.main()
