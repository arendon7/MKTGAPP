from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_CONTRACT = ROOT / "src/binario_marketing/release_contract.py"
CANDIDATE_WRITER = ROOT / "scripts/write_physical_uat_candidate.py"
COMBINED_VERIFY = ROOT / "scripts/verify_combined_uat_attestation.py"
PREPARED_VERIFY = ROOT / "scripts/verify_prepared_release_uat.py"
AUDIT = ROOT / "scripts/release_enablement_audit.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepared_repo(root: Path, *, version: str = "1.0.0", release_ready: bool = True, release_tag: str | None = "v1.0.0") -> Path:
    package = root / "src/binario_marketing"
    package.mkdir(parents=True)
    (root / "web").mkdir()
    (root / "apps").mkdir()
    (package / "version.py").write_text(
        f'__version__ = {version!r}\nRELEASE_READY = {release_ready!r}\nRELEASE_TAG = {release_tag!r}\n',
        encoding="utf-8",
    )
    (root / "web/app.js").write_text("console.log('prepared');\n", encoding="utf-8")
    (root / "apps/manifest.json").write_text('{"id":"prepared"}\n', encoding="utf-8")
    return root


def _combined_attestation(module, *, git_sha: str, version: str, source_sha: str, mode: str = "PREPARED_RELEASE", release_ready: bool = True, release_tag: str | None = "v1.0.0", guard_alias: int = 84) -> dict:
    binding = {
        "git_sha": git_sha,
        "product_version": version,
        "architecture": "arm64",
        "runtime_wave": 76,
        "candidate_guard_wave": 84,
        "certification_guard_wave": guard_alias,
        "attestation_wave": 85,
        "prepared_release_contract_wave": 91,
        "candidate_source_sha256": source_sha,
        "candidate_manifest_sha256": "c" * 64,
        "build_origin": {"event": "push", "ref": "refs/heads/main", "trusted_for_physical_uat": True},
        "provenance_schema": "binario.marketing.full-mac-build.v4",
        "release_contract": {
            "mode": mode,
            "version": version,
            "release_ready": release_ready,
            "release_tag": release_tag,
            "production_ready": False,
            "release_authority": False,
            "operational_authorization": False,
            "same_commit_must_be_tagged": mode == "PREPARED_RELEASE",
        },
    }
    core = {
        "schema": module.SCHEMA,
        "binding": binding,
        "phase_a": {"required_scenarios": 5, "passed_scenarios": 5, "report_sha256": "a" * 64},
        "phase_b": {"required_gates": 12, "passed_gates": 12, "overall": "UAT_PASS", "report_sha256": "b" * 64},
        "both_phases_passed": True,
        "operational_authorization": False,
        "release_authority": False,
        "production_ready": False,
    }
    return {**core, "generated_at": "2026-08-23T00:00:00+00:00", "attestation_sha256": module._digest(core)}


