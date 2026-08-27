import json
import shutil
import subprocess
import unittest
from pathlib import Path

from binario_marketing import service_post_w99_operator_session_progress_app as parent
from binario_marketing.service_post_w99_canonical_change_evidence_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class CanonicalChangeEvidenceTests(unittest.TestCase):
    def test_terminal_inherits_operator_session_progress(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_pure_snapshot_diff_and_event_semantics_execute_in_node(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required by the repository browser contract")
        script = r"""
const fs=require('fs'),vm=require('vm');
vm.runInThisContext(fs.readFileSync('web/canonical-change-evidence.js','utf8'));
const before={
 id:'action-1',source:'CAMPAIGN',kind:'review_paid',rank:54,urgency:'MEDIUM',blocking:false,due_at:null,
 title:'Revisar pauta · Campaña',detail:'Contexto local',reason:{code:'CAMPAIGN_REVIEW_PAID'},
 action:{label:'Revisar pauta',view:'pauta',campaign_id:'campaign-1'},
 owner_resolution:{state:'EXACT_TARGET',source_code:'REVIEW_PAID',owner_view:'pauta',target_kind:'PAID_DRAFT',target_id:'plan-1',candidate_count:1},
 requires_human_action:true,read_only_recommendation:true,
 operator:{sequence:1},generated_at:'volatile-before'
};
const after=JSON.parse(JSON.stringify(before));after.urgency='HIGH';after.due_at='2026-08-27T15:00:00Z';after.operator.sequence=5;after.generated_at='volatile-after';
const left=canonicalChangeEvidenceSnapshot(before),right=canonicalChangeEvidenceSnapshot(after),changes=canonicalChangeEvidenceDiff(left,right);
const pending={action_id:'action-1',title:'Revisar pauta',snapshot:left};
const unchanged=canonicalChangeEvidenceBuildEvent(pending,{state:'STILL_IN_TODAY',action_id:'action-1',checked_at:'2026-08-27T14:00:00Z',current_action:before});
const changed=canonicalChangeEvidenceBuildEvent(pending,{state:'STILL_PENDING',action_id:'action-1',checked_at:'2026-08-27T14:01:00Z',current_action:after});
const gone=canonicalChangeEvidenceBuildEvent(pending,{state:'NO_LONGER_PENDING',action_id:'action-1',checked_at:'2026-08-27T14:02:00Z',current_action:null});
const inconsistentGone=canonicalChangeEvidenceBuildEvent(pending,{state:'NO_LONGER_PENDING',action_id:'action-1',checked_at:'2026-08-27T14:03:00Z',current_action:before});
console.log(JSON.stringify({left,right,changes,unchanged,changed,gone,inconsistentGone}));
"""
        proc = subprocess.run(
            [node, "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout)
        self.assertNotIn("operator", data["left"])
        self.assertNotIn("generated_at", data["left"])
        self.assertEqual(
            [change["field"] for change in data["changes"]],
            ["urgency", "due_at"],
        )
        self.assertEqual(data["unchanged"]["evidence_state"], "UNCHANGED")
        self.assertEqual(data["unchanged"]["changes"], [])
        self.assertEqual(data["changed"]["evidence_state"], "FIELDS_CHANGED")
        self.assertEqual(
            [change["field"] for change in data["changed"]["changes"]],
            ["urgency", "due_at"],
        )
        self.assertEqual(data["gone"]["evidence_state"], "NO_LONGER_PRESENT")
        self.assertEqual(data["gone"]["changes"], [])
        self.assertIsNone(data["inconsistentGone"])

    def test_browser_evidence_is_ephemeral_company_scoped_and_fail_closed(self):
        source = (ROOT / "web" / "canonical-change-evidence.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage", source)
        self.assertIn("canonicalChangeEvidenceKey(companyId)", source)
        self.assertIn("POST_W99_CANONICAL_CHANGE_EVIDENCE_MAX_EVENTS=20", source)
        self.assertIn("FIELDS_CHANGED", source)
        self.assertIn("UNCHANGED", source)
        self.assertIn("NO_LONGER_PRESENT", source)
        self.assertIn("STILL_IN_TODAY", source)
        self.assertIn("STILL_PENDING", source)
        self.assertIn("NO_LONGER_PENDING", source)
        self.assertIn("checkedAt===canonicalChangeEvidenceText(previousCheckedAt)", source)
        self.assertIn("String(company.id)!==String(companyId)", source)
        self.assertIn("String(result.action_id)!==String(actionId)", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("COMPLETED", source)
        self.assertNotIn("MARK_DONE", source)

    def test_browser_layer_has_no_business_transport_execution_or_polling(self):
        source = (ROOT / "web" / "canonical-change-evidence.js").read_text(encoding="utf-8")
        for forbidden in (
            "fetch(",
            "opsApi(",
            "XMLHttpRequest",
            "sendBeacon",
            "setInterval",
            ".click()",
            "dispatchEvent(",
            "requestSubmit(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("No prueba causalidad", source)
        self.assertIn("no prueba que la tarea esté completada", source)

    def test_service_bootstraps_after_operator_session_and_is_get_only(self):
        source = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_canonical_change_evidence_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("service_post_w99_operator_session_progress_app", source)
        self.assertIn('path == "/operator-session-progress.js"', source)
        self.assertIn("script.src='/canonical-change-evidence.js'", source)
        self.assertIn("data-post-w99-canonical-change-evidence", source)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, source)

    def test_release_boundary_is_documented(self):
        doc = (ROOT / "docs" / "POST_W99_CANONICAL_CHANGE_EVIDENCE.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("NO_LONGER_PRESENT", doc)
        self.assertIn("no significa", doc.lower())
        self.assertIn("whitelist", doc.lower())
        self.assertIn("sessionStorage", doc)
        self.assertIn("Physical-UAT PASS", doc)


if __name__ == "__main__":
    unittest.main()
