from __future__ import annotations

import unittest
from types import SimpleNamespace

from binario_marketing.service_post_w99_inbox_action_center_app import AppRuntime


COMPANY = "company_" + "a" * 24


class _Companies:
    def get(self, company_id):
        if company_id != COMPANY:
            raise KeyError(company_id)
        return SimpleNamespace(id=COMPANY, facebook_page_id=None, instagram_id=None)


class _SnapshotStore:
    def get(self, company_id):
        self.requested = company_id
        return None


class InboxUnmappedCompanyTests(unittest.TestCase):
    def test_unmapped_company_has_no_refresh_action_source(self):
        runtime = SimpleNamespace(companies=_Companies(), inbox_attention_store=_SnapshotStore())
        result = AppRuntime.inbox_attention(runtime, COMPANY)
        self.assertEqual(result["snapshot_state"], "NOT_CONFIGURED")
        self.assertFalse(result["refresh_required"])
        self.assertEqual(result["items"], [])
        self.assertFalse(result["provider_read_performed"])

    def test_unmapped_short_circuit_does_not_require_crm_or_reply_stores(self):
        runtime = SimpleNamespace(companies=_Companies(), inbox_attention_store=_SnapshotStore())
        result = AppRuntime.inbox_attention(runtime, COMPANY)
        self.assertNotIn("crm", runtime.__dict__)
        self.assertNotIn("inbox_replies", runtime.__dict__)
        self.assertEqual(result["snapshot_state"], "NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
