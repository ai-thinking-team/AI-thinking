from django.test import Client, TestCase
from django.urls import reverse

from apps.coding_quiz.models import CodingExercise
from apps.learning_core.models import LearnerAttempt, LearningSession
from apps.learning_core.state_machine import WorkflowState


class ProgressRouteTests(TestCase):
    def test_dashboard_loads(self):
        self.assertEqual(self.client.get(reverse('progress:dashboard')).status_code, 200)

    def test_dashboard_and_detail_show_exercise_history(self):
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercise = CodingExercise.objects.get(slug='double-numbers')
        learning_session = LearningSession.objects.get(
            browser_session_key=browser_key,
            activity=exercise.activity,
        )
        LearnerAttempt.objects.create(
            learning_session=learning_session,
            activity=exercise.activity,
            answer='def double_numbers(values):\n    return values',
            reasoning='My preserved reasoning',
            confidence=2,
            evaluation={'status': 'FAILED'},
        )

        dashboard = self.client.get(reverse('progress:dashboard'))
        detail = self.client.get(reverse('progress:session_detail', args=(learning_session.pk,)))

        self.assertContains(dashboard, 'Double every number')
        self.assertContains(dashboard, 'Review evidence')
        self.assertContains(detail, 'def double_numbers(values)')
        self.assertContains(detail, 'My preserved reasoning')

    def test_session_detail_cannot_read_another_browser_history(self):
        exercise = CodingExercise.objects.get(slug='double-numbers')
        other = LearningSession.objects.create(
            browser_session_key='another-browser',
            topic=exercise.activity.concept.topic,
            activity=exercise.activity,
            current_state=WorkflowState.FIRST_ATTEMPT,
        )

        response = self.client.get(reverse('progress:session_detail', args=(other.pk,)))

        self.assertEqual(response.status_code, 404)

    def test_planning_evidence_is_shown_only_to_its_browser_session(self):
        exercise_url = reverse('coding_quiz:exercise_detail', args=('double-numbers',))
        self.client.post(exercise_url, {
            'action': 'plan',
            'solution_plan': 'Use a unique per-item transformation plan.',
            'predicted_output': 'unique-output-[2, 6]',
        })
        learning_session = LearningSession.objects.get(
            browser_session_key=self.client.session.session_key,
        )

        detail = self.client.get(
            reverse('progress:session_detail', args=(learning_session.pk,))
        )
        another_browser = Client()
        other_dashboard = another_browser.get(reverse('progress:dashboard'))
        other_detail = another_browser.get(
            reverse('progress:session_detail', args=(learning_session.pk,))
        )

        self.assertContains(detail, 'Use a unique per-item transformation plan.')
        self.assertContains(detail, 'unique-output-[2, 6]')
        self.assertNotContains(other_dashboard, 'unique-output-[2, 6]')
        self.assertEqual(other_detail.status_code, 404)

    def test_session_detail_renders_coach_interactions_hint_usage_and_mastery(self):
        from apps.learning_core.models import CoachInteraction, CoachLearnerResponse, ConceptMastery, HintUsage
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercise = CodingExercise.objects.get(slug='double-numbers')
        learning_session = LearningSession.objects.get(
            browser_session_key=browser_key,
            activity=exercise.activity,
        )
        attempt = LearnerAttempt.objects.create(
            learning_session=learning_session,
            activity=exercise.activity,
            answer='def double_numbers(values):\n    return values',
            reasoning='Original approach',
            confidence=3,
            evaluation={'status': 'FAILED', 'message': 'Public test failed'},
        )
        HintUsage.objects.create(
            learner_attempt=attempt,
            level=1,
            content='Think about the loop variable value.',
        )
        interaction = CoachInteraction.objects.create(
            learning_session=learning_session,
            learner_attempt=attempt,
            interaction_type=CoachInteraction.InteractionType.DIAGNOSTIC,
            source=CoachInteraction.Source.CURATED_FALLBACK,
            response={'message': 'Which value changes during iteration?'},
            failure_code='AI_UNAVAILABLE',
        )
        CoachLearnerResponse.objects.create(
            interaction=interaction,
            response='The current loop element changes.',
        )
        ConceptMastery.objects.create(
            learning_session=learning_session,
            concept=exercise.activity.concept,
            status=ConceptMastery.Status.NEEDS_REVIEW,
            reason='Transfer test failed.',
            recommendation='Review loop value binding.',
        )

        response = self.client.get(reverse('progress:session_detail', args=(learning_session.pk,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Coach Interactions')
        self.assertContains(response, 'Which value changes during iteration?')
        self.assertContains(response, 'The current loop element changes.')
        self.assertContains(response, 'Fallback code: AI_UNAVAILABLE')
        self.assertContains(response, 'Think about the loop variable value.')
        self.assertContains(response, 'Transfer test failed.')
        self.assertContains(response, 'Review loop value binding.')
