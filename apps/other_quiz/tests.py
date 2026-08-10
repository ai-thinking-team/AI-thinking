from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import OtherSubjectQuestion
from .services import can_evaluate_open_response


class OtherSubjectRouteTests(TestCase):
    def test_home_loads(self):
        self.assertEqual(self.client.get(reverse('other_quiz:home')).status_code, 200)


class RubricSafetyTests(SimpleTestCase):
    def test_open_response_without_reference_or_rubric_is_not_evaluated(self):
        question = OtherSubjectQuestion(reference_answer='', rubric={})
        self.assertFalse(can_evaluate_open_response(question))
