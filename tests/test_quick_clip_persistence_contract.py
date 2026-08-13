import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


class QuickClipPersistenceContractTests(unittest.TestCase):
    def test_local_api_exposes_project_scoped_quick_clip_state(self):
        source=(ROOT/'src/binario_marketing/service.py').read_text(encoding='utf-8')
        for token in (
            '"quick_clips": selection_for_project(self, project_id)',
            'save_selection(self.server.runtime, parts[2], payload)',
            'clear_selection(self.server.runtime, parts[2], reason="user")',
            'clear_selection_for_asset(self, project_id, asset_id)',
            'reason="transcription_started"',
        ):
            self.assertIn(token,source)

    def test_browser_restores_and_persists_selection(self):
        js=(ROOT/'web/clipper-modes.js').read_text(encoding='utf-8')
        for token in (
            'quickSelectionUrl',
            'quickApplySavedSelection',
            'quickPersistSelection',
            'quickClearPersistedSelection',
            'state.current.quick_clips',
            "method:'POST'",
            "method:'DELETE'",
            'selectionConfig',
            'Selección recuperada',
            'La selección queda guardada en el proyecto',
        ):
            self.assertIn(token,js)

    def test_transcript_sha_is_server_canonical_not_browser_supplied(self):
        service=(ROOT/'src/binario_marketing/quick_clip_service.py').read_text(encoding='utf-8')
        self.assertIn('canonical["transcript_sha256"] = transcript.transcript_sha256',service)
        self.assertIn('transcript.transcript_sha256 != row.transcript_sha256',service)
        js=(ROOT/'web/clipper-modes.js').read_text(encoding='utf-8')
        persist=js[js.index('async function quickPersistSelection'):js.index('async function quickClearPersistedSelection')]
        self.assertNotIn('transcript_sha256',persist)


if __name__=='__main__':unittest.main()
