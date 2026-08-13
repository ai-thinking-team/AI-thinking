import json
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.code_runner.runner import ExecutionResult, ExecutionStatus
from apps.learning_core.models import LearnerAttempt
from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState

from .services import (
    begin_teach_back,
    begin_transfer_check,
    complete_transfer_check,
    ensure_demo_exercise,
    ensure_diagnostic_quiz,
    get_demo_session,
    request_curated_hint,
    submit_diagnosis,
    submit_diagnostic_quiz,
    submit_first_attempt,
    submit_verification,
)


def _fake_generate_ai_response(*, system_prompt, user_prompt, response_schema=None, file_bytes=None, mime_type=None):
    """Route to canned JSON based on which prompt is being asked for, so
    tests never depend on a real (and possibly configured) AI provider."""
    if 'diagnostic question' in system_prompt:
        return json.dumps({'question': 'What does a for loop do?'})
    if 'diagnosing a misconception' in system_prompt:
        return json.dumps({'question': 'Which value changes each pass?', 'possible_misconception': 'wrong-variable'})
    if 'marked low confidence' in system_prompt:
        return json.dumps({'question': 'Why does this work for every item?'})
    if 'Hints escalate through' in system_prompt:
        return json.dumps({'content': 'This is a canned hint.'})
    if "Teach-Back explanation" in system_prompt:
        clear = 'CLEAR' in user_prompt
        return json.dumps({
            'evaluation': 'CLEAR_UNDERSTANDING' if clear else 'PARTIAL_UNDERSTANDING',
            'feedback': 'Canned feedback.',
            'follow_up_question': '' if clear else 'Canned follow-up question.',
        })
    if 'did not complete this exercise with mastery' in system_prompt:
        return json.dumps({'recommendation': 'Review loop basics.'})
    raise AssertionError(f'Unexpected system prompt in test: {system_prompt[:60]}')


@patch('apps.coding_quiz.services.generate_ai_response', side_effect=_fake_generate_ai_response)
class CodingRouteTests(TestCase):
    def test_pages_load(self, _mock):
        self.assertEqual(self.client.get(reverse('coding_quiz:home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('coding_quiz:exercise')).status_code, 200)

    def test_full_flow_through_the_view_reaches_diagnosis(self, _mock):
        exercise_url = reverse('coding_quiz:exercise')
        self.client.get(exercise_url)  # primes the session + diagnostic quiz question
        self.client.post(exercise_url, {'action': 'diagnostic_quiz', 'answer': 'It repeats for each item.'})

        response = self.client.post(exercise_url, {
            'action': 'first_attempt',
            'source_code': 'def double_numbers(values):\n    return values',
            'reasoning': 'I return a transformed list.',
            'confidence': 2,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LearnerAttempt.objects.count(), 1)
        attempt = LearnerAttempt.objects.get()
        # Whether or not a code runner is configured in this environment, an
        # unmodified `return values` submission must not count as correct.
        self.assertIn(attempt.evaluation['status'], ('NOT_EXECUTED', 'FAILED'))
        self.assertTrue(attempt.diagnosis_question)


class CodingWorkflowServiceTests(TestCase):
    def setUp(self):
        patcher = patch('apps.coding_quiz.services.generate_ai_response', side_effect=_fake_generate_ai_response)
        self.addCleanup(patcher.stop)
        patcher.start()

        self.exercise = ensure_demo_exercise()
        self.session, _ = get_demo_session(browser_session_key='browser-key', exercise=self.exercise)
        transition_session(self.session, WorkflowState.DIAGNOSTIC_QUIZ)
        ensure_diagnostic_quiz(learning_session=self.session)
        submit_diagnostic_quiz(learning_session=self.session, answer='Loops repeat once per item.')

    def test_incomplete_first_attempt_is_rejected(self):
        with self.assertRaises(ValidationError):
            submit_first_attempt(
                learning_session=self.session,
                exercise=self.exercise,
                source_code='',
                reasoning='A plan',
                confidence=3,
            )

    def test_first_attempt_requires_diagnostic_quiz_answered(self):
        session, _ = get_demo_session(browser_session_key='other-browser', exercise=self.exercise)
        transition_session(session, WorkflowState.DIAGNOSTIC_QUIZ)
        with self.assertRaises(ValidationError):
            submit_first_attempt(
                learning_session=session,
                exercise=self.exercise,
                source_code='def solution():\n    return 1',
                reasoning='Try a direct result.',
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
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.DIAGNOSIS)

    def test_correct_and_confident_answer_skips_straight_to_teach_back(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(status=ExecutionStatus.PASSED, message='ok')
        submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(n):\n    return [x * 2 for x in n]',
            reasoning='Map each item and double it.',
            confidence=5,
            gateway=gateway,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)

    def test_correct_but_unsure_answer_requires_verification_then_teach_back(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(status=ExecutionStatus.PASSED, message='ok')
        attempt, _ = submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(n):\n    return [x * 2 for x in n]',
            reasoning='Map each item and double it.',
            confidence=2,
            gateway=gateway,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.VERIFICATION)
        self.assertTrue(attempt.verification_question)

        with self.assertRaises(ValidationError):
            submit_verification(learning_session=self.session, answer='')

        submit_verification(learning_session=self.session, answer='Each value is multiplied by 2 in the loop.')
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)

    def test_hints_require_guided_revision_and_new_action(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(status=ExecutionStatus.FAILED, message='no')
        attempt, _ = submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def solution():\n    return 1',
            reasoning='Try a direct result.',
            confidence=2,
            gateway=gateway,
        )
        submit_diagnosis(learning_session=self.session, answer='I think I used the wrong variable.')
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.GUIDED_REVISION)

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

    def test_hint_ladder_stops_after_five_levels(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(status=ExecutionStatus.FAILED, message='no')
        attempt, _ = submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def solution():\n    return 1',
            reasoning='A first guess.',
            confidence=1,
            gateway=gateway,
        )
        submit_diagnosis(learning_session=self.session, answer='Not sure yet.')

        last_hint = None
        for level in range(1, 6):
            last_hint = request_curated_hint(learning_session=self.session)
            LearnerAttempt.objects.create(
                learning_session=self.session,
                activity=self.exercise.activity,
                answer=attempt.answer + f'\n# revision {level}',
                reasoning='More thought.',
                confidence=2,
                revision_number=level,
            )
        self.assertEqual(last_hint.level, 5)
        with self.assertRaises(PermissionDenied):
            request_curated_hint(learning_session=self.session)

    def test_teach_back_requires_original_pass(self):
        transition_session(self.session, WorkflowState.FIRST_ATTEMPT)
        transition_session(self.session, WorkflowState.RESPONSE_EVALUATION)
        with self.assertRaises(PermissionDenied):
            begin_teach_back(learning_session=self.session, original_passed=False)

    def test_transfer_requires_clear_teach_back_and_unassisted_pass_for_mastery(self):
        transition_session(self.session, WorkflowState.FIRST_ATTEMPT)
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
