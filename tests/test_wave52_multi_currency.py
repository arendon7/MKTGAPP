import tempfile
import unittest
from pathlib import Path

from binario_marketing.service_wave52_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave52MultiCurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Multi Currency"})
        self.runtime.social_analytics_meta = lambda company_id, limit=20: {
            "configured": False,
            "coverage": {"eligible": 0, "requested": 0, "observed": 0, "measured": 0, "errors": 0},
            "totals": {}, "observations": [],
        }
        self.runtime.company_paid_media = lambda company_id: [
            {"id": "a" * 32, "campaign_id": "remote_a", "ad_id": "ad_a", "plan": {"currency": "COP"}},
            {"id": "b" * 32, "campaign_id": "remote_b", "ad_id": "ad_b", "plan": {"currency": "USD"}},
        ]
        self.runtime.company_paid_media_observability = self._observe

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _observe(self, company_id, draft_id, date_preset=None):
        if draft_id.startswith("a"):
            return {"insights": {"impressions": 1000, "clicks": 50, "spend": 100000}, "safety": {}}
        return {"insights": {"impressions": 500, "clicks": 25, "spend": 40}, "safety": {}}

    def test_mixed_currency_spend_is_never_added_into_one_amount(self):
        result = self.runtime.refresh_learning(self.company["id"], {})
        paid = result["latest_snapshot"]["paid_media"]
        self.assertEqual(paid["currencies"], ["COP", "USD"])
        self.assertFalse(paid["spend_aggregated"])
        self.assertNotIn("spend", paid["totals"])
        self.assertEqual(paid["totals"]["impressions"], 1500)
        self.assertEqual(paid["totals"]["clicks"], 75)
        self.assertEqual(paid["totals_by_currency"]["COP"]["spend"], 100000)
        self.assertEqual(paid["totals_by_currency"]["USD"]["spend"], 40)

    def test_browser_contract_displays_unknown_not_zero_for_mixed_currency(self):
        ui = (ROOT / "web" / "learning-loop.js").read_text(encoding="utf-8")
        self.assertIn("varias monedas · no agregado", ui)
        self.assertIn("metrics.spend===undefined?'—'", ui)
        self.assertIn("spend_aggregated!==false", ui)


if __name__ == "__main__":
    unittest.main()
