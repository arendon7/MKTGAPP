import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_operator_return_evidence_delta_app as parent
from binario_marketing.service_post_w99_operator_session_evidence_integration_app import (
    AppRuntime,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


class OperatorSessionEvidenceIntegrationTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_return_evidence_delta_parent(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_http_bootstrap_appends_session_evidence_after_return_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Session Evidence HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(
                    root + "/operator-return-evidence-delta.js", timeout=5
                ).read().decode("utf-8")
                adapter = urlopen(
                    root + "/operator-session-evidence-integration.js", timeout=5
                ).read().decode("utf-8")
                self.assertIn("/operator-session-evidence-integration.js", parent_js)
                self.assertIn(
                    "data-post-w99-operator-session-evidence-integration", parent_js
                )
                self.assertIn(
                    "binario.marketing.operator-session-evidence-integration.v1",
                    adapter,
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_gap_is_real_and_new_wrapper_runs_after_delta_exists(self):
        progress = (ROOT / "web" / "operator-session-progress.js").read_text(
            encoding="utf-8"
        )
        delta = (ROOT / "web" / "operator-return-evidence-delta.js").read_text(
            encoding="utf-8"
        )
        integration = (
            ROOT / "web" / "operator-session-evidence-integration.js"
        ).read_text(encoding="utf-8")
        self.assertIn("operatorSessionProgressRecordReturn", progress)
        self.assertNotIn("return_evidence_delta", progress)
        self.assertIn("result.return_evidence_delta=operatorReturnEvidenceResolve", delta)
        self.assertIn(
            "const value=await operatorSessionEvidenceBaseReturn.apply", integration
        )
        self.assertIn("result.return_evidence_delta", integration)
        self.assertIn("operatorSessionEvidenceIntegrate", integration)

    def test_only_exact_visible_delta_states_can_be_integrated(self):
        browser = (
            ROOT / "web" / "operator-session-evidence-integration.js"
        ).read_text(encoding="utf-8")
        state_decl = next(
            line
            for line in browser.splitlines()
            if line.startswith("const POST_W99_OPERATOR_SESSION_EVIDENCE_STATES=")
        )
        for state in (
            "FIELDS_CHANGED",
            "NO_WHITELISTED_CHANGE",
            "ACTION_NOT_PRESENT_AFTER_REREAD",
        ):
            self.assertIn(f"'{state}'", state_decl)
        for upstream_fail_closed_state in (
            "NO_OPEN_SNAPSHOT",
            "SNAPSHOT_SCOPE_MISMATCH",
            "RETURN_CONTEXT_MISMATCH",
            "RETURN_STATE_UNSUPPORTED",
            "CURRENT_ACTION_SHAPE_INVALID",
        ):
            self.assertNotIn(f"'{upstream_fail_closed_state}'", state_decl)
        # The integration may use similarly named local fail-closed outcomes; those
        # are diagnostics, not eligible persisted delta states.
        self.assertIn("state:'RETURN_CONTEXT_MISMATCH'", browser)

    def test_exact_return_event_identity_and_write_confirmation_are_required(self):
        browser = (
            ROOT / "web" / "operator-session-evidence-integration.js"
        ).read_text(encoding="utf-8")
        for marker in (
            "event?.type==='RETURN_OBSERVED'",
            "String(event.action_id||'')===String(actionId)",
            "operatorSessionEvidenceText(event.checked_at)===checkedAt",
            "matches.length!==1",
            "RETURN_EVENT_AMBIGUOUS",
            "RETURN_EVENT_NOT_FOUND",
            "operatorSessionProgressWrite(next)",
            "const reread=operatorSessionProgressRead(companyId)",
            "WRITE_NOT_CONFIRMED",
        ):
            self.assertIn(marker, browser)

    def test_persisted_projection_is_compact_and_rejects_corruption(self):
        browser = (
            ROOT / "web" / "operator-session-evidence-integration.js"
        ).read_text(encoding="utf-8")
        for marker in (
            "change_count",
            "changed_fields",
            "completion_claimed:false",
            "causal_change_claimed:false",
            "provider_freshness_claimed:false",
            "operatorSessionEvidenceStored",
            "new Set(fields).size!==fields.length",
        ):
            self.assertIn(marker, browser)
        self.assertNotIn("before:", browser)
        self.assertNotIn("after:", browser)
        self.assertNotIn("snapshot:", browser)
        self.assertNotIn("title:", browser)
        self.assertNotIn("detail:", browser)

    def test_existing_session_history_is_extended_without_new_storage_or_business_io(self):
        service = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_operator_session_evidence_integration_app.py"
        ).read_text(encoding="utf-8")
        browser = (
            ROOT / "web" / "operator-session-evidence-integration.js"
        ).read_text(encoding="utf-8")
        self.assertIn("operatorSessionProgressRead", browser)
        self.assertIn("operatorSessionProgressWrite", browser)
        self.assertIn("operatorSessionProgressEventDetail", browser)
        for forbidden in (
            "sessionStorage.setItem",
            "localStorage",
            "fetch(",
            "opsApi(",
            "XMLHttpRequest",
            "sendBeacon",
            "dispatchEvent",
            "requestSubmit",
            ".click(",
            "setInterval(",
        ):
            self.assertNotIn(forbidden, browser)
        for forbidden in (
            "def do_POST",
            "def do_PATCH",
            "def do_PUT",
            "def do_DELETE",
        ):
            self.assertNotIn(forbidden, service)

    def test_docs_and_dev_terminal_preserve_frozen_w99_boundary(self):
        docs = (
            ROOT / "docs" / "POST_W99_OPERATOR_SESSION_EVIDENCE_INTEGRATION.md"
        ).read_text(encoding="utf-8")
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No es W100", docs)
        self.assertIn(
            "from .service_post_w99_operator_session_evidence_integration_app import",
            entrypoint,
        )
        self.assertIn("service_post_w99_operator_return_evidence_delta_app", entrypoint)


if __name__ == "__main__":
    unittest.main()
