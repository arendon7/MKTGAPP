import shutil
import unittest
from pathlib import Path

from binario_marketing import service_post_w99_setup_readiness_owner_handoff_app as setup_parent
from binario_marketing.service_post_w99_dev_app import AppRuntime

ROOT=Path(__file__).resolve().parents[1]


class OwnerDriftTerminalIntegrationTests(unittest.TestCase):
    def test_terminal_extends_setup_and_keeps_attention_plus_drift_contracts(self):
        self.assertTrue(issubclass(AppRuntime,setup_parent.AppRuntime));data_root=ROOT/"tmp-test-owner-drift-terminal";runtime=AppRuntime.create(ROOT,data_root)
        try:
            company=runtime.create_company({"name":"Owner Drift Terminal"});payload=runtime.action_center(company["id"])
            self.assertEqual(payload["schema"],"binario.marketing.action-center.v1");self.assertIn("observations",payload);self.assertIn("owner_drift_observations",payload)
            self.assertTrue(payload["contracts"]["campaign_passive_attention_uses_exact_source_lineage"]);self.assertTrue(payload["contracts"]["passive_campaign_states_excluded_from_today"]);self.assertTrue(payload["contracts"]["no_target_is_observable"]);self.assertTrue(payload["contracts"]["owner_drift_runs_after_setup_readiness_handoff"])
        finally:
            if runtime.social_scheduler is not None:runtime.social_scheduler.shutdown()
            runtime.proxies.shutdown();runtime.transcriptions.shutdown();runtime.renders.shutdown();shutil.rmtree(data_root,ignore_errors=True)
    def test_entrypoint_and_loader_preserve_terminal_order(self):
        entrypoint=(ROOT/"src"/"binario_marketing"/"service_post_w99_dev_app.py").read_text(encoding="utf-8");service=(ROOT/"src"/"binario_marketing"/"service_post_w99_campaign_execution_owner_drift_guard_app.py").read_text(encoding="utf-8")
        self.assertIn("from .service_post_w99_campaign_execution_owner_drift_guard_app import",entrypoint);self.assertIn("service_post_w99_setup_readiness_owner_handoff_app as base",service);self.assertIn('path == "/setup-readiness-owner-handoff.js"',service)


if __name__=="__main__":unittest.main()
