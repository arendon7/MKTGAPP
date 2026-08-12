import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RenderDeliveryContractTests(unittest.TestCase):
    def test_full_mac_smoke_exercises_real_managed_render_api(self):
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertIn("Smoke boot and render through bundled API", workflow)
        self.assertIn("/assets/upload?filename=smoke-source.mp4&kind=video", workflow)
        self.assertIn("/assets/$ASSET_ID/probe", workflow)
        self.assertIn("/projects/$PROJECT_ID/renders", workflow)
        self.assertIn("/api/renders/$JOB_ID/file", workflow)
        self.assertIn('[[ "$JOB_SHA" == "$FILE_SHA" ]]', workflow)
        self.assertIn("^1920,1080$", workflow)

    def test_smoke_uses_isolated_user_data_root(self):
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertIn('BINARIO_IA_HOME="$DATA"', workflow)
        self.assertIn('DATA="$RUNNER_TEMP/binario-smoke-data"', workflow)


if __name__ == "__main__":
    unittest.main()
