import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Wave81MainPhysicalUATCandidateTests(unittest.TestCase):
    def test_builder_marks_only_push_to_main_as_physical_uat_candidate(self):
        builder = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn('BUILD_EVENT="${GITHUB_EVENT_NAME:-local}"', builder)
        self.assertIn('BUILD_REF="${GITHUB_REF:-local}"', builder)
        self.assertIn('PHYSICAL_UAT_CANDIDATE="false"', builder)
        self.assertIn('[[ "$BUILD_EVENT" == "push" && "$BUILD_REF" == "refs/heads/main" ]]', builder)
        self.assertIn('"build_event": "$BUILD_EVENT"', builder)
        self.assertIn('"build_ref": "$BUILD_REF"', builder)
        self.assertIn('"physical_uat_candidate": $PHYSICAL_UAT_CANDIDATE', builder)

    def test_physical_preflight_requires_main_candidate_and_gates_all_evidence_mutations(self):
        service = (ROOT / "src/binario_marketing/service_wave69_app.py").read_text(encoding="utf-8")
        self.assertIn('build.get("physical_uat_candidate") is True', service)
        self.assertIn('build.get("build_event") == "push"', service)
        self.assertIn('build.get("build_ref") == "refs/heads/main"', service)
        self.assertIn('"main-candidate-build"', service)
        self.assertIn("def _require_physical_uat_preflight", service)
        self.assertIn("def start_physical_uat", service)
        self.assertIn("def update_physical_uat_scenario", service)
        self.assertIn("def finish_physical_uat", service)
        self.assertGreaterEqual(service.count("self._require_physical_uat_preflight(company_id)"), 3)

    def test_arm64_guard_executes_wave81_bundle_audit(self):
        guarded = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts/audit_wave81_main_physical_uat_candidate.sh").read_text(encoding="utf-8")
        self.assertIn("audit_wave81_main_physical_uat_candidate.sh", guarded)
        self.assertIn("CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 81", guarded)
        self.assertIn("physical_uat_candidate", audit)
        self.assertIn('event == "push" and ref == "refs/heads/main"', audit)
        self.assertIn("WAVE 81 MAIN PHYSICAL UAT CANDIDATE AUDIT PASS", audit)

    def test_main_push_still_builds_arm64_and_pr_still_validates_without_becoming_candidate(self):
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertIn("push:", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("build_full_mac_wave47.sh --arch arm64", workflow)
        self.assertIn("build_full_mac_current_guarded.sh", (ROOT / "scripts/build_full_mac_wave47.sh").read_text(encoding="utf-8"))

    def test_release_boundary_and_current_runtime_remain_closed(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('0.9.0.dev1', version)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        current = (ROOT / "scripts/build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave76_app import serve", current)
        self.assertNotIn("service_wave81_app import serve", current)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
