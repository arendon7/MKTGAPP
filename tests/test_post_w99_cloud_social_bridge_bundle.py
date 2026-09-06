import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CloudSocialBridgeBundleContractTests(unittest.TestCase):
    def test_desktop_bridge_has_no_server_gateway_package_dependency(self):
        source = (ROOT / "src" / "binario_marketing" / "cloud_social_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("from gateway", source)
        self.assertNotIn("import gateway", source)
        self.assertIn("derive_social_tenant_secret", source)
        self.assertIn("SocialProcessLock", source)

    def test_post_w99_builder_requires_current_bridge_terminal_and_browser_control(self):
        build = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        for marker in ("cloud_social_bridge.py", "service_post_w99_cloud_social_bridge_app.py", "cloud-social-bridge.js"):
            self.assertIn(marker, build)
            self.assertIn(marker, audit)
        self.assertIn("service_post_w99_cloud_social_bridge_app", dev)
        self.assertIn("/cloud-social-bridge.js", smoke)
        self.assertIn("Delegar a cloud", smoke)

    def test_browser_control_is_explicit_only_and_never_polls(self):
        ui = (ROOT / "web" / "cloud-social-bridge.js").read_text(encoding="utf-8")
        self.assertIn("window.confirm", ui)
        self.assertIn("Delegar a cloud", ui)
        self.assertIn("Estado cloud", ui)
        self.assertIn("Reintentar cloud", ui)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("setTimeout", ui)
        self.assertNotIn("MetaGraph", ui)
        self.assertNotIn("access_token", ui)

    def test_release_boundary_remains_frozen_w99(self):
        docs = (ROOT / "docs" / "POST_W99_DESKTOP_CLOUD_SOCIAL_BRIDGE.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("not W100", docs)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
