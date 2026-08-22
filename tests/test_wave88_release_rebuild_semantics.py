from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave88ReleaseRebuildSemanticsTests(unittest.TestCase):
    def _fake_app(self, root: Path) -> Path:
        app = root / "Binario Marketing IA.app"
        resources = app / "Contents/Resources"
        source = resources / "source"
        package = source / "src/binario_marketing"
        package.mkdir(parents=True)
        (source / "web").mkdir(parents=True)
        (source / "apps").mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "version.py").write_text('__version__="0.9.0.dev1"\nRELEASE_READY=False\nRELEASE_TAG=None\n', encoding="utf-8")
        (source / "web/app.js").write_text("console.log('w88');\n", encoding="utf-8")
        (source / "apps/manifest.json").write_text('{"id":"fake"}\n', encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({
            "schema": "binario.marketing.full-mac-build.v4",
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
        }), encoding="utf-8")
        (resources / "RELEASE_READINESS.json").write_text(json.dumps({
            "schema": "binario.marketing.release-readiness.v1",
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "production_ready": False,
        }), encoding="utf-8")
        (resources / "launch.py").write_text("from binario_marketing.service_wave76_app import serve\n", encoding="utf-8")
        return app

    def test_origin_roles_are_mutually_exclusive(self):
        writer = _load("w88_writer_roles", ROOT / "scripts/write_physical_uat_candidate.py")
        self.assertEqual(writer._role_for_origin("push", "refs/heads/main"), writer.PHYSICAL_ROLE)
        self.assertEqual(writer._role_for_origin("push", "refs/tags/v1.0.0"), writer.DISTRIBUTION_ROLE)
        self.assertEqual(writer._role_for_origin("pull_request", "refs/pull/1/merge"), writer.VALIDATION_ROLE)
        self.assertEqual(writer._role_for_origin("workflow_dispatch", "refs/heads/main"), writer.VALIDATION_ROLE)
        with self.assertRaisesRegex(ValueError, "physical-UAT build-origin trust mismatch"):
            writer._validated_origin({
                "event": "push",
                "ref": "refs/tags/v1.0.0",
                "trusted_for_physical_uat": True,
                "trusted_for_distribution_rebuild": True,
            })

    def test_main_records_new_uat_but_tag_rebuild_cannot(self):
        writer = _load("w88_writer_manifest", ROOT / "scripts/write_physical_uat_candidate.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._fake_app(Path(tmpdir))
            main = writer.build_manifest(app, build_origin={
                "event": "push",
                "ref": "refs/heads/main",
                "trusted_for_physical_uat": True,
                "trusted_for_distribution_rebuild": False,
            })
            tag = writer.build_manifest(app, build_origin={
                "event": "push",
                "ref": "refs/tags/v1.0.0",
                "trusted_for_physical_uat": False,
                "trusted_for_distribution_rebuild": True,
            })
            self.assertEqual(main["role"], writer.PHYSICAL_ROLE)
            self.assertTrue(main["physical_uat"]["new_evidence_may_be_recorded"])
            self.assertFalse(main["distribution_rebuild"]["eligible_build_origin"])
            self.assertEqual(tag["role"], writer.DISTRIBUTION_ROLE)
            self.assertFalse(tag["physical_uat"]["eligible_build_origin"])
            self.assertFalse(tag["physical_uat"]["new_evidence_may_be_recorded"])
            self.assertTrue(tag["physical_uat"]["source_equivalent_prior_evidence_allowed"])
            self.assertTrue(tag["distribution_rebuild"]["must_not_record_new_physical_uat"])
            self.assertTrue(tag["distribution_rebuild"]["requires_prior_combined_uat_attestation"])
            self.assertTrue(tag["distribution_rebuild"]["requires_distribution_trust_evidence"])
            self.assertFalse(tag["distribution_rebuild"]["release_authority"])
            self.assertFalse(tag["release_boundary"]["manifest_grants_release_authority"])

    def test_release_gate_accepts_only_valid_arm64_role_shapes(self):
        gate = _load("w88_gate", ROOT / "scripts/release_candidate_gate.py")
        common = {
            "schema": gate.CANDIDATE_SCHEMA,
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
            "runtime_wave": 76,
            "certification_guard_wave": 84,
            "rebuild_semantics_wave": 88,
            "candidate_source_sha256": "b" * 64,
        }
        main = {
            **common,
            "role": gate.PHYSICAL_ROLE,
            "build_origin": {"event": "push", "ref": "refs/heads/main", "trusted_for_physical_uat": True, "trusted_for_distribution_rebuild": False},
            "physical_uat": {"eligible_build_origin": True, "new_evidence_may_be_recorded": True},
            "distribution_rebuild": {"eligible_build_origin": False},
        }
        tag = {
            **common,
            "role": gate.DISTRIBUTION_ROLE,
            "build_origin": {"event": "push", "ref": "refs/tags/v1.0.0", "trusted_for_physical_uat": False, "trusted_for_distribution_rebuild": True},
            "physical_uat": {"eligible_build_origin": False, "new_evidence_may_be_recorded": False, "source_equivalent_prior_evidence_allowed": True},
            "distribution_rebuild": {"eligible_build_origin": True, "must_not_record_new_physical_uat": True, "requires_prior_combined_uat_attestation": True, "requires_distribution_trust_evidence": True, "release_authority": False},
        }
        for payload, role in ((main, gate.PHYSICAL_ROLE), (tag, gate.DISTRIBUTION_ROLE)):
            with self.subTest(role=role):
                valid, actual_role, _ = gate._arm64_build_role_valid(
                    payload,
                    git_sha="a" * 40,
                    product_version="0.9.0.dev1",
                    candidate_source_sha256="b" * 64,
                    current_source_sha256="b" * 64,
                )
                self.assertTrue(valid)
                self.assertEqual(actual_role, role)
        tag["physical_uat"]["new_evidence_may_be_recorded"] = True
        valid, _, _ = gate._arm64_build_role_valid(tag, git_sha="a" * 40, product_version="0.9.0.dev1", candidate_source_sha256="b" * 64, current_source_sha256="b" * 64)
        self.assertFalse(valid)

    def test_w88_preserves_release_closed_runtime_and_workflows(self):
        builder = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        gate = (ROOT / "scripts/release_candidate_gate.py").read_text(encoding="utf-8")
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn("audit_wave88_release_rebuild_semantics.sh", builder)
        self.assertIn("DISTRIBUTION_REBUILD_ONLY", gate)
        self.assertIn("distribution_rebuild_uat_binding_invalid", gate)
        self.assertIn("physical_candidate_not_distribution_rebuild", gate)
        self.assertIn("service_wave76_app", (ROOT / "scripts/write_physical_uat_candidate.py").read_text(encoding="utf-8"))
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
