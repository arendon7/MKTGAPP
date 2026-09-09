from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from binario_marketing.portfolio_inbox import build_portfolio_inbox


class PortfolioInboxMinimizationTests(unittest.TestCase):
    def test_cross_company_projection_rejects_unexpected_snapshot_fields(self):
        company = SimpleNamespace(
            id="company_" + "1" * 24,
            name="Marca",
            active=True,
            facebook_page_id="page-mapping-must-not-leak",
            instagram_id=None,
        )
        attention = {
            company.id: {
                "snapshot_state": "CURRENT",
                "captured_at": "2026-09-08T00:00:00+00:00",
                "refresh_required": False,
                "items": [{
                    "kind": "facebook_message",
                    "interaction_id": "message-1",
                    "occurred_at": "2026-09-07T23:00:00+00:00",
                    "actor_handle": "@Cliente",
                    "crm_contact_id": "not-a-local-contact",
                    "excerpt": "  Quiero   información  ",
                    "reply_eligible": True,
                    "attention_kind": "incoming_message",
                    "rank": 27,
                    "urgency": "high",
                    "blocking": False,
                    "title": "Responder",
                    "detail": "Detalle seguro",
                    "reason_code": "INBOX_TEST",
                    "provider_person_id": "person-secret",
                    "provider_link": "https://provider.example/private",
                    "from": {"id": "person-secret", "name": "Nombre privado"},
                    "full_message_body": "cuerpo completo que no debe cruzar el límite",
                    "provider_error": "token=never-leak",
                }],
            }
        }

        result = build_portfolio_inbox([company], attention)
        row = result["queue"][0]
        serialized = json.dumps(result)

        self.assertEqual(row["actor_handle"], "cliente")
        self.assertIsNone(row["crm_contact_id"])
        self.assertEqual(row["excerpt"], "Quiero información")
        self.assertEqual(row["urgency"], "HIGH")
        self.assertTrue(result["contracts"]["portfolio_field_allowlist_enforced"])
        for forbidden in (
            "person-secret",
            "provider.example",
            "Nombre privado",
            "cuerpo completo",
            "never-leak",
            "page-mapping-must-not-leak",
            "provider_person_id",
            "provider_link",
            "full_message_body",
            "provider_error",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
