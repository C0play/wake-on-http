from urllib.parse import urlparse
from unittest.mock import patch
import unittest
import os

from src.main import app
from src.service import ServiceFactory


class BaseAppTest(unittest.TestCase):
    """Shared helpers for Flask requests that depend on ServiceFactory."""

    def setUp(self):
        self.app = app.test_client()
        self._tracked_env = []

    def tearDown(self):
        for key in self._tracked_env:
            os.environ.pop(key, None)

    def register_service_config(self, service_name: str, config_filename: str) -> None:
        env_key = f"{service_name.upper()}_CFG"
        os.environ[env_key] = config_filename
        self._tracked_env.append(env_key)
        ServiceFactory.load_all()

    def find_service_by_config(self, config_path: str):
        abs_config_path = os.path.abspath(config_path)
        for svc in ServiceFactory._service_registry._services.values():
            if svc.cfg.file_metadata.path == abs_config_path:
                return svc
        return None


class MockHostTests(BaseAppTest):
    """Behaviors when the mock service defined in mock.yml handles requests."""

    @classmethod
    def setUpClass(cls):
        os.environ['MOCK_CFG'] = 'mock.yml'
        ServiceFactory.load_all()

    @classmethod
    def tearDownClass(cls):
        if 'MOCK_CFG' in os.environ:
            del os.environ['MOCK_CFG']

    @patch('src.utils.check_status')
    @patch('src.utils.wake')
    def test_mock_host_wake(self, mock_wake, mock_check_status):
        mock_check_status.return_value = False
        response = self.app.get('/', headers={'Host': 'mock.local'})

        mock_check_status.assert_called()
        mock_wake.assert_called()

        self.assertEqual(response.status_code, 202)
        self.assertIn(b"Waking", response.data)

    @patch('src.utils.check_status')
    @patch('src.utils.wake')
    def test_mock_host_online(self, mock_wake, mock_check_status):
        mock_check_status.return_value = True
        response = self.app.get('/', headers={'Host': 'mock.local'})

        mock_check_status.assert_called()
        mock_wake.assert_not_called()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'http://mock.local:8096')

    @patch('src.utils.check_status')
    def test_mock_host_ignored_path(self, mock_check_status):
        mock_check_status.return_value = False
        response = self.app.get('/ignore/me/something', headers={'Host': 'mock.local'})

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"background sync ignored", response.data)


class TemplateRenderingTests(BaseAppTest):
    """Ensure each HTML template renders once its config is registered."""

    @patch('src.utils.check_status')
    @patch('src.utils.wake')
    def test_serve_html_templates(self, mock_wake, mock_check_status):
        mock_check_status.return_value = False
        templates_dir = os.path.join(os.path.dirname(__file__), '../templates')
        configs_dir = os.path.join(os.path.dirname(__file__), '../configs')

        for filename in os.listdir(templates_dir):
            if not filename.endswith('.html'):
                continue

            service_name = filename[:-5]
            config_filename = f"{service_name}.yml"
            config_path = os.path.join(configs_dir, config_filename)

            if not os.path.exists(config_path):
                print(f"Skipping {service_name} - no matching config found in {configs_dir}")
                continue

            self.register_service_config(service_name, config_filename)
            target_service = self.find_service_by_config(config_path)

            self.assertIsNotNone(target_service, f"Service {service_name} not loaded! Check logs.")
            assert target_service is not None, f"Service {service_name} not loaded! Check logs."
            hostname = urlparse(target_service.cfg.APP_URL).hostname

            response = self.app.get('/', headers={
                'Host': hostname,
                'Accept': 'text/html'
            })

            self.assertEqual(response.status_code, 202, f"Failed for {service_name}")
            self.assertIn('text/html', response.content_type)


class ServiceResolutionTests(BaseAppTest):
    """Additional scenarios that rely on a known mock service being available."""

    @classmethod
    def setUpClass(cls):
        os.environ['MOCK_CFG'] = 'mock.yml'
        ServiceFactory.load_all()

    @classmethod
    def tearDownClass(cls):
        if 'MOCK_CFG' in os.environ:
            del os.environ['MOCK_CFG']

    def test_service_not_found(self):
        response = self.app.get('/', headers={'Host': 'invalid.host.com'})
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Service not found", response.data)
    
    def test_preview_route(self):
        # Test preview with existing and non-existing template
        # "jellyfin" seems to exist based on file list.
        response = self.app.get('/preview/jellyfin')
        self.assertEqual(response.status_code, 200)
        
        response = self.app.get('/preview/nonexistent')
        self.assertEqual(response.status_code, 200) # Should fallback to default

    @patch('src.utils.check_status')
    def test_json_response(self, mock_check_status):
        mock_check_status.return_value = False
        # No Accept: text/html header
        response = self.app.get('/', headers={'Host': 'mock.local', 'Accept': 'application/json'})
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.is_json)
        data = response.get_json()
        self.assertIn('message', data)
        self.assertEqual(data['service_name'], 'mock')

    @patch('src.utils.check_status')
    def test_internal_error(self, mock_check_status):
        mock_check_status.side_effect = Exception("Boom!")
        response = self.app.get('/', headers={'Host': 'mock.local'})
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Internal error", response.data)

    def test_hostname_mismatch(self):
        # jellyfin is registered for jellyfin.blazejjakubowski.com
        # We try to access it via jellyfin.wrong.com
        response = self.app.get('/', headers={'Host': 'jellyfin.wrong.com'})
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Service not found", response.data)
    
    def test_hostname_substring(self):
        # jellyfin is registered for jellyfin.blazejjakubowski.com
        # We try to access it via jellyfin.wrong.com
        response = self.app.get('/', headers={'Host': 'jellyfin.wrong.com.ru'})
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Service not found", response.data)


if __name__ == '__main__':
    unittest.main()
