from django.test import TestCase
from django.urls import reverse


class CoreRouteTests(TestCase):
    def test_home_lists_all_subjects(self):
        response = self.client.get(reverse('core:home'))

        self.assertEqual(response.status_code, 200)
        for label in ('Mathematics', 'Coding', 'Languages', 'Other Subjects'):
            self.assertContains(response, label)
