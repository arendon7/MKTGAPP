import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_operator_current_priority_continuity_app as parent
from binario_marketing.service_post_w99_operator_return_evidence_delta_app import (
    AppRuntime,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


class OperatorReturnEvidenceDeltaTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_current_priority_continuity(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_http_bootstrap_appends_delta_after_current_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Return Delta HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(root + "/operator-current-priority-continuity.js", timeout=5).read().decode("utf-8")
                adapter = urlopen(root + "/operator-return-evidence-delta.js", timeout=5).read().decode("utf-8")
                self.assertIn("/operator-return-evidence-delta.js", parent_js)
                self.assertIn("data-post-w99-operator-return-evidence-delta", parent_js)
                self.assertIn("REGRESO · EVIDENCIA ANTES / DESPUÉS", adapter)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_snapshot_is_explicit_whitelist_not_full_row_capture(self):
        source = (ROOT / "web" / "operator-return-evidence-delta.js").read_text(encoding="utf-8")
        for field in (
            "'urgency'",
            "'blocking'",
            "'due_at'",
            "'reason_code'",
            "'action.campaign_id'",
            "'owner_resolution.state'",
            "'owner_resolution.target_id'",
            "'owner_drift.state'",
        ):
            self.assertIn(field, source)
        self.assertIn("operatorReturnEvidenceProjection", source)
        self.assertNotIn("row.title", source)
        self.assertNotIn("row.detail", source)
        self.assertNotIn("reason?.explanation", source)

    def test_return_delta_requires_exact_scope_and_fresh_matching_reread(self):
        source = (ROOT / "web" / "operator-return-evidence-delta.js").read_text(encoding="utf-8")
        self.assertIn("SNAPSHOT_SCOPE_MISMATCH", source)
        self.assertIn("RETURN_CONTEXT_MISMATCH", source)
        self.assertIn("CURRENT_ACTION_SHAPE_INVALID", source)
        self.assertIn("String(snapshotEnvelope.company_id)!==String(companyId)", source)
        self.assertIn("String(snapshotEnvelope.action_id)!==String(actionId)", source)
        self.assertIn("String(result.action_id)!==String(actionId)", source)
        self.assertIn("checkedAt!==previousCheckedAt", source)
        self.assertIn("String(after.action_id)!==String(actionId)", source)

    def test_states_do_not_infer_completion_or_causality(self):
        source = (ROOT / "web" / "operator-return-evidence-delta.js").read_text(encoding="utf-8")
        for state in (
            "FIELDS_CHANGED",
            "NO_WHITELISTED_CHANGE",
            "ACTION_NOT_PRESENT_AFTER_REREAD",
            "NO_OPEN_SNAPSHOT",
            "RETURN_STATE_UNSUPPORTED",
        ):
            self.assertIn(state, source)
        self.assertIn("completion_claimed:false", source)
        self.assertIn("causal_change_claimed:false", source)
        self.assertIn("provider_freshness_claimed:false", source)
        self.assertIn("esto no demuestra que la acción haya sido completada", source)

    def test_browser_layer_uses_session_snapshot_only_and_has_no_transport_or_execution(self):
        source = (ROOT / "web" / "operator-return-evidence-delta.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage.setItem", source)
        self.assertIn("sessionStorage.getItem", source)
        self.assertIn("sessionStorage.removeItem", source)
        self.assertIn("operatorReturnEvidenceBaseTodayOpen=globalThis.todayOpen", source)
        self.assertIn("operatorReturnEvidenceBaseReturn=globalThis.executionReturnBackToToday", source)
        for forbidden in (
            "fetch(",
            "opsApi(",
            "XMLHttpRequest",
            "sendBeacon",
            "localStorage",
            "setInterval",
            ".click(",
            "dispatchEvent(",
            "requestSubmit(",
        ):
            self.assertNotIn(forbidden, source)

    def test_service_is_get_only_and_dev_entrypoint_keeps_parent_as_breadcrumb(self):
        service = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_operator_return_evidence_delta_app.py"
        ).read_text(encoding="utf-8")
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("service_post_w99_operator_current_priority_continuity_app", service)
        self.assertIn('path == "/operator-current-priority-continuity.js"', service)
        self.assertIn("script.src='/operator-return-evidence-delta.js'", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)
        self.assertEqual(
            entrypoint.count("from .service_post_w99_operator_current_priority_continuity_app import"),
            1,
        )
        self.assertIn("AppRuntime as _OperatorCurrentPriorityContinuityAppRuntime", entrypoint)
        self.assertEqual(
            entrypoint.count("from .service_post_w99_operator_return_evidence_delta_app import"),
            1,
        )

    def test_docs_preserve_scope_safety_and_w99_boundary(self):
        doc = (ROOT / "docs" / "POST_W99_OPERATOR_RETURN_EVIDENCE_DELTA.md").read_text(encoding="utf-8")
        self.assertIn("FIELDS_CHANGED", doc)
        self.assertIn("ACTION_NOT_PRESENT_AFTER_REREAD", doc)
        self.assertIn("whitelist", doc.lower())
        self.assertIn("completion_claimed=false", doc)
        self.assertIn("causal_change_claimed=false", doc)
        self.assertIn("provider_freshness_claimed=false", doc)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("53d1cf04a67da4308b37ac03c0be4546a04f36eb", doc)
        self.assertIn("not W100", doc)
        self.assertIn("Physical-UAT PASS", doc)


if __name__ == "__main__":
    unittest.main()
