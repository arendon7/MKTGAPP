from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUNDTRIP = ROOT / "scripts" / "verify_packaged_release_asset.py"
AUTH = ROOT / "scripts" / "release_artifact_authorization.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_distribution_trust(path: Path, *, architecture: str = "arm64") -> dict:
    row = {
        "schema": "binario.marketing.distribution-trust.v1",
        "git_sha": "a" * 40,
        "architecture": architecture,
        "product_version": "1.0.0",
        "runtime_wave": 76,
        "signing_mode": "developer_id",
        "developer_id_identity": "Developer ID Application: Example Corp (TEAM123456)",
        "notarized": True,
        "notary_submission_id": f"submission-{architecture}",
        "notary_status": "Accepted",
        "stapler_validated": True,
        "gatekeeper_assessed": True,
        "candidate_manifest_sha256": None,
        "release_authority": False,
    }
    row["evidence_sha256"] = _digest(row)
    path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")
    return row


def _post_package_fixture(module, root: Path, *, architecture: str = "arm64"):
    asset = root / f"Binario-Marketing-IA-v1.0.0-{architecture}.zip"
    with zipfile.ZipFile(asset, "w") as archive:
        archive.writestr("Binario Marketing IA.app/Contents/Info.plist", "plist")
    trust_path = root / f"distribution-{architecture}.json"
    trust = _write_distribution_trust(trust_path, architecture=architecture)
    payload = {
        "schema": module.SCHEMA,
        "tag": "v1.0.0",
        "git_sha": "a" * 40,
        "architecture": architecture,
        "product_version": "1.0.0",
        "runtime_wave": module.RUNTIME_WAVE,
        "certification_guard_wave": module.CERTIFICATION_GUARD_WAVE,
        "source_sha256": "b" * 64,
        "asset": {
            "name": asset.name,
            "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
            "size_bytes": asset.stat().st_size,
        },
        "archive": {
            "entry_count": 1,
            "canonical_app_root": module.APP_NAME,
            "path_safety_verified": True,
            "single_product_root_verified": True,
        },
        "extracted_app": {
            "bundle_name": module.APP_NAME,
            "build_provenance_sha256": "c" * 64,
            "release_readiness_sha256": "d" * 64,
            "distribution_rebuild_manifest_sha256": "e" * 64,
        },
        "pre_package_distribution_trust": {
            "schema": trust["schema"],
            "evidence_file_sha256": hashlib.sha256(trust_path.read_bytes()).hexdigest(),
            "evidence_sha256": trust["evidence_sha256"],
            "developer_id_identity": trust["developer_id_identity"],
            "notary_submission_id": trust["notary_submission_id"],
        },
        "roundtrip_trust": {
            "codesign_verified": True,
            "developer_id_identity": trust["developer_id_identity"],
            "stapler_validated": True,
            "gatekeeper_assessed": True,
        },
        "asset_roundtrip_verified": True,
        "operational_authorization": False,
        "release_authority": False,
        "publication_authority": False,
        "production_ready": False,
        "mutations_performed": False,
    }
    evidence = module._seal(payload)
    evidence_path = root / f"POST-PACKAGE-TRUST-{architecture}.json"
    evidence_path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
    return evidence_path, asset, trust_path, evidence


def _native_from_post(post: dict, *, rebuild_sha: str = "e" * 64, readiness_sha: str = "d" * 64) -> dict:
    return {
        "tag": "v1.0.0",
        "git_sha": "a" * 40,
        "architecture": "arm64",
        "product_version": "1.0.0",
        "runtime_wave": 76,
        "source_sha256": "b" * 64,
        "asset": dict(post["asset"]),
        "distribution_trust": {
            "evidence_file_sha256": post["pre_package_distribution_trust"]["evidence_file_sha256"],
            "evidence_sha256": post["pre_package_distribution_trust"]["evidence_sha256"],
            "notary_submission_id": post["pre_package_distribution_trust"]["notary_submission_id"],
        },
        "distribution_rebuild": {"manifest_sha256": rebuild_sha},
        "build_inputs": {
            "build_provenance_sha256": "c" * 64,
            "embedded_readiness_sha256": readiness_sha,
        },
        "evidence_sha256": "f" * 64,
    }


