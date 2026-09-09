from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from binario_marketing.portfolio_inbox import MAX_PORTFOLIO_INBOX_ITEMS, build_portfolio_inbox


ROOT = Path(__file__).resolve().parents[1]


class PortfolioInboxContractTests(unittest.TestCase):
    def test_global_queue_cap_is_declared_without_losing_observed_total(self):
        company = SimpleNamespace(
            id="company_" + "1" * 24,
            name="Marca",
            active=True,
            facebook_page_id="page",
            instagram_id=None,
        )
        items = []
        for index in range(MAX_PORTFOLIO_INBOX_ITEMS + 7):
            items.append({
                "kind": "facebook_message",
                "interaction_id": f"msg-{index}",
                "occurred_at": f"2026-09-07T{index % 24:02d}:00:00+00:00",
                "attention_kind": "incoming_message",
                "rank": 27,
                "urgency": "HIGH",
                "blocking": False,
            })
        result = build_portfolio_inbox([company], {company.id: {
            "snapshot_state": "CURRENT",
            "captured_at": "2026-09-07T23:00:00+00:00",
            "refresh_required": False,
            "items": items,
        }})
        self.assertEqual(result["summary"]["attention_total"], MAX_PORTFOLIO_INBOX_ITEMS + 7)
        self.assertEqual(result["summary"]["displayed_attention"], MAX_PORTFOLIO_INBOX_ITEMS)
        self.assertTrue(result["summary"]["queue_truncated"])
        self.assertEqual(len(result["queue"]), MAX_PORTFOLIO_INBOX_ITEMS)
        self.assertTrue(result["contracts"]["queue_scope_declared"])

    def test_build_audit_and_smoke_share_portfolio_inbox_contract(self):
        build = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        for source in (build, audit, smoke):
            self.assertIn("service_post_w99_portfolio_inbox_app", source)
            self.assertIn("portfolio_inbox.py", source)
            self.assertIn("portfolio-inbox.js", source)
        for required in (
            "MAX_PORTFOLIO_INBOX_ITEMS = 100",
            "existing_inbox_attention_is_resolution_authority",
            "/api/portfolio/inbox-attention",
            "postW99PortfolioInboxRefreshRun",
        ):
            self.assertIn(required, audit)
        self.assertIn("/api/portfolio/inbox-attention", smoke)
        self.assertIn("provider_read_performed", smoke)
        self.assertNotIn('curl --fail --silent "$BASE/api/portfolio/inbox-refresh"', smoke)
        self.assertNotIn('curl --fail --silent "$BASE/api/inbox/meta', smoke)

    def test_bundle_contract_preserves_w99_authority_boundary(self):
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("release_authority'] is False", audit)
        self.assertIn("physical_uat_authority'] is False", audit)
        self.assertIn("w100'] is False", audit)


if __name__ == "__main__":
    unittest.main()
