import tempfile
import unittest
from pathlib import Path

from binario_marketing.audience_store import AudienceStore
from binario_marketing.crm_import import ContactCSVImporter, parse_contact_csv
from binario_marketing.crm_store import CRMStore


COMPANY_A = "company_" + "a" * 24
COMPANY_B = "company_" + "b" * 24


class AudienceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.audiences = AudienceStore(root / "audiences")
        self.crm = CRMStore(root / "crm")
        self.first = self.crm.create_contact(COMPANY_A, {"name": "Ana", "email": "ana@example.com"})
        self.second = self.crm.create_contact(COMPANY_A, {"name": "Luis", "whatsapp": "+573001112233"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_static_audience_deduplicates_members_and_enforces_company_scope(self):
        row = self.audiences.create(COMPANY_A, {
            "name": "Clientes activos",
            "description": "Snapshot reusable",
            "contact_ids": [self.first.id, self.first.id, self.second.id],
        })
        self.assertEqual(row.contact_ids, (self.first.id, self.second.id))
        self.assertEqual(self.audiences.summary(COMPANY_A)["unique_contacts"], 2)
        with self.assertRaises(KeyError):
            self.audiences.get_for_company(COMPANY_B, row.id)
        updated = self.audiences.update(COMPANY_A, row.id, {"contact_ids": [self.second.id]})
        self.assertEqual(updated.contact_ids, (self.second.id,))
        removed = self.audiences.delete(COMPANY_A, row.id)
        self.assertEqual(removed.id, row.id)


class ContactCSVImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.crm = CRMStore(Path(self.tmp.name) / "crm")
        self.importer = ContactCSVImporter(self.crm)

    def tearDown(self):
        self.tmp.cleanup()

    def test_spanish_headers_import_and_duplicate_skip(self):
        content = (
            "nombre,empresa,correo,whatsapp,etiquetas,origen\n"
            "Ana,Finca Uno,ANA@example.com,+57 300 111 2233,cliente;café,Feria\n"
            "Ana repetida,Finca Dos,ana@example.com,,lead,Web\n"
        ).encode("utf-8")
        report = self.importer.import_bytes(COMPANY_A, content, strategy="skip")
        self.assertEqual(report["created"], 1)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(report["updated"], 0)
        rows = self.crm.list_contacts(COMPANY_A)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].email, "ANA@example.com")
        self.assertEqual(rows[0].tags, ("cliente", "café"))

    def test_update_strategy_changes_only_supplied_nonempty_fields_and_unions_tags(self):
        existing = self.crm.create_contact(COMPANY_A, {
            "name": "Ana Original",
            "organization": "Finca Original",
            "email": "ana@example.com",
            "phone": "123",
            "tags": ["cliente"],
        })
        content = (
            "name,organization,email,phone,tags\n"
            "Ana Nueva,,ANA@example.com,,vip;cliente\n"
        ).encode("utf-8")
        report = self.importer.import_bytes(COMPANY_A, content, strategy="update")
        self.assertEqual(report["updated"], 1)
        row = self.crm.get_contact(existing.id)
        self.assertEqual(row.name, "Ana Nueva")
        self.assertEqual(row.organization, "Finca Original")
        self.assertEqual(row.phone, "123")
        self.assertEqual(row.tags, ("cliente", "vip"))

    def test_same_identity_values_in_other_company_do_not_collide(self):
        self.crm.create_contact(COMPANY_B, {"name": "Otro", "email": "same@example.com"})
        content = b"name,email\nNuevo,same@example.com\n"
        report = self.importer.import_bytes(COMPANY_A, content, strategy="skip")
        self.assertEqual(report["created"], 1)
        self.assertEqual(len(self.crm.list_contacts(COMPANY_A)), 1)
        self.assertEqual(len(self.crm.list_contacts(COMPANY_B)), 1)

    def test_conflicting_identity_fields_are_reported_without_mutating_contacts(self):
        first = self.crm.create_contact(COMPANY_A, {"name": "Email owner", "email": "a@example.com"})
        second = self.crm.create_contact(COMPANY_A, {"name": "Phone owner", "phone": "+573001112233"})
        content = b"name,email,phone\nConflict,a@example.com,+57 300 111 2233\n"
        report = self.importer.import_bytes(COMPANY_A, content, strategy="update")
        self.assertEqual(report["created"], 0)
        self.assertEqual(report["updated"], 0)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(self.crm.get_contact(first.id).name, "Email owner")
        self.assertEqual(self.crm.get_contact(second.id).name, "Phone owner")

    def test_invalid_headers_and_missing_names_are_rejected_or_reported(self):
        with self.assertRaises(ValueError):
            parse_contact_csv(b"name,unknown_column\nAna,x\n")
        rows, errors = parse_contact_csv(b"name,email\n,empty@example.com\nAna,ok@example.com\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors, [{"row": 2, "error": "name is required"}])


if __name__ == "__main__":
    unittest.main()