class Wave92ArtifactRoundtripTrustTests(unittest.TestCase):
    def test_archive_inventory_accepts_only_canonical_app_and_macos_metadata(self):
        module = _module(ROUNDTRIP, "w92_roundtrip_inventory")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            asset = root / "candidate.zip"
            with zipfile.ZipFile(asset, "w") as archive:
                archive.writestr("Binario Marketing IA.app/Contents/Info.plist", "plist")
                archive.writestr("__MACOSX/Binario Marketing IA.app/Contents/._Info.plist", "meta")
            report = module._validate_archive_inventory(asset)
            self.assertTrue(report["path_safety_verified"])
            self.assertTrue(report["single_product_root_verified"])
            self.assertEqual(report["canonical_app_root"], module.APP_NAME)

    def test_archive_path_traversal_is_blocked(self):
        module = _module(ROUNDTRIP, "w92_roundtrip_traversal")
        with tempfile.TemporaryDirectory() as raw:
            asset = Path(raw) / "candidate.zip"
            with zipfile.ZipFile(asset, "w") as archive:
                archive.writestr("Binario Marketing IA.app/Contents/Info.plist", "plist")
                archive.writestr("../escape", "bad")
            with self.assertRaisesRegex(ValueError, "path traversal|unexpected top-level"):
                module._validate_archive_inventory(asset)

    def test_archive_extra_top_level_content_is_blocked(self):
        module = _module(ROUNDTRIP, "w92_roundtrip_extra")
        with tempfile.TemporaryDirectory() as raw:
            asset = Path(raw) / "candidate.zip"
            with zipfile.ZipFile(asset, "w") as archive:
                archive.writestr("Binario Marketing IA.app/Contents/Info.plist", "plist")
                archive.writestr("README.txt", "unexpected")
            with self.assertRaisesRegex(ValueError, "unexpected top-level content"):
                module._validate_archive_inventory(asset)

    def test_portable_post_package_evidence_binds_exact_asset_distribution_and_archive(self):
        module = _module(ROUNDTRIP, "w92_roundtrip_verify")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            evidence_path, asset, trust_path, _ = _post_package_fixture(module, root)
            report = module.verify_evidence(
                evidence_path,
                asset=asset,
                distribution_evidence=trust_path,
                expected_tag="v1.0.0",
                expected_git_sha="a" * 40,
                expected_architecture="arm64",
            )
            self.assertTrue(report["asset_roundtrip_verified"])
            self.assertFalse(report["release_authority"])
            self.assertFalse(report["publication_authority"])

    def test_asset_tampering_after_roundtrip_is_blocked(self):
        module = _module(ROUNDTRIP, "w92_roundtrip_asset_tamper")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            evidence_path, asset, trust_path, _ = _post_package_fixture(module, root)
            asset.write_bytes(asset.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "asset digest mismatch"):
                module.verify_evidence(evidence_path, asset=asset, distribution_evidence=trust_path)

    def test_distribution_evidence_substitution_after_roundtrip_is_blocked(self):
        module = _module(ROUNDTRIP, "w92_roundtrip_trust_tamper")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            evidence_path, asset, trust_path, _ = _post_package_fixture(module, root)
            trust = json.loads(trust_path.read_text(encoding="utf-8"))
            trust["notary_submission_id"] = "different-submission"
            trust_path.write_text(json.dumps(trust), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "distribution trust digest mismatch|distribution evidence bytes mismatch"):
                module.verify_evidence(evidence_path, asset=asset, distribution_evidence=trust_path)

    def test_roundtrip_script_is_fail_closed_to_macos_and_executes_apple_trust_chain(self):
        source = ROUNDTRIP.read_text(encoding="utf-8")
        self.assertIn('platform.system() == "Darwin"', source)
        self.assertIn('"/usr/bin/ditto", "-x", "-k"', source)
        self.assertIn('"/usr/bin/codesign", "--verify", "--deep", "--strict"', source)
        self.assertIn('"/usr/bin/xcrun", "stapler", "validate"', source)
        self.assertIn('"/usr/sbin/spctl", "--assess", "--type", "execute"', source)
        self.assertIn("PHYSICAL_UAT_CANDIDATE.json", source)

    def test_w92_authorization_requires_roundtrip_alignment_with_w91_native_chain(self):
        auth = _module(AUTH, "w92_auth_valid")
        roundtrip = _module(ROUNDTRIP, "w92_auth_fixture")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, _, _, post = _post_package_fixture(roundtrip, root)
            native = _native_from_post(post)
            bound = auth._bind_native_chain(native, post, architecture="arm64")
            self.assertTrue(bound["codesign_verified_after_roundtrip"])
            self.assertTrue(bound["stapler_validated_after_roundtrip"])
            self.assertTrue(bound["gatekeeper_assessed_after_roundtrip"])
            self.assertEqual(bound["release_readiness_sha256"], "d" * 64)

    def test_w92_authorization_blocks_extracted_rebuild_drift(self):
        auth = _module(AUTH, "w92_auth_rebuild_drift")
        roundtrip = _module(ROUNDTRIP, "w92_auth_rebuild_fixture")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, _, _, post = _post_package_fixture(roundtrip, root)
            native = _native_from_post(post, rebuild_sha="9" * 64)
            with self.assertRaisesRegex(ValueError, "extracted rebuild manifest mismatch"):
                auth._bind_native_chain(native, post, architecture="arm64")

    def test_w92_authorization_blocks_extracted_release_readiness_drift(self):
        auth = _module(AUTH, "w92_auth_readiness_drift")
        roundtrip = _module(ROUNDTRIP, "w92_auth_readiness_fixture")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, _, _, post = _post_package_fixture(roundtrip, root)
            native = _native_from_post(post, readiness_sha="9" * 64)
            with self.assertRaisesRegex(ValueError, "extracted release readiness mismatch"):
                auth._bind_native_chain(native, post, architecture="arm64")

    def test_w92_authorization_blocks_failed_roundtrip_gate(self):
        auth = _module(AUTH, "w92_auth_failed_gate")
        roundtrip = _module(ROUNDTRIP, "w92_auth_failed_fixture")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, _, _, post = _post_package_fixture(roundtrip, root)
            post["roundtrip_trust"]["gatekeeper_assessed"] = False
            native = _native_from_post(post)
            with self.assertRaisesRegex(ValueError, "round-trip trust gate missing: gatekeeper_assessed"):
                auth._bind_native_chain(native, post, architecture="arm64")

    def test_workflow_requires_roundtrip_before_final_publication(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        package = workflow.find("Package immutable release asset")
        roundtrip = workflow.find("Verify W92 packaged artifact round-trip trust")
        w91_auth = workflow.find("Build cross-architecture release authorization")
        w92_auth = workflow.find("Build W92 artifact publication authorization")
        w92_verify = workflow.find("Verify W92 final publication authorization")
        publish = workflow.find("Publish permanent GitHub Release")
        self.assertTrue(0 <= package < roundtrip < w91_auth < w92_auth < w92_verify < publish, (package, roundtrip, w91_auth, w92_auth, w92_verify, publish))
        self.assertIn("POST-PACKAGE-TRUST-${{ matrix.arch }}.json", workflow)
        self.assertIn("RELEASE-ARTIFACT-AUTHORIZATION.json", workflow)


if __name__ == "__main__":
    unittest.main()
