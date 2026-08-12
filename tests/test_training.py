import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.training import load_training_source


class TrainingTests(unittest.TestCase):
    def test_jsonl_questions_are_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qa.jsonl"
            path.write_text(json.dumps({"question": "¿Qué hacemos?", "answer": "Marketing asistido por IA."}) + "\n", encoding="utf-8")
            rows = load_training_source(path)
            self.assertEqual(rows, [{"input": "¿Qué hacemos?", "output": "Marketing asistido por IA."}])

    def test_markdown_document_is_chunked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manual.md"
            path.write_text("Bloque uno.\n\nBloque dos.", encoding="utf-8")
            rows = load_training_source(path)
            self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
