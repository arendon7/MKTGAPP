import tempfile
import unittest
from pathlib import Path

from binario_marketing.contactability_store import ContactabilityStore


COMPANY_A = "company_" + "a" * 24
COMPANY_B = "company_" + "b" * 24
CONTACT = "contact_" + "c" * 24


class ContactabilityStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ContactabilityStore(Path(self.tmp.name) / "contactability")

    def tearDown(self):
        self.tmp.cleanup()

    def test_absence_is_unknown_without_persisting_record(self):
        row = self.store.get(COMPANY_A, CONTACT, "email")
        self.assertEqual(row.status, "UNKNOWN")
        self.assertIsNone(row.created_at)
        self.assertEqual(self.store.list(COMPANY_A), [])

    def test_explicit_decisions_require_evidence_and_normalize_timestamp(self):
        with self.assertRaises(ValueError):
            self.store.set(COMPANY_A, CONTACT, "email", {"status": "OPTED_IN"})
        row = self.store.set(COMPANY_A, CONTACT, "email", {
            "status": "OPTED_IN",
            "source": "Formulario web",
            "captured_at": "2030-01-02T10:30:00-05:00",
            "note": "Aceptó contacto por correo",
        })
        self.assertEqual(row.status, "OPTED_IN")
        self.assertEqual(row.source, "Formulario web")
        self.assertEqual(row.captured_at, "2030-01-02T15:30:00+00:00")
        self.assertIsNotNone(row.created_at)
        self.assertIsNotNone(row.updated_at)

    def test_opt_out_transition_and_reset_to_unknown(self):
        first = self.store.set(COMPANY_A, CONTACT, "whatsapp", {
            "status": "OPTED_IN",
            "source": "Evento",
            "captured_at": "2030-01-01T12:00:00+00:00",
        })
        second = self.store.set(COMPANY_A, CONTACT, "whatsapp", {
            "status": "OPTED_OUT",
            "source": "Solicitud del contacto",
            "captured_at": "2030-02-01T12:00:00+00:00",
            "note": "No contactar por WhatsApp",
        })
        self.assertEqual(second.status, "OPTED_OUT")
        self.assertEqual(second.created_at, first.created_at)
        reset = self.store.reset(COMPANY_A, CONTACT, "whatsapp")
        self.assertEqual(reset.status, "UNKNOWN")
        self.assertEqual(self.store.list(COMPANY_A), [])

    def test_company_and_channel_paths_are_isolated(self):
        self.store.set(COMPANY_A, CONTACT, "email", {
            "status": "OPTED_IN",
            "source": "CRM",
            "captured_at": "2030-01-01T00:00:00+00:00",
        })
        self.store.set(COMPANY_B, CONTACT, "email", {
            "status": "OPTED_OUT",
            "source": "CRM",
            "captured_at": "2030-01-01T00:00:00+00:00",
        })
        self.assertEqual(self.store.get(COMPANY_A, CONTACT, "email").status, "OPTED_IN")
        self.assertEqual(self.store.get(COMPANY_B, CONTACT, "email").status, "OPTED_OUT")
        self.assertEqual(self.store.get(COMPANY_A, CONTACT, "whatsapp").status, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
