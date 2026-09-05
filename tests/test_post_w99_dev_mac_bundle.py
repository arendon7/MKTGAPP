import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostW99DevMacBundleContractTests(unittest.TestCase):
    def test_builder_has_distinct_identity_and_terminal(self):
        script = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("Binario Marketing IA Post-W99 Dev.app", script)
        self.assertIn("com.sistemabinario.marketing.postw99dev", script)
        self.assertIn("service_post_w99_dev_app import serve", script)
        self.assertIn('"release_authority": false', script)
        self.assertIn('"physical_uat_authority": false', script)
        self.assertIn('"w100": false', script)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", script)

    def test_builder_reuses_runtime_but_never_replaces_canonical_dist(self):
        script = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn('OUT="$ROOT/dist-post-w99"', script)
        self.assertIn('"$ROOT/scripts/build_full_mac_app.sh"', script)
        self.assertNotIn('OUT="$ROOT/dist"', script)
        self.assertNotIn("build_full_mac_current_guarded.sh", script)
        self.assertNotIn("package_current_arm64_candidate.py", script)
        self.assertNotIn("publish_release_transaction.sh", script)

    def test_audit_requires_development_identity_and_non_authority(self):
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("com.sistemabinario.marketing.postw99dev", audit)
        self.assertIn("release_authority", audit)
        self.assertIn("physical_uat_authority", audit)
        self.assertIn("w100", audit)
        self.assertIn("service_post_w99_social_background_control_app.py", audit)

    def test_dedicated_workflow_does_not_modify_release_workflows(self):
        workflow = (ROOT / ".github" / "workflows" / "post-w99-dev-mac.yml").read_text(encoding="utf-8")
        self.assertIn("Post-W99 Dev Mac · arm64", workflow)
        self.assertIn("build_post_w99_dev_mac_app.sh", workflow)
        self.assertIn("test ! -f \"$PLIST\"", workflow)
        self.assertIn("no automatic LaunchAgent install", workflow)
        self.assertNotIn("publish_release_transaction", workflow)
        self.assertNotIn("release_candidate_gate", workflow)
        self.assertNotIn("v0.9.0", workflow)

    def test_canonical_release_builder_is_not_post_w99_terminal(self):
        canonical = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertNotIn("service_post_w99_dev_app", canonical)
        self.assertNotIn("com.sistemabinario.marketing.postw99dev", canonical)


if __name__ == "__main__":
    unittest.main()
