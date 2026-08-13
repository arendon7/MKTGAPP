import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


class EditorQuickFlowContractTests(unittest.TestCase):
    def test_quick_flow_orchestrates_existing_certified_engines(self):
        js=(ROOT/'web/clipper-modes.js').read_text(encoding='utf-8')
        for token in (
            'ensureQuickEditorPanel',
            'quickUploadVideo',
            'quickStartTranscription',
            'quickGenerateClips',
            'transcriptionUrl(asset.id',
            "'/clips'",
            "action:'add_clip'",
            'startRender',
            'Natural · idea completa',
            'Duración objetivo',
            'Abrir editor avanzado',
        ):
            self.assertIn(token,js)

    def test_quick_flow_is_loaded_after_transcription_and_keeps_manual_mode(self):
        html=(ROOT/'web/index.html').read_text(encoding='utf-8')
        self.assertIn('/transcription.js',html)
        self.assertIn('/clipper-modes.js',html)
        self.assertLess(html.index('/transcription.js'),html.index('/clipper-modes.js'))
        js=(ROOT/'web/clipper-modes.js').read_text(encoding='utf-8')
        self.assertIn('deemphasizeManualClipper',js)
        self.assertIn('Clipper manual',js)
        self.assertIn('clipperModePayload',js)

    def test_quick_flow_bundle_is_part_of_native_full_mac_smoke(self):
        service=(ROOT/'src/binario_marketing/service.py').read_text(encoding='utf-8')
        workflow=(ROOT/'.github/workflows/full-mac-app.yml').read_text(encoding='utf-8')
        self.assertIn('"/clipper-modes.js"',service)
        self.assertIn('"$BASE/clipper-modes.js"',workflow)
        self.assertIn("grep -q 'clipperModePayload'",workflow)

    def test_quick_flow_has_responsive_workspace_styles(self):
        css=(ROOT/'web/styles.css').read_text(encoding='utf-8')
        for token in ('.quick-editor-panel','.quick-flow-grid','.quick-step.active','.quick-clip-card','@media(max-width:720px)'):
            self.assertIn(token,css)


if __name__=='__main__':unittest.main()
