from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from .models import Lesson, Question, QuestionAttempt, Subject
from .services import can_evaluate_open_response


class OtherSubjectRouteTests(TestCase):
    def test_home_loads(self):
        self.assertEqual(self.client.get(reverse('other_quiz:home')).status_code, 200)


class QuestionAttemptTests(TestCase):
    """Per-browser answer history, which Question.is_correct alone cannot give
    (it is one shared flag on the question — see models.QuestionAttempt)."""

    def setUp(self):
        subject = Subject.objects.create(id='sub_test', title='History')
        lesson = Lesson.objects.create(
            id='les_test', subject=subject, chapter='1', title='Causes of WWII',
        )
        self.question = Question.objects.create(
            lesson=lesson,
            title='Trigger',
            prompt='Which event began the war in Europe?',
            q_type='MULTIPLE_CHOICE',
            options=['Invasion of Poland', 'Fall of France'],
            correct_answer='Invasion of Poland',
        )
        self.url = reverse(
            'other_quiz:lesson_detail',
            kwargs={'subject_id': subject.id, 'lesson_id': lesson.id},
        )

    def _answer(self, client, choice):
        return client.post(self.url, {
            'question_id': self.question.id,
            'action': 'submit_mc',
            f'question_{self.question.id}': choice,
        })

    def test_answering_records_the_outcome_for_this_browser(self):
        self._answer(self.client, 'Invasion of Poland')

        attempt = QuestionAttempt.objects.get(question=self.question)
        self.assertTrue(attempt.is_correct)
        self.assertEqual(attempt.browser_session_key, self.client.session.session_key)

    def test_re_answering_updates_the_same_row(self):
        self._answer(self.client, 'Fall of France')
        self._answer(self.client, 'Invasion of Poland')

        attempts = QuestionAttempt.objects.filter(question=self.question)
        self.assertEqual(attempts.count(), 1)
        self.assertTrue(attempts.first().is_correct)

    def test_each_browser_keeps_its_own_outcome(self):
        self._answer(self.client, 'Invasion of Poland')
        self._answer(Client(), 'Fall of France')

        outcomes = set(
            QuestionAttempt.objects.values_list('browser_session_key', 'is_correct')
        )
        self.assertEqual(len(outcomes), 2)
        self.assertEqual({correct for _, correct in outcomes}, {True, False})


class RubricSafetyTests(SimpleTestCase):
    def test_open_response_without_reference_or_rubric_is_not_evaluated(self):
        question = Question(correct_answer='', rubric_keywords=[])
        self.assertFalse(can_evaluate_open_response(question))
