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
            'quickStartRender',
            'transcriptionUrl(asset.id',
            "'/clips'",
            "action:'add_clip'",
            'Natural · idea completa',
            'Duración objetivo',
            'quick-aspect',
            "const start=Number(clip.start),end=Number(clip.end),aspect=$('#quick-aspect')?.value||'9:16'",
            'body:{asset_id:asset.id,start,end,label,aspect}',
            'Vertical 9:16 · Reels / TikTok',
            'Abrir editor avanzado',
        ):
            self.assertIn(token,js)
        self.assertNotIn("startRender({asset_id:asset.id,start,end,aspect:",js)

    def test_quick_render_jobs_are_visible_and_actionable_in_clip_cards(self):
        js=(ROOT/'web/clipper-modes.js').read_text(encoding='utf-8')
        for token in (
            'quickRenderJob',
            'quickRenderStatus',
            'quick-render-state',
            "ACTIVE_RENDERS.has(job.status)",
            'cancelRender(job.id)',
            "href=`/api/renders/${job.id}/file`",
            "link.download=job.output_name",
            'Exportar de nuevo',
            'quickBaseRenderRenders',
        ):
            self.assertIn(token,js)

    def test_bulk_actions_are_duplicate_safe_and_serial(self):
        js=(ROOT/'web/clipper-modes.js').read_text(encoding='utf-8')
        for token in (
            'quick-add-all-timeline',
            'quick-export-all',
            'quickClipOnTimeline',
            'quickAddAllTimeline',
            'quickExportAll',
            'quickWaitRender',
            "state.quickFlow.bulkMode='timeline'",
            "state.quickFlow.bulkMode='export'",
            'un render a la vez',
            'Detener después del actual',
            'Todos los clips ya estaban en Track 0.',
        ):
            self.assertIn(token,js)
        export_body=js[js.index('async function quickExportAll'):js.index('function renderQuickResults')]
        self.assertIn('for(let index=0;index<clips.length;index++)',export_body)
        self.assertIn('await quickWaitRender(job.id,projectId)',export_body)
        self.assertNotIn('Promise.all',export_body)

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
        service_core=(ROOT/'src/binario_marketing/service_core.py').read_text(encoding='utf-8')
        workflow=(ROOT/'.github/workflows/full-mac-app.yml').read_text(encoding='utf-8')
        self.assertIn('"/clipper-modes.js"',service+service_core)
        self.assertIn('"$BASE/clipper-modes.js"',workflow)
        self.assertIn("grep -q 'clipperModePayload'",workflow)

    def test_quick_flow_has_responsive_workspace_styles(self):
        css=(ROOT/'web/styles.css').read_text(encoding='utf-8')
        for token in ('.quick-editor-panel','.quick-flow-grid','.quick-step.active','.quick-clip-card','@media(max-width:720px)'):
            self.assertIn(token,css)


if __name__=='__main__':unittest.main()
