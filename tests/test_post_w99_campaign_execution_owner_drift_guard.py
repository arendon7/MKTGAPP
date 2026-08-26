import copy
import unittest
from pathlib import Path

from binario_marketing import service_post_w99_setup_readiness_owner_handoff_app as parent
from binario_marketing.service_post_w99_campaign_execution_owner_drift_guard_app import AppRuntime, annotate_campaign_execution_owner_drift

ROOT = Path(__file__).resolve().parents[1]


def drift_row(source_code, owner_view, *, action_id="action-1", state="NO_TARGET", target_id=None, candidate_count=0, candidates=None, campaign_id="campaign-1"):
    return {"id":action_id,"rank":42,"urgency":"HIGH","source":"CAMPAIGN","kind":source_code.lower(),"title":"Action","detail":"Detail","action":{"label":"Abrir owner","view":owner_view,"campaign_id":campaign_id},"blocking":False,"owner_resolution":{"state":state,"source_code":source_code,"owner_view":owner_view,"target_kind":None,"target_id":target_id,"candidate_count":candidate_count,"candidates":[] if candidates is None else candidates,"reason":"El objeto esperado ya no está presente."}}


def payload(row):
    passive={"id":"passive-calendar","source":"CAMPAIGN","kind":"calendar","actionability":{"state":"NON_REQUIRED_CAMPAIGN_ATTENTION"}}
    return {"schema":"binario.marketing.action-center.v1","queue":[copy.deepcopy(row)],"next_action":copy.deepcopy(row),"focus":{"now":[copy.deepcopy(row)],"next":[],"later":[]},"observations":[copy.deepcopy(passive)],"contracts":{"setup_shadow_deduplication_fail_closed":True,"campaign_passive_attention_uses_exact_source_lineage":True,"passive_campaign_states_excluded_from_today":True}}


class OwnerDriftProjectionTests(unittest.TestCase):
    def test_known_no_target_shapes_are_observed(self):
        rules={"FIX_PUBLICATION":("calendar","PUBLICATION"),"SCHEDULE_OR_PUBLISH":("calendar","PUBLICATION"),"REVIEW_PAID":("pauta","PAID_DRAFT"),"FINISH_CREATIVE":("content","MEDIA"),"PREPARE_DISTRIBUTION":("content","MEDIA")}
        for source_code,(owner_view,expected) in rules.items():
            with self.subTest(source_code=source_code):
                result=annotate_campaign_execution_owner_drift(payload(drift_row(source_code,owner_view)));observed=result["queue"][0]["owner_drift"]
                self.assertEqual(observed["state"],"CANONICAL_TARGET_NOT_PRESENT");self.assertEqual(observed["source_code"],source_code);self.assertEqual(observed["owner_view"],owner_view);self.assertEqual(observed["expected_target_kind"],expected);self.assertFalse(observed["target_selected"]);self.assertFalse(observed["replacement_inferred"]);self.assertTrue(observed["recovery"]["requires_human_review"])
    def test_annotation_preserves_parent_state_and_order(self):
        source=payload(drift_row("REVIEW_PAID","pauta"));original=copy.deepcopy(source);result=annotate_campaign_execution_owner_drift(source);current=result["queue"][0]
        for key in ("rank","urgency","blocking","action","owner_resolution"):self.assertEqual(current[key],original["queue"][0][key])
        self.assertEqual(result["observations"],original["observations"]);self.assertTrue(result["contracts"]["campaign_passive_attention_uses_exact_source_lineage"])
    def test_queue_next_action_and_focus_share_same_observation(self):
        result=annotate_campaign_execution_owner_drift(payload(drift_row("FIX_PUBLICATION","calendar")));drift=result["queue"][0]["owner_drift"]
        self.assertEqual(result["next_action"]["owner_drift"],drift);self.assertEqual(result["focus"]["now"][0]["owner_drift"],drift)
    def test_source_payload_is_not_mutated(self):
        source=payload(drift_row("FINISH_CREATIVE","content"));snapshot=copy.deepcopy(source);annotate_campaign_execution_owner_drift(source);self.assertEqual(source,snapshot)
    def test_malformed_or_non_drift_shapes_fail_closed(self):
        cases=[drift_row("UNKNOWN","calendar"),drift_row("FIX_PUBLICATION","pauta"),drift_row("FIX_PUBLICATION","calendar",target_id="pub-1"),drift_row("FIX_PUBLICATION","calendar",candidate_count=1),drift_row("FIX_PUBLICATION","calendar",candidate_count=0.5),drift_row("FIX_PUBLICATION","calendar",candidate_count=True),drift_row("FIX_PUBLICATION","calendar",candidates=[{"id":"pub-1"}]),drift_row("FIX_PUBLICATION","calendar",campaign_id=""),drift_row("FIX_PUBLICATION","calendar",action_id=""),drift_row("FIX_PUBLICATION","calendar",state="AMBIGUOUS_TARGET"),drift_row("FIX_PUBLICATION","calendar",state="EXACT_TARGET"),drift_row("CALENDAR","calendar",state="OWNER_ONLY")]
        for row in cases:
            result=annotate_campaign_execution_owner_drift(payload(row));self.assertNotIn("owner_drift",result["queue"][0]);self.assertEqual(result["owner_drift_observations"],[])
    def test_contracts_are_additive(self):
        result=annotate_campaign_execution_owner_drift(payload(drift_row("REVIEW_PAID","pauta")))
        for key in ("no_target_is_observable","no_target_preserves_w64_priority","no_target_does_not_select_replacement","no_target_owner_recovery_is_navigation_only","malformed_no_target_fails_closed","owner_drift_human_review_required","owner_drift_runs_after_campaign_actionability_filters","owner_drift_runs_after_setup_readiness_handoff"):self.assertTrue(result["contracts"][key])


class OwnerDriftCompositionTests(unittest.TestCase):
    def test_terminal_inherits_setup_readiness_owner_handoff(self):self.assertTrue(issubclass(AppRuntime,parent.AppRuntime))
    def test_browser_guard_is_zero_transport_and_non_persistent(self):
        source=(ROOT/"web"/"campaign-execution-owner-drift-guard.js").read_text(encoding="utf-8")
        for required in ("OWNER_STATE_DRIFT","TARGET_NOT_EXACT","actionCenterOpen","controlHandoffResolve","controlHandoffMessage","no se eligió un reemplazo"):self.assertIn(required,source)
        for forbidden in ("fetch(","XMLHttpRequest","sendBeacon","localStorage","sessionStorage","setInterval",".click()","dispatchEvent("):self.assertNotIn(forbidden,source)
    def test_service_bootstraps_after_setup_readiness_and_is_get_only(self):
        source=(ROOT/"src"/"binario_marketing"/"service_post_w99_campaign_execution_owner_drift_guard_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_setup_readiness_owner_handoff_app",source);self.assertIn('path == "/setup-readiness-owner-handoff.js"',source);self.assertIn("script.src='/campaign-execution-owner-drift-guard.js'",source)
        for forbidden in ("def do_POST","def do_PATCH","def do_PUT","def do_DELETE"):self.assertNotIn(forbidden,source)


if __name__=="__main__":unittest.main()
