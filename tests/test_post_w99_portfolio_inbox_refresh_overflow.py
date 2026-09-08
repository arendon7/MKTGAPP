from __future__ import annotations

import unittest

from binario_marketing.portfolio_inbox_refresh import MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES, build_refresh_plan


class PortfolioInboxRefreshOverflowTests(unittest.TestCase):
    @staticmethod
    def _company(index: int) -> dict:
        return {
            "id": f"company_{index:024x}",
            "name": f"Marca {index:02d}",
            "facebook_page_id": f"page_{index}",
            "instagram_id": None,
        }

    def test_plan_reports_refresh_overflow_when_pending_batch_exceeds_limit(self):
        companies = []
        attention = {}
        for index in range(MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES + 3):
            company = self._company(index)
            companies.append(company)
            attention[company["id"]] = {
                "snapshot_state": "MISSING",
                "captured_at": None,
                "items": [],
                "refresh_required": True,
            }
        plan = build_refresh_plan(companies, attention)
        self.assertEqual(plan["summary"]["configured_companies"], MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES + 3)
        self.assertEqual(plan["summary"]["eligible_overflow"], 3)
        self.assertEqual(plan["summary"]["configured_overflow"], 3)
        self.assertEqual(plan["summary"]["refresh_overflow"], 3)
        self.assertEqual(len(plan["company_ids"]), MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES)
        self.assertEqual(len(plan["refresh_company_ids"]), MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES)
        self.assertTrue(plan["contracts"]["exact_company_ids_required"])

    def test_configured_overflow_does_not_block_safe_smaller_pending_batch(self):
        companies = []
        attention = {}
        total = MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES + 3
        pending = MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES - 5
        for index in range(total):
            company = self._company(index)
            companies.append(company)
            needs_refresh = index < pending
            attention[company["id"]] = {
                "snapshot_state": "STALE" if needs_refresh else "CURRENT",
                "captured_at": "2026-09-07T12:00:00+00:00",
                "items": [],
                "refresh_required": needs_refresh,
            }
        plan = build_refresh_plan(companies, attention)
        self.assertEqual(plan["summary"]["configured_overflow"], 3)
        self.assertEqual(plan["summary"]["refresh_required"], pending)
        self.assertEqual(plan["summary"]["refresh_overflow"], 0)
        self.assertEqual(len(plan["refresh_company_ids"]), pending)
        current_ids = {
            company["id"] for company in companies[pending:]
        }
        self.assertTrue(current_ids.isdisjoint(plan["refresh_company_ids"]))


if __name__ == "__main__":
    unittest.main()
