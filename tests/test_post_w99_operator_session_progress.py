import unittest
from pathlib import Path

from binario_marketing import service_post_w99_campaign_execution_owner_drift_guard_app as parent
from binario_marketing.service_post_w99_operator_session_progress_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class OperatorSessionProgressTests(unittest.TestCase):
    def test_terminal_inherits_owner_drift_guard(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_dev_entrypoint_exports_session_progress_and_keeps_owner_drift_breadcrumb(self):
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            entrypoint.count("from .service_post_w99_operator_session_progress_app import"),
            1,
        )
        self.assertEqual(
            entrypoint.count("from .service_post_w99_campaign_execution_owner_drift_guard_app import"),
            1,
        )
        self.assertIn("AppRuntime as _OwnerDriftAppRuntime", entrypoint)

    def test_browser_progress_is_company_scoped_session_evidence(self):
        source = (ROOT / "web" / "operator-session-progress.js").read_text(encoding="utf-8")
        self.assertIn("binario.marketing.operator-session-progress.v1", source)
        self.assertIn("sessionStorage", source)
        self.assertIn("operatorSessionProgressKey(companyId)", source)
        self.assertIn("company_id:String(companyId)", source)
        self.assertIn("POST_W99_OPERATOR_SESSION_PROGRESS_MAX_EVENTS=40", source)
        self.assertIn("ACTION_OPENED", source)
        self.assertIn("RETURN_OBSERVED", source)

    def test_only_canonical_execution_return_states_are_recorded(self):
        source = (ROOT / "web" / "operator-session-progress.js").read_text(encoding="utf-8")
        for state in ("STILL_IN_TODAY", "STILL_PENDING", "NO_LONGER_PENDING"):
            self.assertIn(state, source)
        self.assertIn("executionReturnBackToToday", source)
        self.assertIn("String(result.action_id)!==String(actionId)", source)
        self.assertIn("String(company.id)!==String(companyId)", source)
        self.assertNotIn("COMPLETED", source)
        self.assertNotIn("MARK_DONE", source)

    def test_ui_explicitly_refuses_completion_inference(self):
        source = (ROOT / "web" / "operator-session-progress.js").read_text(encoding="utf-8")
        self.assertIn("no es un contador de tareas completadas", source)
        self.assertIn("Esto no prueba por sí solo que esté completada", source)
        self.assertIn("owner sigue siendo la única autoridad de negocio", source)
        self.assertIn("Reiniciar registro de sesión", source)
        self.assertIn("ninguna tarea ni dato de negocio cambió", source)

    def test_browser_layer_has_no_business_transport_or_execution(self):
        source = (ROOT / "web" / "operator-session-progress.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage", source)
        for forbidden in (
            "localStorage",
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

    def test_service_bootstraps_after_owner_drift_and_is_get_only(self):
        source = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_operator_session_progress_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("service_post_w99_campaign_execution_owner_drift_guard_app", source)
        self.assertIn('path == "/campaign-execution-owner-drift-guard.js"', source)
        self.assertIn("script.src='/operator-session-progress.js'", source)
        self.assertIn("data-post-w99-operator-session-progress", source)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, source)

    def test_release_boundary_is_documented(self):
        doc = (ROOT / "docs" / "POST_W99_OPERATOR_SESSION_PROGRESS.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("sessionStorage", doc)
        self.assertIn("NO_LONGER_PENDING", doc)
        self.assertIn("no significa", doc.lower())
        self.assertIn("Physical-UAT PASS", doc)


if __name__ == "__main__":
    unittest.main()