class Wave91PreparedReleasePhysicalUATContractTests(unittest.TestCase):
    def test_source_contract_distinguishes_locked_and_prepared_without_authority(self):
        module = _load(RELEASE_CONTRACT, "w91_contract")
        locked = module.evaluate_source_release_contract(version="0.9.0.dev1", release_ready=False, release_tag=None)
        self.assertEqual(locked["mode"], module.LOCKED_SOURCE)
        self.assertFalse(locked["release_authority"])
        self.assertFalse(locked["production_ready"])

        prepared = module.evaluate_source_release_contract(version="1.0.0", release_ready=True, release_tag="v1.0.0")
        self.assertEqual(prepared["mode"], module.PREPARED_RELEASE)
        self.assertTrue(prepared["source_contract_ready"])
        self.assertTrue(prepared["same_commit_must_be_tagged"])
        self.assertFalse(prepared["operational_authorization"])
        self.assertFalse(prepared["release_authority"])
        self.assertFalse(prepared["production_ready"])

    def test_invalid_prepared_contracts_are_rejected(self):
        module = _load(RELEASE_CONTRACT, "w91_contract_invalid")
        with self.assertRaisesRegex(ValueError, "development/RC"):
            module.evaluate_source_release_contract(version="1.0.0.dev1", release_ready=True, release_tag="v1.0.0.dev1")
        with self.assertRaisesRegex(ValueError, "tag mismatch"):
            module.evaluate_source_release_contract(version="1.0.0", release_ready=True, release_tag="v1.0.1")
        with self.assertRaisesRegex(ValueError, "locked source"):
            module.evaluate_source_release_contract(version="1.0.0", release_ready=False, release_tag="v1.0.0")

    def test_physical_candidate_writer_accepts_prepared_main_but_never_tag_as_exact_candidate(self):
        module = _load(CANDIDATE_WRITER, "w91_candidate_writer")
        with tempfile.TemporaryDirectory() as tmpdir:
            app = Path(tmpdir) / "Binario Marketing IA.app"
            resources = app / "Contents/Resources"
            source = resources / "source"
            _prepared_repo(source)
            resources.mkdir(parents=True, exist_ok=True)
            (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({
                "schema": "binario.marketing.full-mac-build.v4",
                "git_sha": "d" * 40,
                "architecture": "arm64",
                "product_version": "1.0.0",
            }), encoding="utf-8")
            (resources / "RELEASE_READINESS.json").write_text(json.dumps({
                "schema": "binario.marketing.release-readiness.v1",
                "git_sha": "d" * 40,
                "architecture": "arm64",
                "version": "1.0.0",
                "release_ready_flag": True,
                "release_tag": "v1.0.0",
                "production_ready": False,
            }), encoding="utf-8")
            (resources / "launch.py").write_text("from binario_marketing.service_wave76_app import serve\n", encoding="utf-8")

            main_manifest = module.build_manifest(app, build_origin={"event": "push", "ref": "refs/heads/main", "trusted_for_physical_uat": True})
            self.assertEqual(main_manifest["role"], module.PHYSICAL_ROLE)
            self.assertEqual(main_manifest["release_boundary"]["mode"], "PREPARED_RELEASE")
            self.assertTrue(main_manifest["release_boundary"]["release_ready"])
            self.assertFalse(main_manifest["release_boundary"]["release_authority"])
            self.assertFalse(main_manifest["release_boundary"]["production_ready"])

            tag_manifest = module.build_manifest(app, build_origin={"event": "push", "ref": "refs/tags/v1.0.0", "trusted_for_physical_uat": False})
            self.assertEqual(tag_manifest["role"], module.VALIDATION_ROLE)
            self.assertFalse(tag_manifest["physical_uat"]["eligible_build_origin"])

    def test_combined_verifier_accepts_w91_guard_aliases_and_rejects_disagreement(self):
        module = _load(COMBINED_VERIFY, "w91_combined_verify")
        row = _combined_attestation(module, git_sha="e" * 40, version="1.0.0", source_sha="f" * 64)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "combined.json"
            path.write_text(json.dumps(row), encoding="utf-8")
            report = module.verify(path, expected_git_sha="e" * 40)
            self.assertEqual(report["certification_guard_wave"], 84)
            self.assertEqual(report["source_release_contract"]["mode"], "PREPARED_RELEASE")
            self.assertFalse(report["release_authority"])

            bad = _combined_attestation(module, git_sha="e" * 40, version="1.0.0", source_sha="f" * 64, guard_alias=85)
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "aliases disagree"):
                module.verify(path, expected_git_sha="e" * 40)

    def test_prepared_release_verifier_requires_same_sha_tag_and_source_digest(self):
        combined = _load(COMBINED_VERIFY, "w91_combined_for_prepared")
        prepared = _load(PREPARED_VERIFY, "w91_prepared_verify")
        git_sha = "9" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _prepared_repo(Path(tmpdir) / "repo")
            source_sha = prepared._source_digest(repo)
            evidence = Path(tmpdir) / "combined.json"
            evidence.write_text(json.dumps(_combined_attestation(combined, git_sha=git_sha, version="1.0.0", source_sha=source_sha)), encoding="utf-8")
            report = prepared.verify(repo, evidence, expected_git_sha=git_sha, expected_tag="v1.0.0")
            self.assertTrue(report["same_commit_physically_tested"])
            self.assertTrue(report["same_source_digest_physically_tested"])
            self.assertFalse(report["release_authority"])
            self.assertFalse(report["production_ready"])

            with self.assertRaisesRegex(ValueError, "git SHA mismatch"):
                prepared.verify(repo, evidence, expected_git_sha="8" * 40, expected_tag="v1.0.0")
            with self.assertRaisesRegex(ValueError, "workflow tag"):
                prepared.verify(repo, evidence, expected_git_sha=git_sha, expected_tag="v1.0.1")
            (repo / "web/app.js").write_text("console.log('drift');\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source digest differs"):
                prepared.verify(repo, evidence, expected_git_sha=git_sha, expected_tag="v1.0.0")

    def test_locked_or_legacy_uat_cannot_authorize_prepared_tag(self):
        combined = _load(COMBINED_VERIFY, "w91_combined_locked")
        prepared = _load(PREPARED_VERIFY, "w91_prepared_locked")
        git_sha = "7" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _prepared_repo(Path(tmpdir) / "repo")
            source_sha = prepared._source_digest(repo)
            evidence = Path(tmpdir) / "combined.json"
            locked = _combined_attestation(combined, git_sha=git_sha, version="1.0.0", source_sha=source_sha, mode="LOCKED_SOURCE", release_ready=False, release_tag=None)
            evidence.write_text(json.dumps(locked), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not performed on PREPARED_RELEASE"):
                prepared.verify(repo, evidence, expected_git_sha=git_sha, expected_tag="v1.0.0")

            legacy = dict(locked)
            legacy_core = {k: v for k, v in legacy.items() if k not in {"generated_at", "attestation_sha256"}}
            legacy_core["binding"] = dict(legacy_core["binding"])
            legacy_core["binding"].pop("release_contract", None)
            legacy_core["binding"].pop("prepared_release_contract_wave", None)
            legacy = {**legacy_core, "generated_at": "2026-08-23T00:00:00+00:00", "attestation_sha256": combined._digest(legacy_core)}
            evidence.write_text(json.dumps(legacy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lacks W91 source release contract"):
                prepared.verify(repo, evidence, expected_git_sha=git_sha, expected_tag="v1.0.0")

    def test_persistent_release_orders_w91_before_distribution_and_keeps_three_workflows(self):
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        canonical = workflow.index("Verify canonical release tag")
        combined = workflow.index("verify_combined_uat_attestation.py")
        prepared = workflow.index("verify_prepared_release_uat.py")
        upload = workflow.index("Preserve verified physical UAT attestation")
        second_prepared = workflow.index("verify_prepared_release_uat.py", prepared + 1)
        distribution = workflow.index("build_full_mac_release_candidate.sh --distribution")
        gate = workflow.index("release_candidate_gate.py")
        package = workflow.index("Package immutable release asset")
        publish = workflow.index("gh release create")
        self.assertLess(canonical, combined)
        self.assertLess(combined, prepared)
        self.assertLess(prepared, upload)
        self.assertLess(upload, second_prepared)
        self.assertLess(second_prepared, distribution)
        self.assertLess(distribution, gate)
        self.assertLess(gate, package)
        self.assertLess(package, publish)
        self.assertIn("PREPARED-RELEASE-UAT-${{ matrix.arch }}.json", workflow)
        self.assertNotIn("assert row['product_version']=='0.9.0.dev1'", workflow)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])

    def test_current_source_remains_locked_and_audit_is_wave91_fail_closed(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0.dev1"', version)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        audit = _load(AUDIT, "w91_audit").audit(ROOT)
        self.assertEqual(audit["status"], "BLOCKED")
        self.assertEqual(audit["certification_guard_wave"], 91)
        self.assertTrue(all(audit["structural_gates"].values()), audit)
        self.assertFalse(audit["operational_authorization"])
        self.assertFalse(audit["release_authority"])
        self.assertFalse(audit["production_ready"])


if __name__ == "__main__":
    unittest.main()
