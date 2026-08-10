from django.test import TestCase
from django.urls import reverse


class ProgressRouteTests(TestCase):
    def test_dashboard_loads(self):
        self.assertEqual(self.client.get(reverse('progress:dashboard')).status_code, 200)
