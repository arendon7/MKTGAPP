import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SequenceUiContractTests(unittest.TestCase):
    def test_browser_exposes_track_zero_master_and_reorder_controls(self):
        js = (ROOT / "web/pro-media.js").read_text(encoding="utf-8")
        for token in (
            "sequence-master-bar",
            "Track 0",
            "Exportar master",
            "renders/sequence",
            "action:'reorder'",
            "direction:-1",
            "direction:1",
            "MASTER ·",
            "job.kind==='sequence'",
            "job.clip_ids",
        ):
            self.assertIn(token, js)

    def test_sequence_backend_is_separate_from_http_transport(self):
        service = (ROOT / "src/binario_marketing/service.py").read_text(encoding="utf-8")
        sequence_service = (ROOT / "src/binario_marketing/sequence_service.py").read_text(encoding="utf-8")
        self.assertIn("from .sequence_service import start_sequence_render", service)
        self.assertIn('parts[3:] == ["renders", "sequence"]', service)
        self.assertIn("track = int(payload.get(\"track\", 0))", sequence_service)
        self.assertIn("runtime.renders.start_sequence", sequence_service)


if __name__ == "__main__":
    unittest.main()
