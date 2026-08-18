import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.service_wave54_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]


class Wave54CaptureRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.other_company = self.runtime.create_company({"name": "Otra"})
        self.campaign_a = self.runtime.create_campaign(self.company["id"], {
            "name": "Lead A", "objective": "LEADS", "status": "IN_PROGRESS"
        })
        self.campaign_b = self.runtime.create_campaign(self.company["id"], {
            "name": "Lead B", "objective": "LEADS", "status": "IN_PROGRESS"
        })
        self.link_a = self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": self.campaign_a["id"],
            "destination_url": "https://example.com/a",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
        })
        self.link_b = self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": self.campaign_b["id"],
            "destination_url": "https://example.com/b",
            "utm_source": "facebook",
            "utm_medium": "paid_social",
        })

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _capture(self, link, **extra):
        return {
            "bm_tid": link["tracking_code"],
            "utm_source": link["utm_source"],
            "utm_medium": link["utm_medium"],
            "utm_campaign": link["utm_campaign"],
            "utm_id": link["utm_id"],
            "utm_content": link["utm_content"],
            "utm_source_platform": link["utm_source_platform"],
            "landing_url": "https://example.com/form?email=must-not-persist@example.com",
            "referrer_url": "https://social.example/post?private=1",
            "bridge_version": "1.0.0",
            **extra,
        }

    def test_contact_create_with_capture_generates_verified_evidence(self):
        contact = self.runtime.create_contact(self.company["id"], {
            "name": "Persona Privada",
            "email": "private@example.com",
            "phone": "+57 300 123 4567",
            "attribution_capture": self._capture(self.link_a, client_captured_at="2020-01-01T00:00:00+00:00"),
        })
        bridge = self.runtime.capture_bridge_payload(self.company["id"])
        attribution = self.runtime.attribution_payload(self.company["id"])
        self.assertEqual(bridge["summary"]["capture_records"], 1)
        self.assertEqual(bridge["summary"]["contact_captures"], 1)
        self.assertEqual(bridge["captures"][0]["contact_id"], contact["id"])
        self.assertEqual(bridge["captures"][0]["utm_validation"], "MATCHED_CANONICAL_LINK")
        self.assertNotEqual(bridge["captures"][0]["received_at"], bridge["captures"][0]["client_captured_at"])
        self.assertEqual(attribution["summary"]["attributed_contacts"], 1)
        text = json.dumps(bridge, ensure_ascii=False)
        self.assertNotIn("Persona Privada", text)
        self.assertNotIn("private@example.com", text)
        self.assertNotIn("300 123 4567", text)
        self.assertNotIn("must-not-persist@example.com", text)
        self.assertNotIn("private=1", text)
        self.assertIn("example.com", text)

    def test_utm_mismatch_fails_before_crm_mutation(self):
        before = len(self.runtime.crm.list_contacts(self.company["id"]))
        bad = self._capture(self.link_a)
        bad["utm_source"] = "facebook"
        with self.assertRaisesRegex(ValueError, "does not match canonical tracking link"):
            self.runtime.create_contact(self.company["id"], {
                "name": "Should Not Exist",
                "attribution_capture": bad,
            })
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), before)
        self.assertEqual(self.runtime.capture_bridge_payload(self.company["id"])["summary"]["capture_records"], 0)

    def test_opportunity_capture_links_contact_and_opportunity_without_inference(self):
        contact = self.runtime.create_contact(self.company["id"], {"name": "Lead"})
        opportunity = self.runtime.create_opportunity(self.company["id"], {
            "contact_id": contact["id"],
            "title": "Venta W54",
            "stage": "WON",
            "value": 1800000,
            "currency": "COP",
            "attribution_capture": self._capture(self.link_a),
        })
        bridge = self.runtime.capture_bridge_payload(self.company["id"])
        row = bridge["captures"][0]
        self.assertEqual(row["contact_id"], contact["id"])
        self.assertEqual(row["opportunity_id"], opportunity["id"])
        attribution = self.runtime.attribution_payload(self.company["id"])
        self.assertEqual(attribution["summary"]["attributed_opportunities"], 1)
        self.assertEqual(attribution["summary"]["value_by_currency"]["COP"]["won_value"], 1800000)

    def test_server_receive_order_beats_manipulated_browser_timestamp(self):
        contact = self.runtime.create_contact(self.company["id"], {"name": "Lead"})
        opportunity = self.runtime.create_opportunity(self.company["id"], {
            "contact_id": contact["id"], "title": "Opp", "stage": "WON", "value": 700000, "currency": "COP"
        })
        self.runtime.record_first_party_capture(self.company["id"], {
            **self._capture(self.link_a, client_captured_at="2099-01-01T00:00:00+00:00"),
            "opportunity_id": opportunity["id"],
        })
        self.runtime.record_first_party_capture(self.company["id"], {
            **self._capture(self.link_b, client_captured_at="2000-01-01T00:00:00+00:00"),
            "opportunity_id": opportunity["id"],
        })
        result = self.runtime.attribution_payload(self.company["id"])
        by_id = {row["id"]: row for row in result["campaigns"]}
        self.assertEqual(result["summary"]["attributed_opportunities"], 1)
        self.assertEqual(by_id[self.campaign_a["id"]]["attributed_opportunities"], 0)
        self.assertEqual(by_id[self.campaign_b["id"]]["attributed_opportunities"], 1)
        captures = self.runtime.capture_bridge_payload(self.company["id"])["captures"]
        self.assertTrue(all(row["received_at"] != row["client_captured_at"] for row in captures))

    def test_cross_company_capture_fails_closed(self):
        other_contact = self.runtime.create_contact(self.other_company["id"], {"name": "Ajeno"})
        with self.assertRaises(KeyError):
            self.runtime.record_first_party_capture(self.company["id"], {
                **self._capture(self.link_a),
                "contact_id": other_contact["id"],
            })

    def test_ai_context_gets_aggregates_without_codes_hosts_or_pii(self):
        contact = self.runtime.create_contact(self.company["id"], {
            "name": "Privado",
            "email": "sensitive@example.com",
            "attribution_capture": self._capture(self.link_a),
        })
        context = self.runtime._ai_context(self.company["id"], task="STRATEGY", campaign_id=None, creative_media_id=None)
        bridge = context["attribution"]["first_party_capture_bridge"]
        self.assertEqual(bridge["capture_records"], 1)
        self.assertFalse(bridge["contact_pii_included"])
        self.assertFalse(bridge["tracking_codes_included"])
        text = json.dumps(context, ensure_ascii=False)
        self.assertNotIn(contact["id"], text)
        self.assertNotIn("Privado", text)
        self.assertNotIn("sensitive@example.com", text)
        self.assertNotIn(self.link_a["tracking_code"], text)
        self.assertNotIn("example.com", json.dumps(bridge))


if __name__ == "__main__":
    unittest.main()
