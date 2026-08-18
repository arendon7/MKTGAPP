import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.service_wave55_guard_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]


class Wave55LeadIntakeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.other = self.runtime.create_company({"name": "Otra Empresa"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_intake_never_mutates_crm_and_exact_phone_matches_whatsapp(self):
        contact = self.runtime.create_contact(self.company["id"], {
            "name": "Existente", "whatsapp": "+57 300 123 4567"
        })
        before = len(self.runtime.crm.list_contacts(self.company["id"]))
        lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "FIRST_PARTY_FORM",
            "source_ref": "form_1",
            "name": "Lead",
            "phone": "573001234567",
        })
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), before)
        self.assertEqual(lead["status"], "MATCHED")
        self.assertEqual(lead["candidate_contacts"][0]["id"], contact["id"])
        self.assertFalse(self.runtime.lead_intake_payload(self.company["id"])["conversion_contract"]["intake_mutates_crm"])

    def test_open_duplicate_leads_are_surfaced_but_never_auto_merged(self):
        first = self.runtime.intake_lead(self.company["id"], {
            "connector": "API_IMPORT", "source_ref": "a", "name": "Uno", "email": "same@example.com"
        })
        second = self.runtime.intake_lead(self.company["id"], {
            "connector": "MANUAL", "source_ref": "b", "name": "Dos", "email": "SAME@example.com"
        })
        detail = self.runtime.lead_detail(self.company["id"], first["id"])
        self.assertIn(second["id"], detail["duplicate_open_lead_ids"])
        self.assertEqual(len(self.runtime.lead_intake.list(self.company["id"])), 2)
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)

    def test_create_contact_is_blocked_when_exact_match_exists_then_exact_link_succeeds(self):
        contact = self.runtime.create_contact(self.company["id"], {
            "name": "CRM", "email": "lead@example.com"
        })
        lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "API_IMPORT", "name": "Lead", "email": "LEAD@example.com"
        })
        with self.assertRaisesRegex(ValueError, "exact CRM identity match exists"):
            self.runtime.convert_lead(self.company["id"], lead["id"], {"action": "CREATE_CONTACT"})
        result = self.runtime.convert_lead(self.company["id"], lead["id"], {
            "action": "LINK_CONTACT", "contact_id": contact["id"]
        })
        self.assertEqual(result["converted_contact_id"], contact["id"])
        self.assertEqual(result["conversion_basis"], "EXACT_IDENTITY_MATCH")
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 1)

    def test_conflict_requires_explicit_exact_contact_selection_and_cross_company_fails(self):
        one = self.runtime.create_contact(self.company["id"], {"name": "Uno", "email": "same@example.com"})
        two = self.runtime.create_contact(self.company["id"], {"name": "Dos", "email": "same@example.com"})
        foreign = self.runtime.create_contact(self.other["id"], {"name": "Ajeno", "email": "same@example.com"})
        lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "MANUAL", "name": "Lead", "email": "same@example.com"
        })
        self.assertEqual(lead["status"], "CONFLICT")
        with self.assertRaisesRegex(ValueError, "requires contact_id"):
            self.runtime.convert_lead(self.company["id"], lead["id"], {"action": "LINK_CONTACT"})
        with self.assertRaises(KeyError):
            self.runtime.convert_lead(self.company["id"], lead["id"], {
                "action": "LINK_CONTACT", "contact_id": foreign["id"], "confirm_user_selected": True
            })
        result = self.runtime.convert_lead(self.company["id"], lead["id"], {
            "action": "LINK_CONTACT", "contact_id": two["id"]
        })
        self.assertIn(result["converted_contact_id"], {one["id"], two["id"]})
        self.assertEqual(result["converted_contact_id"], two["id"])

    def test_new_lead_explicitly_creates_contact_and_opportunity(self):
        lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "MANUAL", "name": "Nuevo", "email": "nuevo@example.com"
        })
        result = self.runtime.convert_lead(self.company["id"], lead["id"], {
            "action": "CREATE_CONTACT",
            "opportunity": {"title": "Venta nueva", "stage": "NEW", "value": 1200000, "currency": "COP"},
        })
        self.assertEqual(result["status"], "CONVERTED")
        self.assertEqual(result["conversion_basis"], "CREATED_NEW_CONTACT")
        self.assertIsNotNone(result["converted_contact_id"])
        self.assertIsNotNone(result["converted_opportunity_id"])
        opportunity = self.runtime.crm.get_opportunity(result["converted_opportunity_id"])
        self.assertEqual(opportunity.contact_id, result["converted_contact_id"])
        self.assertEqual(opportunity.value, 1200000)

    def test_verified_bm_tid_materializes_at_original_intake_time_not_conversion_time(self):
        campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Campaña Intake", "objective": "LEADS", "status": "IN_PROGRESS"
        })
        link = self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": campaign["id"],
            "destination_url": "https://example.com/form",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
        })
        lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "FIRST_PARTY_FORM",
            "source_ref": "submission_99",
            "name": "Atribuido",
            "email": "atribuido@example.com",
            "attribution_capture": {"bm_tid": link["tracking_code"], "utm_source": "instagram"},
        })
        received = lead["received_at"]
        result = self.runtime.convert_lead(self.company["id"], lead["id"], {
            "action": "CREATE_CONTACT",
            "opportunity": {"title": "Opp atribuida", "stage": "WON", "value": 500000, "currency": "COP"},
        })
        captures = self.runtime.first_party_captures.list(self.company["id"])
        claims = self.runtime.attribution.list_claims(self.company["id"])
        self.assertTrue(captures)
        self.assertTrue(claims)
        self.assertTrue(all(row.received_at == received for row in captures))
        self.assertTrue(all(row.captured_at == received for row in claims))
        attribution = self.runtime.attribution_payload(self.company["id"])
        self.assertEqual(attribution["summary"]["attributed_won"], 1)
        self.assertEqual(attribution["summary"]["value_by_currency"]["COP"]["won_value"], 500000)
        self.assertEqual(result["converted_opportunity_id"], claims[0].opportunity_id)

    def test_tampered_durable_attribution_fails_before_any_crm_write(self):
        campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Campaña Guard", "objective": "LEADS", "status": "IN_PROGRESS"
        })
        link = self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": campaign["id"],
            "destination_url": "https://example.com/form",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
        })
        lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "FIRST_PARTY_FORM",
            "source_ref": "tamper_1",
            "name": "Guarded",
            "email": "guarded@example.com",
            "attribution_capture": {"bm_tid": link["tracking_code"]},
        })
        path = Path(self.tmp.name) / "data" / "State" / "lead-intake" / f"{lead['id']}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["utm_source"] = "facebook"
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        before_contacts = len(self.runtime.crm.list_contacts(self.company["id"]))
        before_opportunities = len(self.runtime.crm.list_opportunities(self.company["id"]))
        with self.assertRaisesRegex(ValueError, "no longer matches canonical tracking link"):
            self.runtime.convert_lead(self.company["id"], lead["id"], {
                "action": "CREATE_CONTACT",
                "opportunity": {"title": "Should not exist", "stage": "NEW", "currency": "COP"},
            })
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), before_contacts)
        self.assertEqual(len(self.runtime.crm.list_opportunities(self.company["id"])), before_opportunities)

    def test_tampered_utm_is_rejected_before_intake_and_ai_context_is_aggregate_only(self):
        campaign = self.runtime.create_campaign(self.company["id"], {"name": "C", "objective": "LEADS"})
        link = self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": campaign["id"], "destination_url": "https://example.com", "utm_source": "instagram", "utm_medium": "social"
        })
        with self.assertRaisesRegex(ValueError, "does not match canonical"):
            self.runtime.intake_lead(self.company["id"], {
                "connector": "API_IMPORT", "name": "Privado", "email": "private@example.com",
                "attribution_capture": {"bm_tid": link["tracking_code"], "utm_source": "facebook"},
            })
        private_lead = self.runtime.intake_lead(self.company["id"], {
            "connector": "API_IMPORT", "name": "Privado", "email": "private@example.com"
        })
        context = self.runtime._ai_context(self.company["id"], task="STRATEGY", campaign_id=None, creative_media_id=None)
        text = json.dumps(context, ensure_ascii=False)
        self.assertIn("lead_intake", context)
        self.assertNotIn("Privado", text)
        self.assertNotIn("private@example.com", text)
        self.assertNotIn(private_lead["id"], text)
        self.assertNotIn(link["tracking_code"], text)

    def test_csv_reimport_is_idempotent_and_performs_zero_crm_mutations(self):
        content = b"name,email,source\nAna,ana@example.com,landing\nBeto,beto@example.com,feria\n"
        first = self.runtime.import_leads_csv(self.company["id"], content)
        second = self.runtime.import_leads_csv(self.company["id"], content)
        self.assertEqual(first["created"], 2)
        self.assertEqual(first["crm_mutations"], 0)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["reused"], 2)
        self.assertEqual(len(self.runtime.lead_intake.list(self.company["id"])), 2)
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)


if __name__ == "__main__":
    unittest.main()
