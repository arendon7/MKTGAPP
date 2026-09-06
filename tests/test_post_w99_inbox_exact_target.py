from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROWSER = ROOT / "web" / "inbox-action-center.js"


class InboxExactTargetContractTests(unittest.TestCase):
    def test_action_center_and_portfolio_capture_only_inbox_entity_targets(self):
        source = BROWSER.read_text(encoding="utf-8")
        self.assertIn("globalThis.actionCenterOpen", source)
        self.assertIn("globalThis.portfolioNavigate", source)
        self.assertIn("action.view!=='inbox'", source)
        self.assertIn("action.entity_id", source)
        self.assertIn("action.tab", source)

    def test_target_is_transient_and_never_persisted_or_auto_refreshed(self):
        source = BROWSER.read_text(encoding="utf-8")
        self.assertIn("let exactTarget=null", source)
        self.assertIn("exactTarget=null", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("MutationObserver", source)
        self.assertNotIn("inboxRefresh();", source)

    def test_manual_refresh_moves_exact_message_or_comment_to_front(self):
        source = BROWSER.read_text(encoding="utf-8")
        self.assertIn("applyExactTarget(inboxState.data,companyId)", source)
        self.assertIn("messages.findIndex", source)
        self.assertIn("conversations.unshift(conversations.splice(ci,1)[0])", source)
        self.assertIn("comments.findIndex", source)
        self.assertIn("comments.unshift(comments.splice(index,1)[0])", source)
        self.assertIn("refresh-attention", source)
        self.assertIn("method:'POST'", source)

    def test_successful_capture_refreshes_only_existing_local_projection_loaders(self):
        source = BROWSER.read_text(encoding="utf-8")
        self.assertIn("globalThis.actionCenterLoad(true)", source)
        self.assertIn("globalThis.portfolioLoad()", source)
        self.assertIn("globalThis.todayPortfolioLoad(true)", source)
        self.assertIn("Promise.allSettled(loads)", source)
        self.assertNotIn("postW99ActionState.payload", source)
        self.assertNotIn("postW99PortfolioState.payload", source)
        self.assertNotIn("postW99TodayPortfolioState.payload", source)

    def test_no_exact_target_adds_provider_or_business_authority(self):
        source = BROWSER.read_text(encoding="utf-8")
        self.assertNotIn("fetch('https://", source)
        self.assertNotIn("/contacts`,{method:'POST'", source)
        self.assertNotIn("/activities`,{method:'POST'", source)
        self.assertNotIn("/inbox/reply", source)
        self.assertNotIn("publish-now", source)


if __name__ == "__main__":
    unittest.main()
