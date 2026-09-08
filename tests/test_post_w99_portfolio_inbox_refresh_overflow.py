from __future__ import annotations

import unittest

from binario_marketing.portfolio_inbox_refresh import MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES, build_refresh_plan


class PortfolioInboxRefreshOverflowTests(unittest.TestCase):
    def test_plan_reports_overflow_instead_of_silently_claiming_full_batch(self):
        companies = []
        attention = {}
        for index in range(MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES + 3):
            company_id = f"company_{index:024x}"
            companies.append({
                "id": company_id,
                "name": f"Marca {index:02d}",
                "facebook_page_id": f"page_{index}",
                "instagram_id": None,
            })
            attention[company_id] = {
                "snapshot_state": "MISSING",
                "captured_at": None,
                "items": [],
                "refresh_required": True,
            }
        plan = build_refresh_plan(companies, attention)
        self.assertEqual(plan["summary"]["configured_companies"], MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES + 3)
        self.assertEqual(plan["summary"]["eligible_overflow"], 3)
        self.assertEqual(len(plan["company_ids"]), MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES)
        self.assertTrue(plan["contracts"]["exact_company_ids_required"])


if __name__ == "__main__":
    unittest.main()
