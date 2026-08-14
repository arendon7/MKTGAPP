import tempfile
import unittest
from pathlib import Path

from binario_marketing.crm_store import CRMStore


class CRMStoreTests(unittest.TestCase):
    def test_contact_opportunity_activity_are_durable_and_company_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CRMStore(Path(tmp))
            company_a = "company_" + "a" * 24
            company_b = "company_" + "b" * 24
            contact = store.create_contact(company_a, {
                "name": "Ana Cliente",
                "organization": "Finca Norte",
                "email": "ana@example.com",
                "whatsapp": "+573001234567",
                "tags": ["café", "cliente", "café"],
            })
            self.assertEqual(contact.tags, ("café", "cliente"))
            self.assertEqual(len(store.list_contacts(company_a)), 1)
            self.assertEqual(store.list_contacts(company_b), [])

            opportunity = store.create_opportunity(company_a, {
                "contact_id": contact.id,
                "title": "Venta Wondergreen",
                "value": 2500000,
                "currency": "COP",
                "next_action": "Enviar propuesta",
                "next_action_at": "2030-01-02T15:00:00-05:00",
            })
            self.assertEqual(opportunity.stage, "NEW")
            opportunity = store.update_opportunity(company_a, opportunity.id, {"stage": "PROPOSAL"})
            self.assertEqual(opportunity.stage, "PROPOSAL")

            activity = store.create_activity(company_a, {
                "contact_id": contact.id,
                "opportunity_id": opportunity.id,
                "kind": "WHATSAPP",
                "summary": "Confirmar recepción de propuesta",
                "due_at": "2030-01-03T09:00:00-05:00",
            })
            self.assertIsNone(activity.completed_at)

            reopened = CRMStore(Path(tmp))
            detail = reopened.contact_detail(company_a, contact.id)
            self.assertEqual(detail["contact"]["name"], "Ana Cliente")
            self.assertEqual(len(detail["opportunities"]), 1)
            self.assertEqual(len(detail["activities"]), 1)
            completed = reopened.complete_activity(company_a, activity.id)
            self.assertIsNotNone(completed.completed_at)
            self.assertIsNotNone(reopened.get_activity(activity.id).completed_at)

    def test_cross_company_references_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CRMStore(Path(tmp))
            company_a = "company_" + "a" * 24
            company_b = "company_" + "b" * 24
            contact = store.create_contact(company_a, {"name": "Contacto A"})
            with self.assertRaisesRegex(ValueError, "does not belong"):
                store.create_opportunity(company_b, {"contact_id": contact.id, "title": "Cruce inválido"})
            opportunity = store.create_opportunity(company_a, {"contact_id": contact.id, "title": "Venta A"})
            with self.assertRaisesRegex(ValueError, "does not belong"):
                store.create_activity(company_b, {"opportunity_id": opportunity.id, "kind": "TASK", "summary": "No permitido"})
            with self.assertRaises(KeyError):
                store.update_contact(company_b, contact.id, {"notes": "No permitido"})

    def test_summary_counts_pipeline_and_overdue_followups(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CRMStore(Path(tmp))
            company = "company_" + "c" * 24
            contact = store.create_contact(company, {"name": "Lead"})
            open_opp = store.create_opportunity(company, {"contact_id": contact.id, "title": "Abierta", "stage": "INTERESTED"})
            store.create_opportunity(company, {"contact_id": contact.id, "title": "Ganada", "stage": "WON"})
            overdue = store.create_activity(company, {
                "opportunity_id": open_opp.id,
                "kind": "TASK",
                "summary": "Seguimiento vencido",
                "due_at": "2020-01-01T00:00:00+00:00",
            })
            summary = store.summary(company)
            self.assertEqual(summary["contacts"], 1)
            self.assertEqual(summary["opportunities_open"], 1)
            self.assertEqual(summary["opportunities_won"], 1)
            self.assertEqual(summary["pending_activities"], 1)
            self.assertEqual(summary["overdue_activities"], 1)
            self.assertEqual(summary["stage_counts"]["INTERESTED"], 1)
            store.complete_activity(company, overdue.id)
            self.assertEqual(store.summary(company)["overdue_activities"], 0)

    def test_activity_records_interaction_but_never_sends_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CRMStore(Path(tmp))
            company = "company_" + "d" * 24
            contact = store.create_contact(company, {"name": "Persona"})
            row = store.create_activity(company, {
                "contact_id": contact.id,
                "kind": "EMAIL",
                "summary": "Correo de seguimiento enviado manualmente",
            })
            self.assertEqual(row.kind, "EMAIL")
            text = (Path(tmp) / "activities" / f"{row.id}.json").read_text(encoding="utf-8").lower()
            for forbidden in ("access_token", "authorization", "smtp_password"):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
