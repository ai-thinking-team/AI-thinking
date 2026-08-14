import json

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.coding_quiz.models import CodingExercise
from apps.learning_core.models import (
    CoachInteraction,
    ConceptMastery,
    HintUsage,
    LearnerAttempt,
    LearningSession,
    MisconceptionRecord,
    TeachBackAttempt,
    TransferAttempt,
)
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
        self.assertContains(dashboard, 'Review full evidence')
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
        from apps.learning_core.models import CoachLearnerResponse
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
        self.assertContains(response, 'Coach interactions')
        self.assertContains(response, 'Which value changes during iteration?')
        self.assertContains(response, 'The current loop element changes.')
        self.assertContains(response, 'Fallback code: AI_UNAVAILABLE')
        self.assertContains(response, 'Think about the loop variable value.')
        self.assertContains(response, 'Transfer test failed.')
        self.assertContains(response, 'Review loop value binding.')

    def test_dashboard_summarizes_coding_evidence_and_uses_fixed_query_count(self):
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercises = CodingExercise.objects.select_related('activity__concept').filter(
            slug__in=('double-numbers', 'square-numbers', 'increment-numbers')
        )
        for exercise in exercises:
            session, _ = LearningSession.objects.get_or_create(
                browser_session_key=browser_key,
                topic=exercise.activity.concept.topic,
                activity=exercise.activity,
            )
            attempt = LearnerAttempt.objects.create(
                learning_session=session,
                activity=exercise.activity,
                answer='def attempt():\n    return []',
                reasoning='A recorded approach.',
                confidence=2,
                revision_number=0,
                evaluation={'status': 'FAILED'},
            )
            LearnerAttempt.objects.create(
                learning_session=session,
                activity=exercise.activity,
                answer='def attempt():\n    return [1]',
                reasoning='A revised approach.',
                confidence=4,
                revision_number=1,
                evaluation={'status': 'PASSED'},
            )
            HintUsage.objects.create(learner_attempt=attempt, level=2, content='A stored hint.')
        double = exercises.get(slug='double-numbers')
        double_session = LearningSession.objects.get(
            browser_session_key=browser_key, activity=double.activity
        )
        MisconceptionRecord.objects.create(
            learning_session=double_session,
            concept=double.activity.concept,
            code='loop-value-misuse',
            evidence='The learner still applies the operation to the whole list.',
            status=MisconceptionRecord.Status.CONFIRMED,
        )
        ConceptMastery.objects.create(
            learning_session=double_session,
            concept=double.activity.concept,
            status=ConceptMastery.Status.NEEDS_REVIEW,
            reason='The Transfer Check did not pass.',
            recommendation='Review one current loop value at a time.',
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('progress:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 8)
        self.assertContains(response, 'Sessions')
        self.assertContains(response, '<strong>3</strong>', html=True)
        self.assertContains(response, '2/5 → 4/5')
        self.assertContains(response, 'Level 2')
        self.assertContains(response, 'loop-value-misuse')
        self.assertContains(response, 'Review one current loop value at a time.')

    def test_detail_labels_teach_back_fields_and_keeps_resolved_misconceptions_out_of_attention(self):
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercise = CodingExercise.objects.select_related('activity__concept').get(slug='double-numbers')
        learning_session = LearningSession.objects.get(
            browser_session_key=browser_key,
            activity=exercise.activity,
        )
        TeachBackAttempt.objects.create(
            learning_session=learning_session,
            response=json.dumps({
                'original_issue': 'I returned values without doubling them.',
                'failure_reason': 'Each current item was unchanged.',
                'correction': 'I double the current item first.',
                'concept': 'A loop works with one current item.',
                'prevention': 'I will trace one item.',
            }),
            evaluation='CLEAR_UNDERSTANDING',
        )
        confirmed = MisconceptionRecord.objects.create(
            learning_session=learning_session,
            concept=exercise.activity.concept,
            code='loop-value-misuse',
            evidence='Initially confirmed.',
            status=MisconceptionRecord.Status.CONFIRMED,
        )
        MisconceptionRecord.objects.create(
            learning_session=learning_session,
            concept=exercise.activity.concept,
            code='loop-value-misuse',
            evidence='Later resolved.',
            status=MisconceptionRecord.Status.RESOLVED,
            supersedes=confirmed,
        )
        TransferAttempt.objects.create(
            learning_session=learning_session,
            activity=exercise.transfer_activity,
            response='def word_lengths(words):\n    return [len(word) for word in words]',
            reasoning='I transform each word.',
            confidence=5,
            passed=True,
            evaluation={'status': 'PASSED'},
        )

        response = self.client.get(reverse('progress:session_detail', args=(learning_session.pk,)))

        self.assertContains(response, 'Why the original approach failed')
        self.assertContains(response, 'Each current item was unchanged.')
        self.assertNotContains(response, 'Current attention:')
        self.assertContains(response, 'Runner status:</strong> PASSED')
