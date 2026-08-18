import io
import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.ai_provider import AIGeneration
from binario_marketing.service_wave51_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


OUTPUT = {
    "summary": "Priorizar captación y ordenar el pipeline.",
    "diagnosis": ["Hay una campaña lista para profundizar."],
    "recommendations": [{
        "title": "Probar dos ángulos",
        "why": "Permite comparar propuesta de valor.",
        "priority": "HIGH",
        "area": "CREATIVE",
        "next_step": "Crear dos variantes de copy.",
    }],
    "creative_variants": [{
        "label": "Beneficio",
        "copy": "Copy sugerido",
        "headline": "Headline sugerido",
        "cta": "LEARN_MORE",
    }],
    "campaign_brief": {
        "objective": "Leads cualificados",
        "audience": "Audiencia objetivo",
        "proposition": "Propuesta",
        "channels": ["Instagram"],
        "kpis": ["CPL"],
        "notes": "Validar semanalmente",
    },
}


class FakeAIClient:
    def __init__(self):
        self.calls = []

    def generate(self, provider, model, *, system, prompt):
        self.calls.append({"provider": provider, "model": model, "system": system, "prompt": prompt})
        return AIGeneration(
            provider=provider,
            model=model,
            output=OUTPUT,
            provider_meta={"response_id": "resp_test", "api_key": "must-not-persist"},
        )


class Wave51AIRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.contact = self.runtime.create_contact(self.company["id"], {
            "name": "Persona Secreta",
            "email": "pii@example.com",
            "phone": "+57 300 123 4567",
            "whatsapp": "+57 300 123 4567",
        })
        raw = b"\x89PNG\r\n\x1a\nwave51"
        self.media = self.runtime.upload_company_media(
            self.company["id"], "creative.png", "image", io.BytesIO(raw), len(raw)
        )
        self.campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Captación Q3",
            "objective": "LEADS",
            "status": "READY",
            "channels": ["instagram"],
            "media_ids": [self.media["id"]],
            "notes": "Campaña de captación",
        })
        self.runtime.upsert_company_creative(self.company["id"], self.media["id"], {
            "title": "Creative Leads",
            "stage": "READY",
            "purpose": "LEADS",
            "campaign_id": self.campaign["id"],
            "channels": ["instagram", "paid_media"],
            "primary_copy": "Copy original",
            "headline": "Headline original",
            "call_to_action": "LEARN_MORE",
            "destination_url": "https://example.com/leads",
            "notes": "Hipótesis creativa",
        })
        self.runtime.update_ai_settings(self.company["id"], {
            "provider": "ollama",
            "model": "local-test-model",
            "language": "es",
            "brand_voice": "Claro, técnico y sin exageraciones.",
        })
        self.fake = FakeAIClient()
        self.runtime.ai_client = self.fake

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_context_excludes_contact_pii_media_bytes_and_provider_secrets(self):
        context = self.runtime._ai_context(
            self.company["id"],
            task="CREATIVE",
            campaign_id=self.campaign["id"],
            creative_media_id=self.media["id"],
        )
        text = json.dumps(context, ensure_ascii=False)
        self.assertIn("Greenatics", text)
        self.assertIn("Copy original", text)
        self.assertIn("Captación Q3", text)
        self.assertNotIn("Persona Secreta", text)
        self.assertNotIn("pii@example.com", text)
        self.assertNotIn("300 123 4567", text)
        self.assertNotIn("api_key", text.lower())
        self.assertNotIn("access_token", text.lower())
        self.assertNotIn("media_bytes", text.replace('"media_bytes_included": false', ''))
        self.assertFalse(context["privacy"]["contact_pii_included"])
        self.assertFalse(context["privacy"]["media_bytes_included"])
        self.assertFalse(context["privacy"]["provider_secrets_included"])
        self.assertEqual(context["crm"]["contacts"], 1)

    def test_generation_records_hash_provider_model_and_does_not_mutate_marketing_state(self):
        before = self.runtime.creatives.get(self.company["id"], self.media["id"])
        self.runtime.publish_company_publication_now = lambda *a, **k: (_ for _ in ()).throw(AssertionError("publish called"))
        self.runtime.create_company_paid_media_remote_paused = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ads mutation called"))
        self.runtime.social_analytics_meta = lambda *a, **k: (_ for _ in ()).throw(AssertionError("remote analytics called"))

        result = self.runtime.generate_ai_copilot(self.company["id"], {
            "task": "CREATIVE",
            "campaign_id": self.campaign["id"],
            "creative_media_id": self.media["id"],
            "instruction": "Dame variantes con foco en leads.",
        })
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["model"], "local-test-model")
        self.assertEqual(result["task"], "CREATIVE")
        self.assertEqual(result["output"]["summary"], OUTPUT["summary"])
        self.assertRegex(result["context_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["provider_meta"], {"response_id": "resp_test"})
        self.assertNotIn("must-not-persist", json.dumps(result))
        self.assertEqual(len(self.fake.calls), 1)
        call = self.fake.calls[0]
        self.assertIn("cannot publish", call["system"])
        self.assertNotIn("Persona Secreta", call["prompt"])
        self.assertNotIn("pii@example.com", call["prompt"])

        after = self.runtime.creatives.get(self.company["id"], self.media["id"])
        self.assertEqual(before, after)
        self.assertEqual(self.runtime.social.list(self.company["id"]), [])
        self.assertEqual(self.runtime.company_paid_media(self.company["id"]), [])
        sessions = self.runtime.ai_sessions.list(self.company["id"])
        self.assertEqual(sessions[0].id, result["id"])
        self.assertEqual(sessions[0].context_sha256, result["context_sha256"])

    def test_campaign_and_creative_tasks_require_explicit_entity(self):
        with self.assertRaisesRegex(ValueError, "campaign_id"):
            self.runtime.generate_ai_copilot(self.company["id"], {"task": "CAMPAIGN"})
        with self.assertRaisesRegex(ValueError, "creative_media_id"):
            self.runtime.generate_ai_copilot(self.company["id"], {"task": "CREATIVE"})

    def test_prompt_includes_brand_voice_and_no_tool_authority(self):
        context = self.runtime._ai_context(
            self.company["id"], task="STRATEGY", campaign_id=None, creative_media_id=None
        )
        system, prompt = self.runtime._ai_prompt(
            task="STRATEGY",
            context=context,
            instruction="Prioriza tres acciones.",
            language="es",
            brand_voice="Claro, técnico y sin exageraciones.",
        )
        self.assertIn("Claro, técnico", system)
        self.assertIn("cannot publish", system)
        self.assertIn("cannot", system)
        self.assertIn("Additional user instruction", prompt)
        self.assertNotIn("pii@example.com", prompt)


if __name__ == "__main__":
    unittest.main()
