import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostW99DevMacBundleContractTests(unittest.TestCase):
    def test_builder_has_distinct_identity_and_terminal(self):
        script = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("Binario Marketing IA Post-W99 Dev.app", script)
        self.assertIn("com.sistemabinario.marketing.postw99dev", script)
        self.assertIn("service_post_w99_dev_app import serve", script)
        self.assertIn("service_post_w99_today_portfolio_app.py", script)
        self.assertIn("today-portfolio.js", script)
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

    def test_audit_requires_development_identity_non_authority_and_current_terminal(self):
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("com.sistemabinario.marketing.postw99dev", audit)
        self.assertIn("release_authority", audit)
        self.assertIn("physical_uat_authority", audit)
        self.assertIn("w100", audit)
        self.assertIn("service_post_w99_social_background_control_app.py", audit)
        self.assertIn("service_post_w99_today_portfolio_app.py", audit)
        self.assertIn("today-portfolio.js", audit)
        self.assertIn("/api/portfolio-control-tower", audit)

    def test_controlled_smoke_is_read_only_and_exercises_today_portfolio(self):
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("com.sistemabinario.marketing.postw99dev", smoke)
        self.assertIn("/api/health", smoke)
        self.assertIn("/api/social/background", smoke)
        self.assertIn("/api/portfolio-control-tower", smoke)
        self.assertIn("/primary-navigation.js", smoke)
        self.assertIn("/social-background-control.js", smoke)
        self.assertIn("/today-portfolio.js", smoke)
        self.assertIn("slice(0,5)", smoke)
        self.assertIn("Volver a todas las empresas", smoke)
        self.assertIn("window.confirm", smoke)
        self.assertIn("test ! -e \"$AGENT\"", smoke)
        self.assertNotIn("/api/social/background/install", smoke)
        self.assertNotIn("method=DELETE", smoke)
        self.assertNotIn("launchctl bootstrap", smoke)
        self.assertNotIn("launchctl bootout", smoke)

    def test_post_w99_builder_does_not_add_a_fourth_workflow(self):
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(len(workflows), 3)
        self.assertFalse((ROOT / ".github" / "workflows" / "post-w99-dev-mac.yml").exists())
        names = {path.name for path in workflows}
        self.assertEqual(names, {"ci.yml", "full-mac-app.yml", "release-mac.yml"})

    def test_canonical_release_builder_is_not_post_w99_terminal(self):
        canonical = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertNotIn("service_post_w99_dev_app", canonical)
        self.assertNotIn("com.sistemabinario.marketing.postw99dev", canonical)


if __name__ == "__main__":
    unittest.main()
