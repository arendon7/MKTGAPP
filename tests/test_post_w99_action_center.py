import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_action_center_app import AppRuntime, compose_action_center, create_server

ROOT = Path(__file__).resolve().parents[1]


def fixture_payload(*, failed_publication=True):
    workdesk_queue=[]
    if failed_publication:
        workdesk_queue.append({"priority":0,"kind":"publication_failed","title":"Publicación con error","detail":"Meta rechazó la pieza","view":"calendar","entity_id":"pub-1","due_at":"2026-08-24T12:00:00+00:00"})
    workdesk_queue.append({"priority":2,"kind":"crm_overdue","title":"Seguimiento vencido","detail":"Llamar a Cliente A","view":"crm","tab":"followups","entity_id":"act-1","contact_id":"contact-1","opportunity_id":"opp-1","due_at":"2026-08-23T12:00:00+00:00"})
    return {
        "company":{"id":"company-1","name":"Greenatics"},
        "workdesk":{"queue":workdesk_queue,"product_gaps":[]},
        "commercial":{"lead_queue":[{"priority":0,"lead_id":"lead-1","status":"CONFLICT","display_name":"Ana","connector":"META","received_at":"2026-08-24T10:00:00+00:00","exact_match_count":2,"duplicate_open_lead_count":0}],"handoffs":[{"lead_id":"lead-2","contact_id":"contact-2","contact_name":"Carlos","opportunity_id":None,"opportunity_title":None,"handoff_state":"NEEDS_OPPORTUNITY"}]},
        "execution":{"campaigns":[]},
        "results":{"campaigns":[{"campaign":{"id":"campaign-1","name":"Agosto Leads","status":"IN_PROGRESS"},"evidence":{"summary":"Distribución activa sin snapshot"},"next_action":{"code":"FIX_EXECUTION" if failed_publication else "CAPTURE_RESULTS","label":"Resolver ejecución" if failed_publication else "Capturar resultados","view":"execution" if failed_publication else "analytics"}}]},
        "command":{"priorities":[]},
    }


class PostW99ActionCenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.runtime=AppRuntime.create(ROOT,Path(self.tmp.name)/"data"); self.company=self.runtime.create_company({"name":"Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_global_queue_prioritizes_concrete_blocker_and_deduplicates_campaign_fix(self):
        payload=compose_action_center(**fixture_payload(failed_publication=True),generated_at="2026-08-24T19:00:00-05:00")
        self.assertEqual(payload["schema"],"binario.marketing.action-center.v1"); self.assertEqual(payload["next_action"]["kind"],"publication_failed"); self.assertEqual(payload["next_action"]["urgency"],"CRITICAL"); self.assertNotIn("fix_execution",{row["kind"] for row in payload["queue"]}); self.assertEqual(payload["summary"]["blocking"],2)

    def test_campaign_results_action_is_preserved_without_publication_failure(self):
        payload=compose_action_center(**fixture_payload(failed_publication=False)); campaign=next(row for row in payload["queue"] if row["source"]=="CAMPAIGN")
        self.assertEqual(campaign["kind"],"capture_results"); self.assertEqual(campaign["action"]["view"],"analytics"); self.assertEqual(campaign["action"]["campaign_id"],"campaign-1"); self.assertTrue(campaign["read_only_recommendation"]); self.assertTrue(campaign["requires_human_action"])

    def test_execution_is_safe_fallback_when_results_projection_has_no_campaigns(self):
        payloads=fixture_payload(failed_publication=False); payloads["results"]={"campaigns":[]}; payloads["execution"]={"campaigns":[{"campaign":{"id":"campaign-2","name":"Fallback","status":"IN_PROGRESS"},"next_action":{"code":"CREATE_CREATIVE","label":"Crear creativo","view":"content"}}]}
        payload=compose_action_center(**payloads); row=next(item for item in payload["queue"] if item["action"].get("campaign_id")=="campaign-2")
        self.assertEqual(row["kind"],"create_creative"); self.assertEqual(row["action"]["view"],"content")

    def test_commercial_handoffs_are_actionable_but_never_auto_mutating(self):
        payload=compose_action_center(**fixture_payload(failed_publication=False)); conflict=next(row for row in payload["queue"] if row["kind"]=="lead_conflict"); handoff=next(row for row in payload["queue"] if row["kind"]=="needs_opportunity")
        self.assertTrue(conflict["blocking"]); self.assertEqual(handoff["action"]["contact_id"],"contact-2"); self.assertTrue(payload["contracts"]["human_execution_required"]); self.assertFalse(payload["safety"]["business_mutation_performed"]); self.assertFalse(payload["safety"]["automatic_execution"])

    def test_runtime_empty_company_is_company_scoped_read_only_projection(self):
        payload=self.runtime.action_center(self.company["id"]); self.assertEqual(payload["company"]["id"],self.company["id"]); self.assertEqual(payload["schema"],"binario.marketing.action-center.v1"); self.assertFalse(payload["safety"]["provider_read_performed"]); self.assertFalse(payload["safety"]["provider_mutation_performed"]); self.assertFalse(payload["safety"]["ai_generation_performed"]); self.assertFalse(payload["safety"]["background_polling"])

    def test_http_route_and_bootstrap_are_get_only(self):
        server=create_server(self.runtime,"127.0.0.1",0); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base+"/uat-functional-journey.js",timeout=5) as response: bootstrap=response.read().decode()
            self.assertIn("action-center.js",bootstrap); self.assertIn("data-post-w99-action-center",bootstrap)
            with urlopen(base+"/action-center.js",timeout=5) as response: ui=response.read().decode()
            self.assertIn("Action Center",ui)
            with urlopen(base+f"/api/companies/{self.company['id']}/action-center",timeout=5) as response: payload=json.loads(response.read().decode())
            self.assertEqual(payload["schema"],"binario.marketing.action-center.v1")
        finally: server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_only_navigates_and_service_has_no_mutation_routes(self):
        ui=(ROOT/"web"/"action-center.js").read_text(); service=(ROOT/"src"/"binario_marketing"/"service_post_w99_action_center_app.py").read_text()
        for marker in ("Prioridades","Action Center","/action-center","PRIORIDAD GLOBAL","LOCAL-FIRST"): self.assertIn(marker,ui)
        for forbidden in ("method:'POST'","method:'PATCH'","method:'PUT'","method:'DELETE'","setInterval","sendBeacon","fetch('https://"): self.assertNotIn(forbidden,ui)
        self.assertNotIn("def do_POST",service); self.assertNotIn("def do_PATCH",service); self.assertNotIn("def do_DELETE",service); self.assertIn("service_wave76_app as base",service)

    def test_release_boundary_is_documented(self):
        doc=(ROOT/"docs"/"POST_W99_ACTION_CENTER.md").read_text(); self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",doc); self.assertIn("dev/post-w99-action-center",doc); self.assertIn("NO se crea W100",doc); self.assertIn("NO modifica `main`",doc)


if __name__=="__main__": unittest.main()
