from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "scripts" / "release_artifact_authorization.py"


def _module():
    spec = importlib.util.spec_from_file_location("w92_artifact_authorization", AUTH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _pair(architecture: str, *, asset_sha: str, notary: str):
    identity = "Developer ID Application: Example Corp (TEAM123456)"
    native = {
        "tag": "v1.0.0",
        "git_sha": "a" * 40,
        "architecture": architecture,
        "product_version": "1.0.0",
        "runtime_wave": 76,
        "source_sha256": "b" * 64,
        "asset": {
            "name": f"Binario-Marketing-IA-v1.0.0-{architecture}.zip",
            "sha256": asset_sha,
            "size_bytes": 12345,
        },
        "distribution_trust": {
            "evidence_file_sha256": ("c" if architecture == "arm64" else "d") * 64,
            "evidence_sha256": ("e" if architecture == "arm64" else "f") * 64,
            "notary_submission_id": notary,
        },
        "distribution_rebuild": {"manifest_sha256": ("1" if architecture == "arm64" else "2") * 64},
        "build_inputs": {"build_provenance_sha256": ("3" if architecture == "arm64" else "4") * 64},
        "evidence_sha256": ("5" if architecture == "arm64" else "6") * 64,
    }
    post = {
        "tag": native["tag"],
        "git_sha": native["git_sha"],
        "architecture": architecture,
        "product_version": native["product_version"],
        "runtime_wave": native["runtime_wave"],
        "source_sha256": native["source_sha256"],
        "asset": dict(native["asset"]),
        "extracted_app": {
            "build_provenance_sha256": native["build_inputs"]["build_provenance_sha256"],
            "distribution_rebuild_manifest_sha256": native["distribution_rebuild"]["manifest_sha256"],
        },
        "pre_package_distribution_trust": {
            "evidence_file_sha256": native["distribution_trust"]["evidence_file_sha256"],
            "evidence_sha256": native["distribution_trust"]["evidence_sha256"],
            "notary_submission_id": notary,
            "developer_id_identity": identity,
        },
        "roundtrip_trust": {
            "codesign_verified": True,
            "developer_id_identity": identity,
            "stapler_validated": True,
            "gatekeeper_assessed": True,
        },
        "asset_roundtrip_verified": True,
        "evidence_sha256": ("7" if architecture == "arm64" else "8") * 64,
    }
    return native, post


class Wave92ArtifactAuthorizationTests(unittest.TestCase):
    def test_w91_authorization_is_mandatory(self):
        module = _module()
        arm, arm_post = _pair("arm64", asset_sha="9" * 64, notary="notary-arm")
        x86, x86_post = _pair("x86_64", asset_sha="a" * 64, notary="notary-x86")
        blocked_w91 = {
            "release_authority": False,
            "operational_authorization": True,
            "production_ready": True,
            "publication_performed": False,
            "authorization_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(ValueError, "W91 release authority missing"):
            module.build_authorization(
                w91=blocked_w91,
                arm_native=arm,
                x86_native=x86,
                arm_post=arm_post,
                x86_post=x86_post,
            )

    def test_w91_must_be_production_ready_and_prepublication(self):
        module = _module()
        arm, arm_post = _pair("arm64", asset_sha="9" * 64, notary="notary-arm")
        x86, x86_post = _pair("x86_64", asset_sha="a" * 64, notary="notary-x86")
        for field, value, message in (
            ("operational_authorization", False, "W91 operational authorization missing"),
            ("production_ready", False, "W91 authorization is not production ready"),
            ("publication_performed", True, "W91 authorization must precede publication"),
        ):
            w91 = {
                "release_authority": True,
                "operational_authorization": True,
                "production_ready": True,
                "publication_performed": False,
                "authorization_sha256": "b" * 64,
            }
            w91[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                module.build_authorization(
                    w91=w91,
                    arm_native=arm,
                    x86_native=x86,
                    arm_post=arm_post,
                    x86_post=x86_post,
                )

    def test_valid_w92_authorization_is_sealed_and_only_final_layer_has_publication_authority(self):
        module = _module()
        arm, arm_post = _pair("arm64", asset_sha="9" * 64, notary="notary-arm")
        x86, x86_post = _pair("x86_64", asset_sha="a" * 64, notary="notary-x86")
        w91 = {
            "release_authority": True,
            "operational_authorization": True,
            "production_ready": True,
            "publication_performed": False,
            "authorization_sha256": "b" * 64,
        }
        authorization = module.build_authorization(
            w91=w91,
            arm_native=arm,
            x86_native=x86,
            arm_post=arm_post,
            x86_post=x86_post,
        )
        module._verify_seal(authorization)
        self.assertEqual(authorization["schema"], module.SCHEMA)
        self.assertEqual(authorization["certification_guard_wave"], 92)
        self.assertTrue(authorization["release_authority"])
        self.assertTrue(authorization["publication_authority"])
        self.assertTrue(authorization["production_ready"])
        self.assertFalse(authorization["publication_performed"])
        self.assertFalse(authorization["mutations_performed"])

    def test_final_authorization_tampering_breaks_seal(self):
        module = _module()
        arm, arm_post = _pair("arm64", asset_sha="9" * 64, notary="notary-arm")
        x86, x86_post = _pair("x86_64", asset_sha="a" * 64, notary="notary-x86")
        w91 = {
            "release_authority": True,
            "operational_authorization": True,
            "production_ready": True,
            "publication_performed": False,
            "authorization_sha256": "b" * 64,
        }
        authorization = module.build_authorization(
            w91=w91,
            arm_native=arm,
            x86_native=x86,
            arm_post=arm_post,
            x86_post=x86_post,
        )
        authorization["publication_authority"] = False
        with self.assertRaisesRegex(ValueError, "authorization digest mismatch"):
            module._verify_seal(authorization)

    def test_cross_architecture_identity_drift_is_blocked(self):
        module = _module()
        arm, arm_post = _pair("arm64", asset_sha="9" * 64, notary="notary-arm")
        x86, x86_post = _pair("x86_64", asset_sha="a" * 64, notary="notary-x86")
        x86["git_sha"] = "c" * 40
        w91 = {
            "release_authority": True,
            "operational_authorization": True,
            "production_ready": True,
            "publication_performed": False,
            "authorization_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(ValueError, "x86_64 native/post-package git_sha mismatch|cross-architecture git_sha mismatch"):
            module.build_authorization(
                w91=w91,
                arm_native=arm,
                x86_native=x86,
                arm_post=arm_post,
                x86_post=x86_post,
            )


if __name__ == "__main__":
    unittest.main()
