from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "scripts" / "publish_main_candidate_receipt.py"
WORKFLOW = ROOT / ".github" / "workflows" / "full-mac-app.yml"


def _module():
    spec = importlib.util.spec_from_file_location("w99_main_candidate_receipt", PUBLISHER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class Wave99TrustedMainCandidateReceiptTests(unittest.TestCase):
    def _valid(self, module):
        return module.validate_receipt(
            repository="arendon7/MKTGAPP",
            git_sha="a" * 40,
            event_name="push",
            git_ref="refs/heads/main",
            run_id="123456",
            artifact_id="7890",
            artifact_url="https://github.com/arendon7/MKTGAPP/actions/runs/123456/artifacts/7890",
            artifact_digest="sha256:" + "b" * 64,
        )

    def test_receipt_accepts_only_exact_push_main_artifact_identity(self):
        module = _module()
        receipt = self._valid(module)
        self.assertEqual(receipt.git_sha, "a" * 40)
        self.assertEqual(receipt.artifact_digest, "b" * 64)
        self.assertEqual(receipt.run_id, "123456")
        self.assertEqual(receipt.artifact_id, "7890")

        cases = (
            {"event_name": "pull_request"},
            {"event_name": "workflow_dispatch"},
            {"git_ref": "refs/heads/wave/99-test"},
            {"git_ref": "refs/tags/v0.9.0"},
            {"artifact_url": "https://github.com/arendon7/MKTGAPP/actions/runs/123456/artifacts/7891"},
            {"artifact_digest": "not-a-digest"},
        )
        base = {
            "repository": "arendon7/MKTGAPP",
            "git_sha": "a" * 40,
            "event_name": "push",
            "git_ref": "refs/heads/main",
            "run_id": "123456",
            "artifact_id": "7890",
            "artifact_url": "https://github.com/arendon7/MKTGAPP/actions/runs/123456/artifacts/7890",
            "artifact_digest": "b" * 64,
        }
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.validate_receipt(**{**base, **change})

    def test_status_is_explicitly_candidate_only_and_never_uat_pass(self):
        module = _module()
        payload = module.status_payload(self._valid(module))
        self.assertEqual(payload["state"], "success")
        self.assertEqual(payload["context"], "physical-uat-candidate/main-artifact")
        self.assertIn("candidate uploaded", payload["description"])
        self.assertIn("UAT not executed", payload["description"])
        self.assertNotIn("UAT PASS", payload["description"])
        self.assertNotIn("release", payload["description"].lower())

    def test_publisher_posts_only_sanitized_status_and_never_logs_token(self):
        module = _module()
        receipt = self._valid(module)
        expected = {
            "state": "success",
            "context": module.CONTEXT,
            "target_url": receipt.artifact_url,
        }
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["request"] = request
            captured["timeout"] = timeout
            body = json.loads(request.data.decode("utf-8"))
            return _Response({**expected, "description": body["description"]})

        with patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = module.publish_status(receipt, token="secret-token-value")
        self.assertEqual(result["state"], "success")
        request = captured["request"]
        self.assertEqual(request.full_url, "https://api.github.com/repos/arendon7/MKTGAPP/statuses/" + "a" * 40)
        body = json.loads(request.data.decode("utf-8"))
        self.assertNotIn("secret-token-value", json.dumps(body))
        self.assertEqual(body["target_url"], receipt.artifact_url)
        self.assertEqual(body["context"], module.CONTEXT)

    def test_workflow_scopes_write_permission_to_push_main_receipt_job(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("id: physical_uat_candidate", source)
        self.assertIn("artifact-id: ${{ steps.physical_uat_candidate.outputs.artifact-id }}", source)
        self.assertIn("artifact-url: ${{ steps.physical_uat_candidate.outputs.artifact-url }}", source)
        self.assertIn("artifact-digest: ${{ steps.physical_uat_candidate.outputs.artifact-digest }}", source)
        self.assertIn("publish-main-candidate-receipt:", source)
        self.assertIn("needs: build-and-smoke-arm64", source)
        self.assertIn("github.event_name == 'push' && github.ref == 'refs/heads/main'", source)
        self.assertIn("statuses: write", source)
        self.assertIn("scripts/publish_main_candidate_receipt.py", source)
        self.assertIn("ARTIFACT_ID: ${{ needs.build-and-smoke-arm64.outputs.artifact-id }}", source)
        self.assertIn("ARTIFACT_URL: ${{ needs.build-and-smoke-arm64.outputs.artifact-url }}", source)
        self.assertIn("ARTIFACT_DIGEST: ${{ needs.build-and-smoke-arm64.outputs.artifact-digest }}", source)

        build_start = source.index("  build-and-smoke-arm64:")
        receipt_start = source.index("  publish-main-candidate-receipt:")
        build_section = source[build_start:receipt_start]
        receipt_section = source[receipt_start:]
        self.assertNotIn("statuses: write", build_section)
        self.assertIn("permissions:\n      contents: read\n      statuses: write", receipt_section)
        self.assertLess(source.index("Upload exact arm64 physical UAT candidate"), receipt_start)

    def test_repository_still_has_exactly_three_workflows(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
