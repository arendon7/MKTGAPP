import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_operator_session_progress_app as parent
from binario_marketing.service_post_w99_operator_current_priority_continuity_app import (
    AppRuntime,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


class OperatorCurrentPriorityContinuityTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_operator_session_progress(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_http_bootstrap_appends_continuity_after_session_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Continuity HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(root + "/operator-session-progress.js", timeout=5).read().decode("utf-8")
                adapter = urlopen(root + "/operator-current-priority-continuity.js", timeout=5).read().decode("utf-8")
                self.assertIn("/operator-current-priority-continuity.js", parent_js)
                self.assertIn("data-post-w99-operator-current-priority-continuity", parent_js)
                self.assertIn("SESIÓN · CONTINUIDAD DE PRIORIDAD", adapter)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_only_no_longer_pending_can_offer_priority_handoff(self):
        source = (ROOT / "web" / "operator-current-priority-continuity.js").read_text(encoding="utf-8")
        self.assertIn("event.observed_state!=='NO_LONGER_PENDING'", source)
        self.assertIn("NO_HANDOFF_REQUIRED", source)
        self.assertIn("CURRENT_PRIORITY_CONFIRMED", source)
        self.assertIn("PLAN_CLEAR_AFTER_RETURN", source)
        self.assertIn("RETURN_PRIORITY_MISSING", source)
        self.assertIn("OBSERVED_PRIORITY_NO_LONGER_PRIMARY", source)
        self.assertIn("OBSERVED_PRIORITY_NO_LONGER_IN_TODAY", source)
        self.assertIn("CURRENT_PLAN_AMBIGUOUS", source)
        self.assertIn("CURRENT_PRIORITY_SHAPE_INVALID", source)

    def test_confirmation_requires_exact_current_today_primary_identity(self):
        source = (ROOT / "web" / "operator-current-priority-continuity.js").read_text(encoding="utf-8")
        self.assertIn("plan.filter(row=>operatorCurrentPriorityText(row?.id)===nextId)", source)
        self.assertIn("primaryId!==nextId||statusId!==nextId||firstId!==nextId", source)
        self.assertIn("Number(candidate?.operator?.sequence||0)!==1", source)
        self.assertIn("operatorCurrentPriorityText(candidate?.action?.view)===''", source)
        self.assertIn("causal_successor_claimed:false", source)
        self.assertIn("String(payload.company?.id||'')!==String(companyId)", source)

    def test_human_click_revalidates_before_existing_today_open(self):
        source = (ROOT / "web" / "operator-current-priority-continuity.js").read_text(encoding="utf-8")
        self.assertIn("open.addEventListener('click'", source)
        self.assertIn("const fresh=operatorCurrentPriorityResolve()", source)
        self.assertIn("fresh.current_priority_id!==result.current_priority_id", source)
        self.assertIn("todayOpen(fresh.candidate)", source)
        self.assertIn("La prioridad cambió; relee el plan antes de abrirla.", source)
        self.assertNotIn("todayOpen(result.candidate)", source)

    def test_return_wrapper_runs_after_session_progress_and_reset_removes_stale_card(self):
        source = (ROOT / "web" / "operator-current-priority-continuity.js").read_text(encoding="utf-8")
        self.assertIn("operatorCurrentPriorityBaseReturn=globalThis.executionReturnBackToToday", source)
        self.assertIn("await operatorCurrentPriorityBaseReturn.apply(this,arguments)", source)
        self.assertIn("queueMicrotask(operatorCurrentPriorityRender)", source)
        self.assertIn("operatorCurrentPriorityBaseReset=globalThis.operatorSessionProgressReset", source)

    def test_browser_layer_has_no_business_transport_persistence_or_synthetic_execution(self):
        source = (ROOT / "web" / "operator-current-priority-continuity.js").read_text(encoding="utf-8")
        self.assertIn("operatorSessionProgressRead", source)
        for forbidden in (
            "fetch(",
            "opsApi(",
            "XMLHttpRequest",
            "sendBeacon",
            "localStorage",
            "sessionStorage.setItem",
            "sessionStorage.removeItem",
            "setInterval",
            ".click(",
            "dispatchEvent(",
            "requestSubmit(",
        ):
            self.assertNotIn(forbidden, source)

    def test_service_is_get_only_and_dev_entrypoint_preserves_parent_breadcrumbs(self):
        service = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_operator_current_priority_continuity_app.py"
        ).read_text(encoding="utf-8")
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("service_post_w99_operator_session_progress_app", service)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)
        self.assertEqual(entrypoint.count("from .service_post_w99_operator_session_progress_app import"), 1)
        self.assertIn("AppRuntime as _OperatorSessionProgressAppRuntime", entrypoint)
        self.assertEqual(entrypoint.count("from .service_post_w99_operator_current_priority_continuity_app import"), 1)
        self.assertIn("AppRuntime as _OwnerDriftAppRuntime", entrypoint)
        self.assertIn("AppRuntime as _SetupReadinessAppRuntime", entrypoint)

    def test_docs_refuse_completion_and_causal_successor_claims_and_preserve_w99(self):
        doc = (ROOT / "docs" / "POST_W99_OPERATOR_CURRENT_PRIORITY_CONTINUITY.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("53d1cf04a67da4308b37ac03c0be4546a04f36eb", doc)
        self.assertIn("next_action_id", doc)
        self.assertIn("CURRENT_PRIORITY_CONFIRMED", doc)
        self.assertIn("causal", doc.lower())
        self.assertIn("completion", doc.lower())
        self.assertIn("not W100", doc)
        self.assertIn("Physical-UAT PASS", doc)


if __name__ == "__main__":
    unittest.main()
