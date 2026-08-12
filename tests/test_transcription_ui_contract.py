import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


class TranscriptionUiContractTests(unittest.TestCase):
    def test_transcription_bundle_is_loaded_and_served_locally(self):
        html=(ROOT/'web/index.html').read_text(encoding='utf-8')
        service=(ROOT/'src/binario_marketing/service.py').read_text(encoding='utf-8')
        self.assertIn('<script src="/transcription.js" defer></script>',html)
        self.assertIn('"/transcription.js"',service)

    def test_ui_supports_transcribe_status_manual_and_direct_clipper(self):
        js=(ROOT/'web/transcription.js').read_text(encoding='utf-8')
        for token in ('Transcribir','Transcribiendo localmente','Pasar al Clipper manual','Elegir mejores clips','/segments','/clips','startTranscription','cancelTranscription','selectClipsFromTranscript','auto-clipper'):
            self.assertIn(token,js)

    def test_api_contract_has_managed_transcript_routes(self):
        service=(ROOT/'src/binario_marketing/service.py').read_text(encoding='utf-8')
        for token in ('TranscriptionManager','transcriptions','[\"transcription\", \"segments\"]','[\"transcription\", \"file\"]','[\"transcription\", \"clips\"]'):
            self.assertIn(token,service)


if __name__=='__main__':unittest.main()
