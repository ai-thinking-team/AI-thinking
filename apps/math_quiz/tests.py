from django.test import TestCase
from django.urls import reverse


class MathRouteTests(TestCase):
    def test_home_loads(self):
        self.assertEqual(self.client.get(reverse('math_quiz:home')).status_code, 200)
