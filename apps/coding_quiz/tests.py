from unittest.mock import Mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.code_runner.runner import ExecutionResult, ExecutionStatus
from apps.learning_core.models import (
    HintUsage,
    LearnerAttempt,
    LearningSession,
    MisconceptionRecord,
    TeachBackAttempt,
    TransferAttempt,
)
from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState

from .models import CodingExercise
from .services import (
    ensure_demo_exercise,
    get_demo_session,
    request_curated_hint,
    submit_diagnosis,
    submit_first_attempt,
    submit_revision,
    submit_teach_back,
    submit_transfer_check,
)


class PassingCodeExecutionGateway:
    def run(self, request):
        return ExecutionResult(
            status=ExecutionStatus.PASSED,
            message='Passed by the isolated test gateway.',
            tests=({'name': 'curated-tests', 'passed': True},),
        )


PASSING_GATEWAY = 'apps.coding_quiz.tests.PassingCodeExecutionGateway'


class CodingWorkflowBrowserTests(TestCase):
    url = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.url = reverse('coding_quiz:exercise')

    def first_attempt_data(self, **overrides):
        data = {
            'action': 'first_attempt',
            'source_code': 'def double_numbers(values):\n    return [value * 2 for value in values]',
            'reasoning': 'Transform each current list value and collect the results.',
            'confidence': '3',
        }
        data.update(overrides)
        return data

    def post_first_attempt(self, client=None, **overrides):
        return (client or self.client).post(self.url, self.first_attempt_data(**overrides))

    def advance_to_revision(self):
        self.post_first_attempt()
        self.client.post(self.url, {
            'action': 'diagnosis',
            'diagnosis_answer': 'The loop variable is one current number and is appended after doubling.',
        })

    def advance_to_transfer(self):
        self.advance_to_revision()
        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            self.client.post(self.url, {
                'action': 'finish_revision',
                'revision-source_code': 'def double_numbers(values):\n    return [value * 2 for value in values]',
                'revision-reasoning': 'I now transform the current value, not the whole list.',
                'revision-confidence': '4',
            })
        self.client.post(self.url, {
            'action': 'teach_back',
            'teach-original_issue': 'I was uncertain which value the loop represented.',
            'teach-failure_reason': 'The old approach did not transform each current list item.',
            'teach-correction': 'I doubled the current loop value and collected it.',
            'teach-concept': 'A for loop binds one item at a time.',
            'teach-prevention': 'I will trace the loop variable with a small example.',
        })

    def test_page_loads_exercise_from_database_and_starts_at_first_attempt(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CodingExercise.objects.count(), 1)
        exercise = CodingExercise.objects.select_related('activity').get()
        self.assertEqual(response.context['exercise'], exercise)
        self.assertContains(response, 'Double every number')
        self.assertContains(response, 'Think-First / First Attempt')

    def test_legacy_untracked_browser_progress_starts_again_at_first_attempt(self):
        self.client.get(self.url)
        learning_session = LearningSession.objects.get()
        LearnerAttempt.objects.create(
            learning_session=learning_session,
            activity=CodingExercise.objects.get().activity,
            answer='def old_attempt():\n    pass',
            reasoning='An attempt left by the old browser-session workflow.',
            confidence=2,
        )
        learning_session.current_state = WorkflowState.DIAGNOSIS
        learning_session.save(update_fields=('current_state',))

        browser_session = self.client.session
        browser_session.pop('coding_demo_learning_session_id')
        browser_session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Think-First / First Attempt')
        self.assertNotContains(response, '2. Diagnosis')
        self.assertEqual(LearnerAttempt.objects.count(), 0)

    def test_refresh_keeps_a_tracked_first_attempt_at_diagnosis(self):
        self.post_first_attempt()

        first_refresh = self.client.get(self.url)
        second_refresh = self.client.get(self.url)

        self.assertContains(first_refresh, '2. Diagnosis')
        self.assertContains(second_refresh, '2. Diagnosis')
        self.assertEqual(LearnerAttempt.objects.filter(revision_number=0).count(), 1)

    @override_settings(CODE_RUNNER_URL='', CODE_RUNNER_GATEWAY_CLASS='')
    def test_valid_first_attempt_is_saved_and_redirects_to_diagnosis(self):
        response = self.post_first_attempt()

        self.assertRedirects(response, self.url)
        self.assertEqual(LearnerAttempt.objects.count(), 1)
        attempt = LearnerAttempt.objects.get()
        self.assertEqual(attempt.revision_number, 0)
        self.assertEqual(attempt.evaluation['status'], 'NOT_EXECUTED')
        page = self.client.get(self.url)
        self.assertContains(page, '2. Diagnosis')
        self.assertContains(page, 'NOT_EXECUTED')
        self.assertNotContains(page, 'ExecutionStatus.NOT_EXECUTED')

    def test_each_required_first_attempt_field_shows_an_inline_error(self):
        cases = (
            ('source_code', '', 'This field is required.'),
            ('reasoning', '', 'This field is required.'),
            ('confidence', '', 'This field is required.'),
        )
        for field, value, error in cases:
            with self.subTest(field=field):
                response = self.post_first_attempt(**{field: value})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)
                self.assertEqual(LearnerAttempt.objects.count(), 0)

    def test_first_attempt_cannot_be_submitted_twice_and_refresh_does_not_duplicate(self):
        self.post_first_attempt()
        second = self.post_first_attempt()
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'already been submitted')
        self.client.get(self.url)
        self.assertEqual(LearnerAttempt.objects.filter(revision_number=0).count(), 1)

    def test_workflow_cannot_skip_diagnosis(self):
        response = self.client.post(self.url, {
            'action': 'diagnosis',
            'diagnosis_answer': 'Trying to skip ahead.',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available at this step')
        self.assertEqual(MisconceptionRecord.objects.count(), 0)

    def test_diagnosis_is_saved_and_opens_revision(self):
        self.advance_to_revision()
        self.assertEqual(MisconceptionRecord.objects.count(), 1)
        response = self.client.get(self.url)
        self.assertContains(response, '3. Revision')

    def test_interrupted_first_attempt_session_recovers_before_diagnosis_submission(self):
        self.post_first_attempt()
        learning_session = LearningSession.objects.get()
        learning_session.current_state = WorkflowState.FIRST_ATTEMPT
        learning_session.save(update_fields=('current_state', 'updated_at'))

        page = self.client.get(self.url)
        learning_session.refresh_from_db()
        self.assertEqual(learning_session.current_state, WorkflowState.DIAGNOSIS)
        self.assertContains(page, 'Your First Attempt is already saved')

        response = self.client.post(self.url, {
            'action': 'diagnosis',
            'diagnosis_answer': 'Double the current value before appending it.',
        })
        self.assertRedirects(response, self.url)
        learning_session.refresh_from_db()
        self.assertEqual(learning_session.current_state, WorkflowState.GUIDED_REVISION)

    def test_hints_unlock_in_order_only_after_new_revision_action(self):
        self.advance_to_revision()
        self.assertRedirects(
            self.client.post(self.url, {'action': 'hint'}), self.url
        )
        self.assertEqual(list(HintUsage.objects.values_list('level', flat=True)), [1])

        blocked = self.client.post(self.url, {'action': 'hint'})
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, 'Revise your work before unlocking the next hint')
        self.assertEqual(HintUsage.objects.count(), 1)

        self.client.post(self.url, {
            'action': 'save_revision',
            'revision-source_code': 'def double_numbers(values):\n    return []',
            'revision-reasoning': 'I reconsidered what the current loop value means.',
            'revision-confidence': '2',
        })
        self.client.post(self.url, {'action': 'hint'})
        self.assertEqual(list(HintUsage.objects.values_list('level', flat=True)), [1, 2])

    def test_revision_is_append_only_and_opens_teach_back(self):
        self.advance_to_revision()
        original = LearnerAttempt.objects.get(revision_number=0)
        original_answer = original.answer
        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            response = self.client.post(self.url, {
                'action': 'finish_revision',
                'revision-source_code': 'def double_numbers(values):\n    return [value * 2 for value in values]',
                'revision-reasoning': 'Use the current value on every pass.',
                'revision-confidence': '4',
            })
        self.assertRedirects(response, self.url)
        original.refresh_from_db()
        self.assertEqual(original.answer, original_answer)
        self.assertTrue(LearnerAttempt.objects.filter(revision_number=1).exists())
        self.assertContains(self.client.get(self.url), '4. Teach-Back')

    def test_unverified_revision_stays_in_revision(self):
        self.advance_to_revision()
        response = self.client.post(self.url, {
            'action': 'finish_revision',
            'revision-source_code': 'def double_numbers(values):\n    return values',
            'revision-reasoning': 'This revision cannot be verified without the runner.',
            'revision-confidence': '2',
        }, follow=True)

        session = LearningSession.objects.get()
        self.assertEqual(session.current_state, WorkflowState.GUIDED_REVISION)
        self.assertContains(response, 'Teach-Back remains locked')
        self.assertEqual(LearnerAttempt.objects.filter(revision_number=1).count(), 1)

    def test_partial_teach_back_stays_locked(self):
        self.advance_to_revision()
        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            self.client.post(self.url, {
                'action': 'finish_revision',
                'revision-source_code': 'def double_numbers(values):\n    return [value * 2 for value in values]',
                'revision-reasoning': 'Transform each current value.',
                'revision-confidence': '4',
            })
        response = self.client.post(self.url, {
            'action': 'teach_back',
            'teach-original_issue': 'Not sure.',
            'teach-failure_reason': 'It failed.',
            'teach-correction': 'I fixed it.',
            'teach-concept': 'Python.',
            'teach-prevention': 'Be careful.',
        }, follow=True)

        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.TEACH_BACK)
        self.assertEqual(TeachBackAttempt.objects.get().evaluation, 'PARTIAL_UNDERSTANDING')
        self.assertContains(response, 'Teach-Back needs revision')

    @override_settings(CODE_RUNNER_URL='', CODE_RUNNER_GATEWAY_CLASS='')
    def test_teach_back_and_transfer_check_are_saved(self):
        self.advance_to_transfer()
        self.assertEqual(TeachBackAttempt.objects.count(), 1)
        page = self.client.get(self.url)
        self.assertContains(page, '5. Transfer Check')
        self.assertContains(page, 'AI and all hints are locked')
        self.assertNotContains(page, 'def double_numbers')

        response = self.client.post(self.url, {
            'action': 'transfer',
            'transfer-source_code': 'def word_lengths(words):\n    return [len(word) for word in words]',
            'transfer-reasoning': 'Transform each word into its length.',
            'transfer-confidence': '4',
        })
        self.assertRedirects(response, self.url)
        self.assertEqual(TransferAttempt.objects.count(), 1)
        transfer = TransferAttempt.objects.get()
        self.assertFalse(transfer.used_assistance)
        self.assertEqual(transfer.evaluation['status'], 'NOT_EXECUTED')
        self.assertContains(self.client.get(self.url), 'Learning session completed')

    def test_verified_browser_workflow_reaches_mastered(self):
        self.advance_to_transfer()
        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            response = self.client.post(self.url, {
                'action': 'transfer',
                'transfer-source_code': 'def word_lengths(words):\n    return [len(word) for word in words]',
                'transfer-reasoning': 'A loop maps every current word to its length.',
                'transfer-confidence': '5',
            }, follow=True)

        learning_session = LearningSession.objects.get()
        self.assertEqual(learning_session.current_state, WorkflowState.MASTERED)
        self.assertContains(response, 'Mastered: all required evidence was verified')
        self.assertContains(response, 'Status: PASSED')

    def test_transfer_check_rejects_hints(self):
        self.advance_to_transfer()
        response = self.client.post(self.url, {'action': 'hint'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hints are available only during guided revision')
        self.assertEqual(HintUsage.objects.count(), 0)

    def test_browser_sessions_have_independent_progress_and_reset_is_scoped(self):
        other = Client()
        self.post_first_attempt()
        other.get(self.url)
        sessions = LearningSession.objects.order_by('id')
        self.assertEqual(sessions.count(), 2)
        self.assertNotEqual(sessions[0].browser_session_key, sessions[1].browser_session_key)
        self.assertNotEqual(sessions[0].current_state, sessions[1].current_state)

        self.client.post(self.url, {'action': 'reset'})
        self.assertEqual(LearningSession.objects.count(), 1)
        remaining = LearningSession.objects.get()
        self.assertEqual(remaining.browser_session_key, other.session.session_key)


class CodingWorkflowServiceTests(TestCase):
    def setUp(self):
        self.exercise = ensure_demo_exercise()
        self.session, _ = get_demo_session(browser_session_key='service-browser', exercise=self.exercise)
        transition_session(self.session, WorkflowState.DIAGNOSTIC_QUIZ)

    def submit_first(self, gateway=None):
        return submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(values):\n    return values',
            reasoning='I will transform the values.',
            confidence=3,
            gateway=gateway,
        )

    def test_incomplete_first_attempt_is_rejected(self):
        with self.assertRaises(ValidationError):
            submit_first_attempt(
                learning_session=self.session,
                exercise=self.exercise,
                source_code='',
                reasoning='A plan',
                confidence=3,
            )

    def test_submission_crosses_only_the_code_runner_gateway(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(
            status=ExecutionStatus.FAILED,
            message='Isolated test evidence',
        )
        attempt, _ = self.submit_first(gateway=gateway)
        gateway.run.assert_called_once()
        execution_request = gateway.run.call_args.args[0]
        self.assertEqual(
            execution_request.test_case_ids,
            ('double-public', 'empty-list', 'negative-values'),
        )
        self.assertEqual(attempt.evaluation['status'], 'FAILED')

    def test_full_service_flow_with_stub_gateway_can_reach_mastered(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(
            status=ExecutionStatus.PASSED,
            message='Passed in isolated stub.',
        )
        self.submit_first(gateway=gateway)
        submit_diagnosis(learning_session=self.session, answer='Use each current loop value.')
        submit_revision(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(values):\n    return [value * 2 for value in values]',
            reasoning='Double each current value.',
            confidence=5,
            gateway=gateway,
        )
        submit_teach_back(learning_session=self.session, response={
            'original_issue': 'The original attempt returned values without transforming them.',
            'failure_reason': 'It failed because every current item stayed unchanged.',
            'correction': 'I double each current value and append it to the result.',
            'concept': 'A for loop processes one item or value on every iteration.',
            'prevention': 'I will trace one loop iteration before submitting future code.',
        })
        transfer, result = submit_transfer_check(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def word_lengths(words):\n    return [len(word) for word in words]',
            reasoning='Map every word to its length.',
            confidence=5,
            gateway=gateway,
        )
        self.session.refresh_from_db()
        self.assertEqual(result.status, ExecutionStatus.PASSED)
        self.assertTrue(transfer.passed)
        self.assertEqual(transfer.activity.activity_type, 'coding_transfer')
        self.assertEqual(transfer.evaluation['status'], 'PASSED')
        transfer_request = gateway.run.call_args.args[0]
        self.assertEqual(
            transfer_request.test_case_ids,
            ('empty-words', 'mixed-word-lengths'),
        )
        self.assertEqual(self.session.current_state, WorkflowState.MASTERED)

    @override_settings(CODE_RUNNER_URL='', CODE_RUNNER_GATEWAY_CLASS='')
    def test_default_gateway_never_executes_code(self):
        attempt, result = self.submit_first()
        self.assertEqual(result.status, ExecutionStatus.NOT_EXECUTED)
        self.assertEqual(attempt.evaluation['status'], 'NOT_EXECUTED')

    def test_teach_back_rejects_an_unverified_revision_even_if_state_is_forced(self):
        self.submit_first()
        submit_diagnosis(learning_session=self.session, answer='Use each current loop value.')
        submit_revision(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(values):\n    return values',
            reasoning='This revision is stored but cannot be verified.',
            confidence=2,
        )
        transition_session(self.session, WorkflowState.TEACH_BACK)

        with self.assertRaisesMessage(ValidationError, 'verified as PASSED'):
            submit_teach_back(learning_session=self.session, response={
                'original_issue': 'The original code did not transform the current value.',
                'failure_reason': 'The old approach returned unchanged values.',
                'correction': 'I double each current value before collecting it.',
                'concept': 'A for loop processes one item at a time.',
                'prevention': 'I will trace each loop iteration next time.',
            })

    def test_hint_is_not_available_during_transfer(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.PASSED, 'Passed')
        self.submit_first(gateway=gateway)
        submit_diagnosis(learning_session=self.session, answer='Current loop item')
        submit_revision(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def solution():\n    return 1',
            reasoning='A complete revision.',
            confidence=4,
            gateway=gateway,
        )
        submit_teach_back(learning_session=self.session, response={
            'original_issue': 'The original code did not transform the current value.',
            'failure_reason': 'The same unchanged value was returned by the old approach.',
            'correction': 'I double each current value before adding it to the result.',
            'concept': 'A for loop processes one item at a time during iteration.',
            'prevention': 'I will trace the current loop item with a small input first.',
        })
        with self.assertRaises(PermissionDenied):
            request_curated_hint(learning_session=self.session)
