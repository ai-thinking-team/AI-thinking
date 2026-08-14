from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.test import SimpleTestCase

from .environment import env_bool, env_csv, require_env


class EnvironmentParsingTests(SimpleTestCase):
    def test_boolean_values_are_parsed_explicitly(self):
        with patch.dict('os.environ', {'FEATURE_FLAG': 'yes'}):
            self.assertTrue(env_bool('FEATURE_FLAG'))
        with patch.dict('os.environ', {'FEATURE_FLAG': '0'}):
            self.assertFalse(env_bool('FEATURE_FLAG', True))

    def test_invalid_boolean_fails_closed(self):
        with patch.dict('os.environ', {'FEATURE_FLAG': 'sometimes'}):
            with self.assertRaises(ImproperlyConfigured):
                env_bool('FEATURE_FLAG')

    def test_csv_values_are_trimmed_and_empty_items_removed(self):
        with patch.dict('os.environ', {'HOSTS': 'example.com, api.example.com, '}):
            self.assertEqual(env_csv('HOSTS'), ['example.com', 'api.example.com'])

    def test_required_value_rejects_empty_secret(self):
        with patch.dict('os.environ', {'REQUIRED_SECRET': '  '}):
            with self.assertRaises(ImproperlyConfigured):
                require_env('REQUIRED_SECRET')


class TestSettingsIsolationTests(SimpleTestCase):
    def test_external_integrations_are_disabled(self):
        self.assertEqual(settings.AI_PROVIDER_CLASS, '')
        self.assertEqual(settings.CODE_RUNNER_URL, '')
        self.assertEqual(settings.CODE_RUNNER_GATEWAY_CLASS, '')
        self.assertFalse(settings.CODE_RUNNER_AUTOSTART)
