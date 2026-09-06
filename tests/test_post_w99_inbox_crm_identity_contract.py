from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InboxCRMIdentityContractTests(unittest.TestCase):
    def test_exact_canonical_workflows_remain_unchanged(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])

    def test_new_terminal_has_no_meta_transport_or_background_execution(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_inbox_crm_identity_app.py").read_text(encoding="utf-8")
        core = (ROOT / "src" / "binario_marketing" / "inbox_crm_identity.py").read_text(encoding="utf-8")
        browser = (ROOT / "web" / "inbox-crm-identity.js").read_text(encoding="utf-8")
        self.assertNotIn("MetaGraph", source)
        self.assertNotIn("MetaInboxReader", source)
        self.assertNotIn("setInterval", browser)
        self.assertNotIn("setTimeout", browser)
        self.assertNotIn("MutationObserver", browser)
        self.assertNotIn("graph.facebook", browser)
        self.assertIn("hmac.new", core)
        self.assertIn("0o600", core)

    def test_attention_refresh_hook_preserves_one_provider_read_path(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_inbox_action_center_app.py").read_text(encoding="utf-8")
        self.assertIn("def _inbox_attention_payload", source)
        self.assertIn("payload = self._inbox_attention_payload", source)
        self.assertEqual(source.count("super().social_inbox("), 1)

    def test_post_w99_terminal_advances_without_release_authority(self):
        terminal = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        build = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_inbox_crm_identity_app", terminal)
        self.assertIn('"release_authority": false', build)
        self.assertIn('"physical_uat_authority": false', build)
        self.assertIn('"w100": false', build)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", build)


if __name__ == "__main__":
    unittest.main()
