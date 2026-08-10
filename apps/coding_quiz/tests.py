from unittest.mock import Mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.code_runner.runner import ExecutionResult, ExecutionStatus
from apps.learning_core.models import LearnerAttempt
from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState

from .models import CodingExercise
from .services import (
    begin_teach_back,
    begin_transfer_check,
    complete_transfer_check,
    ensure_demo_exercise,
    get_demo_session,
    request_curated_hint,
    submit_first_attempt,
)


class CodingRouteTests(TestCase):
    def test_pages_load(self):
        self.assertEqual(self.client.get(reverse('coding_quiz:home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('coding_quiz:exercise')).status_code, 200)

    def test_exercise_is_loaded_from_database(self):
        response = self.client.get(reverse('coding_quiz:exercise'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CodingExercise.objects.count(), 1)

        exercise = CodingExercise.objects.select_related('activity').get()
        self.assertEqual(response.context['exercise'], exercise)
        self.assertContains(response, exercise.activity.title)

    def test_complete_first_attempt_is_stored_and_sent_to_gateway(self):
        response = self.client.post(reverse('coding_quiz:exercise'), {
            'source_code': 'def double_numbers(values):\n    return values',
            'reasoning': 'I return a transformed list.',
            'confidence': 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LearnerAttempt.objects.count(), 1)
        self.assertEqual(LearnerAttempt.objects.get().evaluation['status'], 'NOT_EXECUTED')
        self.assertContains(response, 'NOT_EXECUTED')
        self.assertNotContains(response, 'ExecutionStatus.NOT_EXECUTED')


class CodingWorkflowServiceTests(TestCase):
    def setUp(self):
        self.exercise = ensure_demo_exercise()
        self.session, _ = get_demo_session(browser_session_key='browser-key', exercise=self.exercise)
        transition_session(self.session, WorkflowState.DIAGNOSTIC_QUIZ)

    def test_incomplete_first_attempt_is_rejected(self):
        with self.assertRaises(ValidationError):
            submit_first_attempt(
                learning_session=self.session,
                exercise=self.exercise,
                source_code='',
                reasoning='A plan',
                confidence=3,
            )

    def test_submission_crosses_only_the_code_runner_boundary(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(
            status=ExecutionStatus.FAILED,
            message='Isolated test evidence',
        )
        attempt, _ = submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def solution():\n    return 1',
            reasoning='Return the required value.',
            confidence=3,
            gateway=gateway,
        )

        gateway.run.assert_called_once()
        self.assertEqual(attempt.evaluation['status'], 'FAILED')

    def test_hints_require_guided_revision_and_new_action(self):
        attempt, _ = submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def solution():\n    return 1',
            reasoning='Try a direct result.',
            confidence=2,
        )
        transition_session(self.session, WorkflowState.RESPONSE_EVALUATION)
        transition_session(self.session, WorkflowState.DIAGNOSIS)
        transition_session(self.session, WorkflowState.GUIDED_REVISION)

        first_hint = request_curated_hint(learning_session=self.session)
        self.assertEqual(first_hint.level, 1)
        with self.assertRaises(PermissionDenied):
            request_curated_hint(learning_session=self.session)

        LearnerAttempt.objects.create(
            learning_session=self.session,
            activity=self.exercise.activity,
            answer=attempt.answer + '\n# revision',
            reasoning='I reconsidered the loop variable.',
            confidence=3,
            revision_number=1,
        )
        second_hint = request_curated_hint(learning_session=self.session)
        self.assertEqual(second_hint.level, 2)

    def test_teach_back_requires_original_pass(self):
        submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def solution():\n    return 1',
            reasoning='Try a direct result.',
            confidence=2,
        )
        transition_session(self.session, WorkflowState.RESPONSE_EVALUATION)

        with self.assertRaises(PermissionDenied):
            begin_teach_back(learning_session=self.session, original_passed=False)

    def test_transfer_requires_clear_teach_back_and_unassisted_pass_for_mastery(self):
        submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def solution():\n    return 1',
            reasoning='Try a direct result.',
            confidence=2,
        )
        transition_session(self.session, WorkflowState.RESPONSE_EVALUATION)
        begin_teach_back(learning_session=self.session, original_passed=True)
        with self.assertRaises(PermissionDenied):
            begin_transfer_check(
                learning_session=self.session,
                teach_back_evaluation='PARTIAL_UNDERSTANDING',
            )

        begin_transfer_check(
            learning_session=self.session,
            teach_back_evaluation='CLEAR_UNDERSTANDING',
        )
        outcome = complete_transfer_check(
            learning_session=self.session,
            original_passed=True,
            teach_back_clear=True,
            transfer_passed=True,
            used_assistance=True,
            misconception_repeated=False,
        )
        self.assertEqual(outcome, WorkflowState.NEEDS_REVIEW)
