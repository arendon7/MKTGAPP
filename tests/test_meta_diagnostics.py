import unittest
from unittest.mock import patch

from binario_marketing.meta_graph import MetaGraphClient, MetaGraphError
from binario_marketing.meta_diagnostics import MetaDiagnostics, _page_capabilities


class FakeTransport:
    def __init__(self, *, missing=(), no_instagram=False, permissions_error=False):
        self.calls = []
        self.missing = set(missing)
        self.no_instagram = no_instagram
        self.permissions_error = permissions_error

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        path = url.split('/v25.0/', 1)[-1]
        if path == 'me':
            return {'id': 'user-1', 'name': 'UAT User'}
        if path == 'me/permissions':
            if self.permissions_error:
                raise MetaGraphError('Meta permissions inventory unavailable')
            expected = {
                'pages_show_list', 'instagram_basic', 'instagram_content_publish',
                'pages_read_engagement', 'instagram_manage_insights', 'ads_read', 'ads_management',
            }
            return {'data': [
                {'permission': name, 'status': 'declined' if name in self.missing else 'granted'}
                for name in sorted(expected)
            ]}
        if path == 'me/accounts':
            row = {
                'id': 'page-1', 'name': 'Page One',
                'tasks': ['PROFILE_PLUS_CREATE_CONTENT', 'PROFILE_PLUS_ANALYZE', 'PROFILE_PLUS_ADVERTISE'],
            }
            if not self.no_instagram:
                row['instagram_business_account'] = {'id': 'ig-1', 'username': 'igone'}
            return {'data': [row]}
        if path == 'me/adaccounts':
            return {'data': [{
                'id': 'act_77', 'account_id': '77', 'name': 'Ads One', 'account_status': 1,
                'currency': 'COP', 'timezone_name': 'America/Bogota',
            }]}
        raise AssertionError(f'unexpected path {path}')


def client(transport):
    return MetaGraphClient('user-secret', 'v25.0', transport=transport)


class MetaDiagnosticsTests(unittest.TestCase):
    def test_page_full_control_inherits_all_uat_capabilities(self):
        capabilities = _page_capabilities(['PROFILE_PLUS_FULL_CONTROL'])
        self.assertEqual(capabilities, {'create_content': True, 'analyze': True, 'advertise': True})

    @patch('binario_marketing.meta_diagnostics.MetaCredentialStore.status')
    def test_full_capability_report_is_read_only_and_secret_free(self, status):
        status.return_value = type('S', (), {'source': 'keychain'})()
        transport = FakeTransport()
        report = MetaDiagnostics(client(transport)).report()
        self.assertEqual(report['status'], 'PASS')
        self.assertTrue(report['ready']['facebook_publish'])
        self.assertTrue(report['ready']['instagram_publish'])
        self.assertTrue(report['ready']['instagram_insights'])
        self.assertTrue(report['ready']['ads_read'])
        self.assertTrue(report['ready']['ads_create'])
        self.assertTrue(report['permissions']['available'])
        self.assertEqual(report['permissions']['missing']['instagram_publish'], [])
        self.assertFalse(report['security']['token_included'])
        self.assertFalse(report['security']['mutation_performed'])
        self.assertNotIn('user-secret', str(report))
        self.assertTrue(all(method == 'GET' for method, _, _ in transport.calls))

    @patch('binario_marketing.meta_diagnostics.MetaCredentialStore.status')
    def test_declined_permissions_are_mapped_to_specific_flows(self, status):
        status.return_value = type('S', (), {'source': 'keychain'})()
        report = MetaDiagnostics(client(FakeTransport(missing={'instagram_content_publish', 'ads_management'}))).report()
        self.assertFalse(report['ready']['instagram_publish'])
        self.assertTrue(report['ready']['instagram_insights'])
        self.assertTrue(report['ready']['ads_read'])
        self.assertFalse(report['ready']['ads_create'])
        self.assertEqual(report['permissions']['missing']['instagram_publish'], ['instagram_content_publish'])
        self.assertEqual(report['permissions']['missing']['ads_create'], ['ads_management'])
        permission_check = next(row for row in report['checks'] if row['id'] == 'permissions')
        self.assertEqual(permission_check['state'], 'WARN')

    @patch('binario_marketing.meta_diagnostics.MetaCredentialStore.status')
    def test_missing_professional_instagram_link_is_actionable(self, status):
        status.return_value = type('S', (), {'source': 'keychain'})()
        report = MetaDiagnostics(client(FakeTransport(no_instagram=True))).report()
        self.assertTrue(report['ready']['facebook_publish'])
        self.assertFalse(report['ready']['instagram_publish'])
        row = next(item for item in report['checks'] if item['id'] == 'instagram_link')
        self.assertEqual(row['state'], 'WARN')
        self.assertIn('Business/Creator', row['action'])

    @patch('binario_marketing.meta_diagnostics.MetaCredentialStore.status')
    def test_permissions_inventory_failure_does_not_hide_functional_capabilities(self, status):
        status.return_value = type('S', (), {'source': 'environment'})()
        report = MetaDiagnostics(client(FakeTransport(permissions_error=True))).report()
        self.assertFalse(report['permissions']['available'])
        self.assertTrue(report['ready']['instagram_publish'])
        self.assertTrue(report['ready']['ads_create'])
        row = next(item for item in report['checks'] if item['id'] == 'permissions')
        self.assertEqual(row['state'], 'WARN')


if __name__ == '__main__':
    unittest.main()
