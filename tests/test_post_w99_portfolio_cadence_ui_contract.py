import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PostW99PortfolioCadenceUIContractTests(unittest.TestCase):
    def test_null_age_is_never_rendered_as_zero_hours(self):
        source = (ROOT / "web" / "portfolio-cadence.js").read_text(encoding="utf-8")
        self.assertIn("timing?.age_hours!==null", source)
        self.assertIn("timing?.age_hours!==undefined", source)
        self.assertNotIn("if(Number.isFinite(Number(timing?.age_hours)))", source)

    def test_anomaly_rows_recover_canonical_action_before_navigation(self):
        source = (ROOT / "web" / "portfolio-cadence.js").read_text(encoding="utf-8")
        self.assertIn("function cadenceResolvedItem(item)", source)
        self.assertIn("postW99CadenceState.payload?.queue||[]", source)
        self.assertIn("const target=cadenceResolvedItem(item)", source)
        self.assertIn("target.action||{view:'home'}", source)


if __name__ == "__main__":
    unittest.main()
