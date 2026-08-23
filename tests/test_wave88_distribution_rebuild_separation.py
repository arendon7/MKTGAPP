from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHYSICAL = ROOT / "scripts/write_physical_uat_candidate.py"
REBUILD = ROOT / "scripts/write_distribution_rebuild_manifest.py"
RELEASE_BUILDER = ROOT / "scripts/build_full_mac_release_candidate.sh"
GATE = ROOT / "scripts/release_candidate_gate.py"
EVIDENCE_CHAIN = ROOT / "scripts/release_evidence_chain.py"
WORKFLOW = ROOT / ".github/workflows/persistent-release.yml"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave88DistributionRebuildSeparationTests(unittest.TestCase):
    def _fake_app(self, tmp: Path) -> Path:
        app = tmp / "Binario Marketing IA.app"
        resources = app / "Contents/Resources"
        source = resources / "source"
        for folder in (source / "src/binario_marketing", source / "web", source / "apps"):
            folder.mkdir(parents=True, exist_ok=True)
        (source / "src/binario_marketing/__init__.py").write_text("", encoding="utf-8")
        (source / "src/binario_marketing/version.py").write_text(
            '__version__ = "0.9.0.dev1"\nRELEASE_READY = False\nRELEASE_TAG = None\n', encoding="utf-8"
        )
        (source / "web/app.js").write_text("console.log('w88')\n", encoding="utf-8")
        (source / "apps/README.md").write_text("apps\n", encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({
            "schema": "binario.marketing.full-mac-build.v4",
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
        }), encoding="utf-8")
        (resources / "launch.py").write_text("from binario_marketing.service_wave76_app import serve\n", encoding="utf-8")
        return app

    def test_exact_physical_uat_origin_is_main_only_not_tag(self):
        physical = _load(PHYSICAL, "w88_physical")
        self.assertTrue(physical._trusted_origin("push", "refs/heads/main"))
        self.assertFalse(physical._trusted_origin("push", "refs/tags/v1.0.0"))
        self.assertFalse(physical._trusted_origin("pull_request", "refs/pull/96/merge"))
        source = PHYSICAL.read_text(encoding="utf-8")
        self.assertIn("Tag builds are source-equivalent distribution rebuilds", source)

    def test_distribution_manifest_is_tag_only_source_equivalent_and_detects_drift(self):
        rebuild = _load(REBUILD, "w88_rebuild")
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._fake_app(Path(tmpdir))
            origin = {"event": "push", "ref": "refs/tags/v0.9.0", "eligible_distribution_origin": True}
            manifest = rebuild.build_manifest(app, origin=origin)
            self.assertEqual(manifest["schema"], rebuild.SCHEMA)
            self.assertEqual(manifest["purpose"], "SOURCE_EQUIVALENT_DISTRIBUTION_REBUILD")
            self.assertFalse(manifest["physical_uat"]["claimed"])
            self.assertFalse(manifest["physical_uat"]["exact_bundle_tested"])
            self.assertEqual(manifest["physical_uat"]["authorization_mode"], "source_equivalent_only")
            path = app / "Contents/Resources/DISTRIBUTION_REBUILD.json"
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            rebuild.verify_manifest(app)
            (app / "Contents/Resources/source/web/app.js").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest drift"):
                rebuild.verify_manifest(app)

    def test_distribution_manifest_rejects_physical_candidate_identity(self):
        rebuild = _load(REBUILD, "w88_rebuild_conflict")
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._fake_app(Path(tmpdir))
            (app / "Contents/Resources/PHYSICAL_UAT_CANDIDATE.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not contain physical-UAT candidate"):
                rebuild.build_manifest(app, origin={
                    "event": "push", "ref": "refs/tags/v0.9.0", "eligible_distribution_origin": True,
                })

    def test_release_builder_has_explicit_distribution_mode_and_hardened_timestamped_signing(self):
        source = RELEASE_BUILDER.read_text(encoding="utf-8")
        self.assertIn("--distribution", source)
        self.assertIn("refs/tags/v", source)
        self.assertIn("Developer\\ ID\\ Application:*", source)
        self.assertIn("build_full_mac_current.sh", source)
        self.assertIn("PHYSICAL_UAT_CANDIDATE.json", source)
        self.assertIn("--options runtime --timestamp", source)
        self.assertIn("write_distribution_rebuild_manifest.py", source)
        self.assertIn("--verify", source)

    def test_tag_workflow_builds_distribution_rebuild_not_exact_physical_candidate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        evidence_chain = EVIDENCE_CHAIN.read_text(encoding="utf-8")
        self.assertIn('build_full_mac_release_candidate.sh --distribution --arch', workflow)
        self.assertIn("DISTRIBUTION_REBUILD.json", workflow)
        self.assertIn("SOURCE_EQUIVALENT_DISTRIBUTION_REBUILD", workflow)
        self.assertIn('test ! -e "$APP/Contents/Resources/PHYSICAL_UAT_CANDIDATE.json"', workflow)
        match = re.search(r"CERTIFICATION_GUARD_WAVE\s*=\s*(\d+)", evidence_chain)
        self.assertIsNotNone(match, evidence_chain)
        self.assertGreaterEqual(int(match.group(1)), 88)
        self.assertLess(workflow.index("DISTRIBUTION_REBUILD.json"), workflow.index("notarize_release_candidate.sh"))

    def test_production_gate_requires_rebuild_manifest_and_combined_source_equivalent_uat(self):
        source = GATE.read_text(encoding="utf-8")
        for marker in (
            "DISTRIBUTION_REBUILD_SCHEMA",
            "candidate_distribution_identity_conflict",
            "distribution_rebuild_manifest_missing_or_invalid",
            "distribution_requires_combined_source_equivalent_uat",
            "source_equivalent_arm64_rebuild",
            "source_equivalent_cross_arch_distribution",
        ):
            self.assertIn(marker, source)
        self.assertIn('candidate_origin.get("ref") == "refs/heads/main"', source)
        self.assertIn('rebuild.get("physical_uat", {}).get("claimed") is False', source)

    def test_release_boundary_and_workflow_count_remain_closed(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
