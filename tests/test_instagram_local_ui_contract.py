import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstagramLocalUiContractTests(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / 'web' / 'instagram-local-reel.js').read_text(encoding='utf-8')

    def test_composer_exposes_explicit_local_or_url_origin(self):
        for required in (
            'Origen del Reel',
            'Render local certificado',
            'URL pública',
            "source.value==='local'",
            'instagramLocalEligibleRenders',
            'render_id:renderId',
            'media_url:null',
        ):
            self.assertIn(required, self.js)

    def test_local_gate_matches_certified_short_form_profile(self):
        for required in (
            "row.status==='PASS'",
            'width*16===height*9',
            'width<=1920',
            'duration>=3',
            'duration<=60',
            'bytes<=1000000000',
            "name.endsWith('.mp4')",
            "name.endsWith('.mov')",
        ):
            self.assertIn(required, self.js)

    def test_browser_never_handles_meta_credentials_or_upload_uri(self):
        for forbidden in (
            'META_ACCESS_TOKEN',
            'access_token',
            'Authorization',
            'OAuth ',
            'rupload.facebook.com',
            'upload_type',
        ):
            self.assertNotIn(forbidden, self.js)
        self.assertNotIn('window.open(', self.js)

    def test_local_publication_still_requires_explicit_user_action(self):
        self.assertIn("form.addEventListener('submit'", self.js)
        self.assertIn("publish.addEventListener('click'", self.js)
        self.assertIn('createInstagramLocalPublication({publishNow:true})', self.js)
        self.assertNotIn('setInterval(createInstagramLocalPublication', self.js)
        self.assertNotIn('MutationObserver(()=>createInstagramLocalPublication', self.js)

    def test_loader_and_specialized_service_expose_bundle(self):
        uat = (ROOT / 'web' / 'social-uat.js').read_text(encoding='utf-8')
        service = (ROOT / 'src' / 'binario_marketing' / 'service_wave27.py').read_text(encoding='utf-8')
        self.assertIn("script.src='/instagram-local-reel.js'", uat)
        self.assertIn('loadInstagramLocalReelExtension', uat)
        self.assertIn('"/instagram-local-reel.js"', service)
        self.assertIn('super().do_GET()', service)
        self.assertNotIn('def do_POST', service)
        self.assertNotIn('def do_DELETE', service)


if __name__ == '__main__':
    unittest.main()
