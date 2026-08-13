import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SocialUiContractTests(unittest.TestCase):
    def test_distribution_bundle_is_served_and_loaded_after_core_app(self):
        service = (ROOT / 'src/binario_marketing/service.py').read_text(encoding='utf-8')
        html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        self.assertIn('"/social.js"', service)
        self.assertIn('<script src="/social.js" defer></script>', html)
        self.assertLess(html.index('/app.js'), html.index('/social.js'))

    def test_distribution_workspace_exposes_publish_schedule_connection_and_paused_ads(self):
        js = (ROOT / 'web/social.js').read_text(encoding='utf-8')
        for token in (
            'Meta, publicaciones y pauta',
            'social-publication-form',
            'social-scheduled-for',
            '/api/meta/status',
            '/api/meta/pages',
            '/api/meta/ad-accounts',
            '/publications',
            '/publish-now',
            'OUTCOME_TRAFFIC',
            'OUTCOME_ENGAGEMENT',
            'OUTCOME_LEADS',
            'OUTCOME_SALES',
            'Crear campaña pausada',
            'no se guardan dentro del proyecto',
        ):
            self.assertIn(token, js)

    def test_ui_does_not_offer_paid_activation_or_local_instagram_fake_publish(self):
        js = (ROOT / 'web/social.js').read_text(encoding='utf-8')
        self.assertIn('puente automático desde renders locales', js)
        self.assertIn('No activa pauta ni genera gasto', js)
        self.assertNotIn('status:\'ACTIVE\'', js)
        self.assertNotIn('Activar campaña', js)


if __name__ == '__main__':
    unittest.main()
