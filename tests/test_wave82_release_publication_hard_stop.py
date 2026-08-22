import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts" / "verify_release_tag.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_release_tag_wave82", VERIFY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave82ReleasePublicationHardStopTests(unittest.TestCase):
    def _valid_pipeline(self) -> str:
        return """
        env:
          PHYSICAL_UAT_ATTESTATION_B64: ${{ secrets.PHYSICAL_UAT_ATTESTATION_B64 }}
        run: python scripts/verify_combined_uat_attestation.py --evidence release-evidence/combined-physical-uat-attestation.json --expected-git-sha "$GITHUB_SHA"
        uses: actions/upload-artifact@v4
        with:
          name: verified-physical-uat-attestation-${{ github.sha }}
        uses: actions/download-artifact@v4
        with:
          name: verified-physical-uat-attestation-${{ github.sha }}
        - name: Enforce production release candidate
          run: python scripts/release_candidate_gate.py --repo . --app "$APP" --uat-evidence release-evidence/combined-physical-uat-attestation.json --production
        - name: Package immutable release asset
        """

    def test_current_persistent_release_satisfies_w82_after_w86_transport(self):
        verify = _module()
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        verify.verify_pipeline_contract(workflow)

    def test_contract_requires_verified_transport_and_production_gate_before_packaging(self):
        verify = _module()
        valid = self._valid_pipeline()
        verify.verify_pipeline_contract(valid)

        cases = {
            "missing_transport_secret": valid.replace("PHYSICAL_UAT_ATTESTATION_B64", "REMOVED", 2),
            "missing_verifier": valid.replace("verify_combined_uat_attestation.py", "removed.py"),
            "missing_uat": valid.replace(" --uat-evidence release-evidence/combined-physical-uat-attestation.json", ""),
            "missing_production": valid.replace(" --production", ""),
            "wrong_order": valid.replace("- name: Package immutable release asset", "- name: Package immutable release asset\n        # moved early", 1).replace("run: python scripts/release_candidate_gate.py", "run: python scripts/release_candidate_gate.py", 1),
            "non_blocking": valid.replace(" --production", " --production || true"),
            "expect_blocked": valid.replace(" --production", " --expect-blocked"),
        }
        # Explicitly construct a wrong-order case because string replacement above keeps relative order.
        cases["wrong_order"] = valid[: valid.index("scripts/release_candidate_gate.py")] + "Package immutable release asset\n" + valid[valid.index("scripts/release_candidate_gate.py") :]
        for name, workflow in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify.verify_pipeline_contract(workflow)

    def test_tag_verifier_calls_pipeline_contract_only_after_canonical_tag_checks(self):
        source = VERIFY_PATH.read_text(encoding="utf-8")
        body = source[source.index("def verify(tag: str)") : source.index("def main(")]
        self.assertIn("verify_pipeline_contract()", body)
        self.assertLess(body.index("if not RELEASE_READY"), body.index("verify_pipeline_contract()"))
        self.assertLess(body.index("if tag != RELEASE_TAG"), body.index("verify_pipeline_contract()"))

    def test_release_remains_fail_closed_today(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)

    def test_hard_stop_does_not_add_a_fourth_workflow(self):
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
