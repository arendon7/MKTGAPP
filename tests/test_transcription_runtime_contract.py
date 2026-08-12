import re
import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


class TranscriptionRuntimeContractTests(unittest.TestCase):
    def test_runtime_pin_is_exact_and_multilingual(self):
        text=(ROOT/'scripts/full_mac_transcription_runtime.env').read_text(encoding='utf-8')
        values=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
        self.assertEqual(values['WHISPER_REPOSITORY'],'https://github.com/ggml-org/whisper.cpp.git')
        self.assertRegex(values['WHISPER_COMMIT'],r'^[0-9a-f]{40}$')
        self.assertEqual(values['WHISPER_MODEL_NAME'],'ggml-tiny.bin')
        self.assertRegex(values['WHISPER_MODEL_SHA256'],r'^[0-9a-f]{64}$')
        self.assertGreater(int(values['WHISPER_MODEL_BYTES']),10_000_000)

    def test_builder_disables_runner_native_cpu_and_verifies_model(self):
        script=(ROOT/'scripts/build_embedded_whisper.sh').read_text(encoding='utf-8')
        for token in ('-DGGML_NATIVE=OFF','-DGGML_METAL=OFF','WHISPER_COMMIT','WHISPER_MODEL_SHA256','otool -L','whisper-cli','RUNTIME.json'):
            self.assertIn(token,script)

    def test_full_mac_builder_packages_transcription_runtime(self):
        builder=(ROOT/'scripts/build_full_mac_app.sh').read_text(encoding='utf-8')
        self.assertIn('build_embedded_whisper.sh',builder)
        self.assertIn('runtime/transcription',builder)

    def test_native_gate_audits_and_executes_offline_transcription(self):
        workflow=(ROOT/'.github/workflows/full-mac-app.yml').read_text(encoding='utf-8')
        self.assertIn('audit_embedded_whisper.sh',workflow)
        self.assertIn('smoke_full_mac_transcription.sh',workflow)
        self.assertIn('full-mac-whisper',workflow)
        smoke=(ROOT/'scripts/smoke_full_mac_transcription.sh').read_text(encoding='utf-8')
        self.assertIn('/usr/bin/say',smoke)
        self.assertIn('/transcription/segments',smoke)
        self.assertIn('/transcription/clips',smoke)
        self.assertIn('offline transcription -> transcript -> automatic Clipper',smoke)

    def test_source_runtime_resolves_embedded_bundle_before_external_path(self):
        source=(ROOT/'src/binario_marketing/video/transcription.py').read_text(encoding='utf-8')
        self.assertIn('runtime/transcription/bin/whisper-cli',source)
        self.assertIn('runtime/transcription/models',source)
        self.assertIn('BINARIO_WHISPER_CLI',source)
        self.assertIn('BINARIO_WHISPER_MODEL',source)


if __name__=='__main__':unittest.main()
