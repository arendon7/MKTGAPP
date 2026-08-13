import unittest
from unittest.mock import patch

from binario_marketing.meta_graph import MetaGraphClient, _default_transport


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b'{"id":"ok"}'


class MetaTransportSecurityTests(unittest.TestCase):
    def test_get_uses_authorization_header_not_query_string(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured['request'] = request
            captured['timeout'] = timeout
            return FakeResponse()

        with patch('binario_marketing.meta_graph.urlopen', side_effect=fake_urlopen):
            result = _default_transport('GET', 'https://graph.facebook.com/v25.0/me', {
                'fields': 'id,name',
                'access_token': 'super-secret',
            })
        request = captured['request']
        self.assertEqual(result['id'], 'ok')
        self.assertNotIn('super-secret', request.full_url)
        self.assertNotIn('access_token', request.full_url)
        self.assertEqual(request.get_header('Authorization'), 'Bearer super-secret')
        self.assertIn('fields=id%2Cname', request.full_url)

    def test_post_uses_authorization_header_not_form_body(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured['request'] = request
            return FakeResponse()

        with patch('binario_marketing.meta_graph.urlopen', side_effect=fake_urlopen):
            _default_transport('POST', 'https://graph.facebook.com/v25.0/page/feed', {
                'message': 'hola',
                'access_token': 'page-secret',
            })
        request = captured['request']
        body = (request.data or b'').decode('utf-8')
        self.assertNotIn('page-secret', body)
        self.assertNotIn('access_token', body)
        self.assertEqual(request.get_header('Authorization'), 'Bearer page-secret')
        self.assertEqual(body, 'message=hola')

    def test_client_rejects_unexpectedly_large_token_before_network(self):
        with self.assertRaisesRegex(ValueError, 'unexpectedly large'):
            MetaGraphClient('x' * 8193)


if __name__ == '__main__':
    unittest.main()
