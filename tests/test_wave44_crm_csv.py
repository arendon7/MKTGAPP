import tempfile
import unittest
from pathlib import Path

from binario_marketing.crm_csv import export_contacts_csv, import_contacts_csv, parse_contacts_csv, preview_contacts_csv
from binario_marketing.crm_store import CRMStore


class Wave44CrmCsvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = CRMStore(Path(self.tmp.name) / "crm")
        self.company = "company_aaaaaaaaaaaaaaaaaaaaaaaa"
        self.other = "company_bbbbbbbbbbbbbbbbbbbbbbbb"

    def tearDown(self):
        self.tmp.cleanup()

    def test_semicolon_bom_and_spanish_aliases_parse(self):
        text = "\ufeffnombre;empresa;cargo;correo;telefono;whatsapp;instagram;origen;etiquetas;notas\nAna Pérez;Finca Sol;Gerente;ANA@EXAMPLE.COM;+57 300 111 2233;;@anafinca;Feria;café|cliente;Interés inicial\n"
        rows = parse_contacts_csv(text)
        self.assertEqual(len(rows), 1)
        row = rows[0]["payload"]
        self.assertEqual(row["name"], "Ana Pérez")
        self.assertEqual(row["organization"], "Finca Sol")
        self.assertEqual(row["email"], "ANA@EXAMPLE.COM")
        self.assertEqual(row["tags"], ["café", "cliente"])

    def test_preview_dedupes_existing_and_file_rows_without_writing(self):
        self.store.create_contact(self.company, {"name": "Existente", "email": "cliente@example.com"})
        text = "nombre,email,whatsapp\nDuplicado,CLIENTE@example.com,\nNuevo,nuevo@example.com,+57 300 222 3344\nNuevo repetido,nuevo@example.com,+57 300 222 3344\nSin nombre,otro@example.com,\n"
        before = len(self.store.list_contacts(self.company))
        preview = preview_contacts_csv(self.store, self.company, text)
        self.assertEqual(preview["rows"], 4)
        self.assertEqual(preview["valid"], 2)
        self.assertEqual(preview["duplicates"], 2)
        self.assertEqual(preview["invalid"], 0)
        self.assertEqual(len(self.store.list_contacts(self.company)), before)

    def test_import_is_repeat_safe_and_company_scoped(self):
        text = "name,company,email,phone,tags\nCarlos,Finca Uno,carlos@example.com,+57 301 555 7788,lead|cafe\nLucía,Finca Dos,lucia@example.com,,cliente\n"
        first = import_contacts_csv(self.store, self.company, text)
        second = import_contacts_csv(self.store, self.company, text)
        third = import_contacts_csv(self.store, self.other, text)
        self.assertEqual(first["created"], 2)
        self.assertEqual(first["duplicates"], 0)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["duplicates"], 2)
        self.assertEqual(third["created"], 2)
        self.assertEqual(len(self.store.list_contacts(self.company)), 2)
        self.assertEqual(len(self.store.list_contacts(self.other)), 2)

    def test_phone_and_whatsapp_cross_field_normalization_dedupes(self):
        self.store.create_contact(self.company, {"name": "A", "phone": "+57 (300) 123-4567"})
        preview = preview_contacts_csv(self.store, self.company, "nombre,whatsapp\nB,573001234567\n")
        self.assertEqual(preview["valid"], 0)
        self.assertEqual(preview["duplicates"], 1)

    def test_export_guards_spreadsheet_formula_and_round_trips(self):
        original = "=HYPERLINK(\"https://example.com\")"
        self.store.create_contact(self.company, {"name": original, "email": "safe@example.com", "tags": ["uno", "dos"]})
        csv_text = export_contacts_csv(self.store, self.company)
        self.assertTrue(csv_text.startswith("\ufeffnombre,empresa,cargo,email"))
        self.assertIn("\u200b=HYPERLINK", csv_text)
        self.assertNotIn("\n=HYPERLINK", csv_text)
        rows = parse_contacts_csv(csv_text)
        self.assertEqual(rows[0]["payload"]["name"], original)
        imported = import_contacts_csv(self.store, self.other, csv_text)
        self.assertEqual(imported["created"], 1)
        self.assertEqual(self.store.list_contacts(self.other)[0].name, original)

    def test_invalid_or_oversized_input_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "nombre/name"):
            parse_contacts_csv("email,phone\na@example.com,123456789\n")
        with self.assertRaisesRegex(ValueError, "larger than 2 MB"):
            parse_contacts_csv("nombre\n" + ("a" * 2_000_001))


if __name__ == "__main__":
    unittest.main()
