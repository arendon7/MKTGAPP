import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


class EditorStartHomeContractTests(unittest.TestCase):
    def test_start_home_exposes_two_clear_entry_paths(self):
        html=(ROOT/'web/index.html').read_text(encoding='utf-8')
        for token in (
            'id="start-video-project"',
            'id="start-project-name"',
            'Crear y cargar video',
            'id="continue-recent-project"',
            'id="start-recent-projects"',
            'Whisper + FFmpeg · local',
            'Carga',
            'Transcribe',
            'Selecciona',
            'Exporta',
        ):
            self.assertIn(token,html)

    def test_start_home_reuses_canonical_project_and_quick_upload_flow(self):
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        for token in (
            'function recentProjects',
            'function renderStartHome',
            'async function createProjectAndOpen',
            "api('/api/projects',{method:'POST'",
            'await refreshProjects()',
            'await selectProject(project.id)',
            "typeof globalThis.quickUploadVideo==='function'",
            'globalThis.quickUploadVideo()',
            "$('#start-video-project').addEventListener('submit'",
            "$('#continue-recent-project').addEventListener('click'",
        ):
            self.assertIn(token,js)
        self.assertIn("String(b.created_at||'').localeCompare(String(a.created_at||''))",js)

    def test_start_home_is_responsive_not_a_second_workspace(self):
        css=(ROOT/'web/styles.css').read_text(encoding='utf-8')
        for token in (
            '.start-home{',
            '.start-home-actions{',
            '.start-recent-projects{',
            '.start-flow-explainer{',
            '@media(max-width:720px)',
        ):
            self.assertIn(token,css)
        html=(ROOT/'web/index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('id="create-project"'),1)
        self.assertEqual(html.count('id="project-list"'),1)


if __name__=='__main__':unittest.main()
