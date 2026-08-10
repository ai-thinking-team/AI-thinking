from django.test import TestCase


class DemoRouteTests(TestCase):
    def test_required_routes_load(self):
        for route in ('/', '/math/', '/coding/', '/languages/', '/other-subjects/', '/progress/'):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)
