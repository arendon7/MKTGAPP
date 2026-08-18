import tempfile
import unittest
from pathlib import Path

from binario_marketing.learning_store import LearningStore


class Wave52LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearningStore(Path(self.tmp.name))
        self.company = "company_1234567890abcdef12345678"

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_roundtrip_and_company_boundary(self):
        row = self.store.create_snapshot(self.company, {
            "date_preset": "last_7d",
            "social": {"totals": {"reach": 120}},
            "paid_media": {"totals": {"clicks": 8}},
            "crm": {"summary": {"opportunities_won": 2}},
            "coverage": {"crm_campaign_attribution": False},
        })
        self.assertEqual(row.company_id, self.company)
        self.assertEqual(self.store.latest_snapshot(self.company).id, row.id)
        other = "company_abcdef1234567890abcdef12"
        with self.assertRaises(KeyError):
            self.store.get_snapshot(other, row.id)

    def test_decision_is_local_evidence_not_execution_state(self):
        snap = self.store.create_snapshot(self.company, {
            "social": {}, "paid_media": {}, "crm": {}, "coverage": {},
        })
        decision = self.store.create_decision(self.company, {
            "entity_kind": "CAMPAIGN",
            "entity_id": "campaign_1234567890abcdef12345678",
            "action": "ITERATE",
            "rationale": "CTR observado todavía no justifica escalar.",
            "snapshot_id": snap.id,
        })
        self.assertEqual(decision.action, "ITERATE")
        self.assertFalse(hasattr(decision, "executed"))
        self.assertFalse(hasattr(decision, "remote_status"))

    def test_rejects_secrets_invalid_presets_and_entities(self):
        with self.assertRaisesRegex(ValueError, "credentials"):
            self.store.create_snapshot(self.company, {
                "social": {"access_token": "secret"}, "paid_media": {}, "crm": {}, "coverage": {},
            })
        with self.assertRaisesRegex(ValueError, "date preset"):
            self.store.create_snapshot(self.company, {
                "date_preset": "forever", "social": {}, "paid_media": {}, "crm": {}, "coverage": {},
            })
        with self.assertRaisesRegex(ValueError, "campaign"):
            self.store.create_decision(self.company, {
                "entity_kind": "CAMPAIGN", "entity_id": "wrong", "action": "SCALE", "rationale": "x",
            })


if __name__ == "__main__":
    unittest.main()
