import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.background_scheduler import LockedSocialScheduler
from binario_marketing.background_social_agent import STATUS_SCHEMA, run_once
from binario_marketing.social_process_lock import social_queue_lock
from binario_marketing.wave27_instagram_local import Wave27SocialStore


ROOT = Path(__file__).resolve().parents[1]


class BackgroundAgentTests(unittest.TestCase):
    def test_one_shot_without_credentials_is_secret_free_and_sidecar_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "data"
            with patch.dict(os.environ, {"BINARIO_META_KEYCHAIN_HELPER": "", "META_ACCESS_TOKEN": ""}, clear=False):
                payload = run_once(data_root)
            self.assertEqual(payload["schema"], STATUS_SCHEMA)
            self.assertEqual(payload["processed"], 0)
            self.assertIsNone(payload["last_error"])
            self.assertNotIn("data_root", payload)
            sidecar = data_root / "State" / "background_social" / "status.json"
            self.assertTrue(sidecar.is_file())
            stored = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(stored, payload)
            text = sidecar.read_text(encoding="utf-8").lower()
            for forbidden in ("access_token", "authorization", "upload_uri", "rupload.facebook.com"):
                self.assertNotIn(forbidden, text)
            self.assertFalse((data_root / "State" / "workspace").exists())
            source = (ROOT / "src" / "binario_marketing" / "background_social_agent.py").read_text(encoding="utf-8")
            self.assertNotIn("Workspace", source)
            self.assertNotIn("timeline", source)

    def test_scheduler_skips_when_another_process_owner_holds_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Wave27SocialStore(Path(tmp) / "social")
            scheduler = LockedSocialScheduler(store)
            with social_queue_lock(store.root, timeout=0.0) as acquired:
                self.assertTrue(acquired)
                self.assertEqual(scheduler.run_once(), [])
            self.assertEqual(scheduler.lock_skips, 1)
            self.assertTrue(scheduler.status()["process_lock"])

    def test_interrupted_recovery_is_deferred_until_queue_is_owned(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Wave27SocialStore(Path(tmp) / "social")
            row = store.create("project-1", {
                "channel": "facebook_page",
                "target_id": "page-1",
                "kind": "text",
                "message": "Recovery guard",
            })
            store.queue(row.id)
            store.transition(row.id, "PUBLISHING")
            scheduler = LockedSocialScheduler(store)
            with social_queue_lock(store.root, timeout=0.0) as acquired:
                self.assertTrue(acquired)
                self.assertEqual(scheduler.run_once(), [])
                self.assertEqual(store.get(row.id).status, "PUBLISHING")
            with patch("binario_marketing.background_scheduler.MetaGraphClient.diagnose_env") as diagnose:
                diagnose.return_value.configured = False
                scheduler.run_once()
            self.assertEqual(store.get(row.id).status, "FAILED")
            self.assertEqual(scheduler.recovered_on_start, 1)


if __name__ == "__main__":
    unittest.main()
