from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PortfolioInboxRefreshMacContractTests(unittest.TestCase):
    def test_build_audit_and_smoke_share_exact_feature_contract(self):
        build = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")

        for source in (build, audit, smoke):
            self.assertIn("service_post_w99_portfolio_inbox_refresh_app", source)
            self.assertIn("portfolio_inbox_refresh.py", source)
            self.assertIn("portfolio-inbox-refresh.js", source)

        for required in (
            "MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES = 50",
            "sequential_provider_reads",
            "per_company_failure_isolated",
            "/api/portfolio/inbox-refresh",
            "POST_W99_PORTFOLIO_INBOX_REFRESH",
            "window.confirm",
        ):
            self.assertIn(required, audit)

        self.assertIn("/api/portfolio/inbox-refresh-plan", smoke)
        self.assertIn("provider_read_performed", smoke)
        self.assertIn("portfolio Inbox provider-read POST", smoke)
        self.assertNotIn("curl --fail --silent \"$BASE/api/portfolio/inbox-refresh\"", smoke)

    def test_audit_keeps_post_w99_authority_boundary(self):
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        service = ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_inbox_refresh_app.py"
        service_source = service.read_text(encoding="utf-8")
        self.assertIn("release_authority'] is False", audit)
        self.assertIn("physical_uat_authority'] is False", audit)
        self.assertIn("w100'] is False", audit)
        self.assertNotIn("MetaGraphClient", service_source)
        self.assertNotIn("AIProviderClient", service_source)


if __name__ == "__main__":
    unittest.main()
