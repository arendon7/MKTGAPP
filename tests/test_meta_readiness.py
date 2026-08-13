import unittest

from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.meta_readiness import MetaReadinessService


class FakeReadinessTransport:
    def __init__(self, *, permissions=None, pages=None, ad_accounts=None):
        self.permissions = permissions or []
        self.pages = pages or []
        self.ad_accounts = ad_accounts or []
        self.calls = []

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        if url.endswith('/me/permissions'):
            return {'data': self.permissions}
        if url.endswith('/me/accounts'):
            return {'data': self.pages}
        if url.endswith('/me/adaccounts'):
            return {'data': self.ad_accounts}
        raise AssertionError(f'unexpected request {method} {url}')


def granted(*names):
    return [{'permission': name, 'status': 'granted'} for name in names]


class MetaReadinessTests(unittest.TestCase):
    def test_ready_connection_reports_facebook_instagram_and_ads_independently(self):
        fake = FakeReadinessTransport(
            permissions=granted(
                'pages_show_list', 'instagram_basic', 'instagram_content_publish',
                'pages_read_engagement', 'ads_read', 'ads_management',
            ),
            pages=[{
                'id': 'page-1',
                'name': 'Greenatics',
                'access_token': 'page-secret',
                'tasks': ['PROFILE_PLUS_CREATE_CONTENT', 'PROFILE_PLUS_MODERATE'],
                'instagram_business_account': {'id': 'ig-1', 'username': 'greenatics'},
            }],
            ad_accounts=[{
                'id': 'act_77', 'account_id': '77', 'name': 'Ads',
                'account_status': 1, 'currency': 'COP', 'timezone_name': 'America/Bogota',
            }],
        )
        client = MetaGraphClient('user-secret', 'v25.0', transport=fake)
        row = MetaReadinessService(client).diagnose()
        self.assertTrue(row['facebook']['ready'])
        self.assertTrue(row['instagram']['ready'])
        self.assertTrue(row['ads']['ready'])
        self.assertEqual(row['instagram']['accounts'][0]['username'], 'greenatics')
        encoded = repr(row)
        self.assertNotIn('user-secret', encoded)
        self.assertNotIn('page-secret', encoded)

    def test_missing_instagram_publish_permission_is_explained_without_blocking_facebook(self):
        fake = FakeReadinessTransport(
            permissions=granted('pages_show_list', 'instagram_basic', 'pages_read_engagement', 'ads_read', 'ads_management'),
            pages=[{
                'id': 'page-1', 'name': 'Greenatics', 'access_token': 'page-secret',
                'tasks': ['PROFILE_PLUS_CREATE_CONTENT'],
                'instagram_business_account': {'id': 'ig-1', 'username': 'greenatics'},
            }],
            ad_accounts=[{'id': 'act_77', 'account_id': '77', 'name': 'Ads'}],
        )
        row = MetaReadinessService(MetaGraphClient('token', transport=fake)).diagnose()
        self.assertTrue(row['facebook']['ready'])
        self.assertFalse(row['instagram']['ready'])
        self.assertIn('instagram_content_publish', row['instagram']['missing_permissions'])
        self.assertTrue(row['ads']['ready'])

    def test_ads_require_both_permissions_and_accessible_account(self):
        fake = FakeReadinessTransport(
            permissions=granted('ads_read'),
            pages=[],
            ad_accounts=[],
        )
        row = MetaReadinessService(MetaGraphClient('token', transport=fake)).diagnose()
        self.assertFalse(row['ads']['ready'])
        self.assertIn('ads_management', row['ads']['missing_permissions'])
        self.assertIn('no_ad_accounts', row['ads']['reasons'])

    def test_page_token_and_content_task_are_never_exposed_as_secret(self):
        fake = FakeReadinessTransport(
            permissions=[],
            pages=[{'id': 'page-1', 'name': 'Page', 'access_token': 'secret', 'tasks': []}],
            ad_accounts=[],
        )
        row = MetaReadinessService(MetaGraphClient('token', transport=fake)).diagnose()
        page = row['facebook']['pages'][0]
        self.assertTrue(page['has_page_token'])
        self.assertFalse(page['facebook_publish_ready'])
        self.assertIn('page_create_content_task_missing', page['facebook_reasons'])
        self.assertNotIn('access_token', page)
        self.assertNotIn('secret', repr(row))


if __name__ == '__main__':
    unittest.main()
