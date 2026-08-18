import tempfile
import unittest
from pathlib import Path

from binario_marketing.lead_intake_store import LeadIntakeStore, identity_keys, parse_lead_csv


COMPANY = "company_" + "a" * 24
OTHER = "company_" + "b" * 24


class Wave55LeadIntakeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LeadIntakeStore(Path(self.tmp.name) / "leads")

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_ref_is_idempotent_but_changed_payload_fails_closed(self):
        payload = {
            "connector": "API_IMPORT",
            "source_ref": "submission_001",
            "name": "Ana",
            "email": "ANA@EXAMPLE.COM",
        }
        first = self.store.create(COMPANY, payload)
        second = self.store.create(COMPANY, payload)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.store.list(COMPANY)), 1)
        with self.assertRaisesRegex(ValueError, "source_ref already exists"):
            self.store.create(COMPANY, {**payload, "name": "Ana Cambiada"})

    def test_exact_identity_normalization_unifies_phone_whatsapp_and_instagram(self):
        left = set(identity_keys({
            "email": "USER@Example.COM",
            "phone": "+57 (300) 123-4567",
            "instagram": "https://instagram.com/Marca.Test/",
        }))
        right = set(identity_keys({
            "email": "user@example.com",
            "whatsapp": "573001234567",
            "instagram": "@marca.test",
        }))
        self.assertEqual(left, right)
        self.assertIn(("phone", "573001234567"), left)
        self.assertIn(("instagram", "marca.test"), left)

    def test_company_boundary_conversion_and_dismissal_are_fail_closed(self):
        row = self.store.create(COMPANY, {"connector": "MANUAL", "name": "Lead"})
        with self.assertRaises(KeyError):
            self.store.get(OTHER, row.id)
        converted = self.store.mark_contact_conversion(
            COMPANY, row.id, "contact_" + "c" * 24, basis="CREATED_NEW_CONTACT"
        )
        self.assertEqual(converted.converted_contact_id, "contact_" + "c" * 24)
        with self.assertRaisesRegex(ValueError, "converted lead cannot be dismissed"):
            self.store.dismiss(COMPANY, row.id, "duplicado")

    def test_csv_parser_stages_attribution_and_rejects_utm_without_bm_tid(self):
        content = (
            "nombre,correo,bm_tid,utm_source,utm_medium\n"
            "Ana,ana@example.com,bm_aaaaaaaaaaaaaaaaaaaaaaaa,instagram,paid_social\n"
            "Beto,beto@example.com,,facebook,paid_social\n"
        ).encode("utf-8")
        rows, errors = parse_lead_csv(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1]["attribution_capture"]["bm_tid"], "bm_" + "a" * 24)
        self.assertEqual(len(errors), 1)
        self.assertIn("require bm_tid", errors[0]["error"])


if __name__ == "__main__":
    unittest.main()
