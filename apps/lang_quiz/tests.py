from django.test import TestCase
from django.urls import reverse


class LanguageRouteTests(TestCase):
    def test_home_loads(self):
        self.assertEqual(self.client.get(reverse('lang_quiz:home')).status_code, 200)
