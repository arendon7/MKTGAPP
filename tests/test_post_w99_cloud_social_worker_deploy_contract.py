from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "deploy" / "cloud-social-worker" / "Dockerfile"
RUNNER = ROOT / "scripts" / "run_cloud_social_worker_once.sh"
WORKER = ROOT / "src" / "binario_marketing" / "cloud_social_worker.py"


class CloudSocialWorkerDeployContractTests(unittest.TestCase):
    def test_container_is_one_shot_non_root_and_has_no_http_surface(self):
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("FROM python:3.12-slim-bookworm", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn('ENTRYPOINT ["./scripts/run_cloud_social_worker_once.sh"]', dockerfile)
        self.assertIn("COPY gateway ./gateway", dockerfile)
        self.assertIn("COPY src ./src", dockerfile)
        self.assertNotIn("EXPOSE ", dockerfile)
        self.assertNotIn("HEALTHCHECK", dockerfile)
        for server in ("uvicorn", "gunicorn", "flask run", "http.server"):
            self.assertNotIn(server, dockerfile.lower())
        self.assertNotIn("META_ACCESS_TOKEN=", dockerfile)
        self.assertNotIn("SUPABASE_SECRET_KEY=", dockerfile)
        self.assertIn('com.sistemabinario.release-authority="false"', dockerfile)
        self.assertIn('com.sistemabinario.physical-uat-authority="false"', dockerfile)

    def test_runner_fails_closed_before_worker_when_required_environment_is_missing(self):
        completed = subprocess.run(
            ["sh", str(RUNNER)],
            cwd=ROOT,
            env={"PATH": os.environ.get("PATH", "")},
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("BINARIO_SOCIAL_WORKER_ENABLED must equal 1", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_runner_requires_headless_secrets_by_name_but_never_prints_values(self):
        runner = RUNNER.read_text(encoding="utf-8")
        for required in (
            "BINARIO_SOCIAL_WORKER_ENABLED",
            "BINARIO_SOCIAL_WORKER_TENANTS",
            "SUPABASE_URL",
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "META_ACCESS_TOKEN",
        ):
            self.assertIn(required, runner)
        self.assertIn("exec python -m binario_marketing.cloud_social_worker", runner)
        self.assertNotIn("printenv", runner)
        self.assertNotIn(" env ", runner)
        self.assertNotIn('echo "$META_ACCESS_TOKEN"', runner)
        self.assertNotIn('echo "$SUPABASE_SECRET_KEY"', runner)

    def test_worker_remains_one_shot_cli_without_server_loop(self):
        worker = WORKER.read_text(encoding="utf-8")
        self.assertIn("def run_once(self) -> dict:", worker)
        self.assertIn("def main() -> int:", worker)
        self.assertIn('if __name__ == "__main__":', worker)
        for forbidden in ("serve_forever", "HTTPServer", "FastAPI", "Flask("):
            self.assertNotIn(forbidden, worker)

    def test_deploy_contract_does_not_add_a_fourth_canonical_workflow(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "release-mac.yml"])

    def test_python_project_keeps_zero_external_runtime_dependencies(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("requires-python = \">=3.12\"", pyproject)
        self.assertIn("dependencies = []", pyproject)


if __name__ == "__main__":
    unittest.main()
