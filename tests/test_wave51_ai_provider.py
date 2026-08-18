import json
import unittest

from binario_marketing.ai_provider import AIProviderClient, AIProviderError, normalize_copilot_output


OUTPUT = {
    "summary": "Resumen",
    "diagnosis": ["Hallazgo"],
    "recommendations": [{
        "title": "Prioridad",
        "why": "Razón",
        "priority": "HIGH",
        "area": "STRATEGY",
        "next_step": "Ejecutar siguiente paso",
    }],
    "creative_variants": [{"label": "A", "copy": "Copy", "headline": "Hook", "cta": "LEARN_MORE"}],
    "campaign_brief": {
        "objective": "Leads",
        "audience": "Segmento",
        "proposition": "Valor",
        "channels": ["Instagram"],
        "kpis": ["CPL"],
        "notes": "Nota",
    },
}


class FakeCredentials:
    def read(self, provider):
        return f"secret-{provider}"


class Wave51AIProviderTests(unittest.TestCase):
    def capture_client(self, response):
        calls = []
        def transport(method, url, headers, payload):
            calls.append((method, url, headers, payload))
            return response
        return AIProviderClient(FakeCredentials(), transport), calls

    def test_openai_responses_uses_strict_json_schema_without_tools(self):
        client, calls = self.capture_client({
            "id": "resp_1",
            "status": "completed",
            "output": [{"content": [{"type": "output_text", "text": json.dumps(OUTPUT)}]}],
        })
        result = client.generate("openai", "gpt-test", system="system", prompt="prompt")
        self.assertEqual(result.output["summary"], "Resumen")
        method, url, headers, payload = calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer secret-openai")
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("secret-openai", json.dumps(payload))

    def test_anthropic_messages_uses_text_only_and_no_tools(self):
        client, calls = self.capture_client({
            "id": "msg_1",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": json.dumps(OUTPUT)}],
        })
        result = client.generate("anthropic", "claude-test", system="system", prompt="prompt")
        self.assertEqual(result.provider, "anthropic")
        _, url, headers, payload = calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers["x-api-key"], "secret-anthropic")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("tools", payload)
        self.assertNotIn("secret-anthropic", json.dumps(payload))

    def test_gemini_generate_content_uses_key_header_and_json_response_mode(self):
        client, calls = self.capture_client({
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": json.dumps(OUTPUT)}]},
            }],
        })
        result = client.generate("gemini", "gemini-test", system="system", prompt="prompt")
        self.assertEqual(result.output["campaign_brief"]["objective"], "Leads")
        _, url, headers, payload = calls[0]
        self.assertTrue(url.endswith("/models/gemini-test:generateContent"))
        self.assertEqual(headers["x-goog-api-key"], "secret-gemini")
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertNotIn("tools", payload)
        self.assertNotIn("secret-gemini", json.dumps(payload))

    def test_ollama_is_local_json_chat_without_tools(self):
        class NoSecretCredentials:
            def read(self, provider):
                raise AssertionError("Ollama should not read a cloud key")
        calls = []
        def transport(method, url, headers, payload):
            calls.append((method, url, headers, payload))
            return {"message": {"content": json.dumps(OUTPUT)}, "done_reason": "stop"}
        client = AIProviderClient(NoSecretCredentials(), transport)
        result = client.generate("ollama", "local-model", system="system", prompt="prompt")
        self.assertEqual(result.provider, "ollama")
        _, url, _, payload = calls[0]
        self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["format"], "json")
        self.assertNotIn("tools", payload)

    def test_malformed_or_overwide_output_is_fail_closed_or_normalized(self):
        with self.assertRaises(AIProviderError):
            client, _ = self.capture_client({"content": [{"type": "text", "text": "not-json"}]})
            client.generate("anthropic", "model", system="system", prompt="prompt")
        normalized = normalize_copilot_output({
            "summary": "x" * 3000,
            "recommendations": [{"title": "t", "why": "w", "priority": "INVALID", "area": "OTHER", "next_step": "n"}],
            "creative_variants": [{"copy": "copy", "cta": "CTA"}] * 10,
        })
        self.assertEqual(len(normalized["summary"]), 1800)
        self.assertEqual(normalized["recommendations"][0]["priority"], "MEDIUM")
        self.assertEqual(normalized["recommendations"][0]["area"], "STRATEGY")
        self.assertEqual(len(normalized["creative_variants"]), 5)


if __name__ == "__main__":
    unittest.main()
