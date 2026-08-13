import json
from copy import deepcopy
from io import StringIO
from unittest.mock import Mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.core.management import call_command

from apps.code_runner.runner import ExecutionResult, ExecutionStatus
from apps.learning_core.models import (
    CoachInteraction,
    CoachLearnerResponse,
    ConceptMastery,
    HintUsage,
    LearnerAttempt,
    LearningActivity,
    LearningSession,
    MisconceptionRecord,
    TeachBackAttempt,
    TransferAttempt,
)
from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import InvalidWorkflowTransition, WorkflowState

from .models import CodingExercise, CodingPlanEvidence
from .catalog import CODING_CATALOG
from .catalog_validation import validate_catalog
from .teach_back_rubric import LOOP_VALUES_TEACH_BACK_RUBRIC, evaluate_teach_back
from .services import (
    acknowledge_diagnosis_solution,
    ensure_demo_exercise,
    get_demo_session,
    request_curated_hint,
    submit_diagnosis,
    submit_first_attempt,
    submit_plan,
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


class PassingDiagnosticProvider:
    def generate(self, **kwargs):
        return {
            'possible_misconception': 'loop-value-misuse',
            'diagnostic_confidence': 0.8,
            'response_type': 'guiding_question',
            'message': 'During one iteration, what value is stored in the loop variable?',
            'hint_level': 1,
            'should_reveal_solution': False,
        }


class InvalidDiagnosticProvider:
    def generate(self, **kwargs):
        return {
            'possible_misconception': 'loop-value-misuse',
            'diagnostic_confidence': 1.0,
            'response_type': 'guiding_question',
            'message': 'The complete solution is forbidden.',
            'hint_level': 1,
            'should_reveal_solution': True,
            'mastery': 'MASTERED',
        }


PASSING_AI_PROVIDER = 'apps.coding_quiz.tests.PassingDiagnosticProvider'
INVALID_AI_PROVIDER = 'apps.coding_quiz.tests.InvalidDiagnosticProvider'


class PartialTeachBackProvider:
    def generate(self, **kwargs):
        return {
            'field_evaluations': [
                {'field': 'original_issue', 'understood': True, 'feedback': ''},
                {
                    'field': 'failure_reason',
                    'understood': False,
                    'feedback': 'Explain how one iteration caused the wrong output.',
                },
                {'field': 'correction', 'understood': True, 'feedback': ''},
                {'field': 'concept', 'understood': True, 'feedback': ''},
                {'field': 'prevention', 'understood': True, 'feedback': ''},
            ],
            'misconception_code': 'none',
            'follow_up_question': 'How did the old operation affect the value in one iteration?',
        }


PARTIAL_TEACH_BACK_PROVIDER = 'apps.coding_quiz.tests.PartialTeachBackProvider'


class TeachBackRubricTests(SimpleTestCase):
    def test_semantic_rubric_evidence_replaces_minimum_length(self):
        outcome = evaluate_teach_back({
            'original_issue': 'Wrong current value.',
            'failure_reason': 'Each item stayed unchanged.',
            'correction': 'Double each value.',
            'concept': 'A for loop handles one item.',
            'prevention': 'Trace the loop with small input.',
        }, LOOP_VALUES_TEACH_BACK_RUBRIC)

        self.assertEqual(outcome.result, 'CLEAR_UNDERSTANDING')

    def test_approximate_answer_passes_when_most_core_ideas_are_present(self):
        outcome = evaluate_teach_back({
            'failure_reason': 'Each number was not changed.',
            'correction': 'I double the current value and put it in the result.',
            'concept': 'The loop handles one value at a time.',
        }, LOOP_VALUES_TEACH_BACK_RUBRIC)

        self.assertEqual(outcome.result, 'CLEAR_UNDERSTANDING')
        self.assertEqual(outcome.rubric_evidence['grading_mode'], 'core_ideas_majority')

    def test_invalid_rubric_fails_closed_with_one_question(self):
        outcome = evaluate_teach_back({'concept': 'Anything'}, {'criteria': [{}]})

        self.assertEqual(outcome.result, 'PARTIAL_UNDERSTANDING')
        self.assertFalse(outcome.rubric_evidence['rubric_valid'])
        self.assertTrue(outcome.follow_up_question)


@override_settings(AI_PROVIDER_CLASS='')
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

    def plan_data(self, **overrides):
        data = {
            'action': 'plan',
            'solution_plan': 'Loop through each current value, transform it, and collect the result.',
            'predicted_output': '[2, 6]',
        }
        data.update(overrides)
        return data

    def post_plan(self, client=None, url=None, **overrides):
        return (client or self.client).post(
            url or self.url,
            self.plan_data(**overrides),
        )

    def post_first_attempt(self, client=None, url=None, **overrides):
        selected_client = client or self.client
        selected_url = url or self.url
        self.post_plan(client=selected_client, url=selected_url)
        return selected_client.post(selected_url, self.first_attempt_data(**overrides))

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

    def test_page_loads_exercise_from_database_and_starts_at_understand_and_plan(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CodingExercise.objects.filter(active=True).count(), 4)
        exercise = CodingExercise.objects.select_related('activity').get(slug='double-numbers')
        self.assertEqual(response.context['exercise'], exercise)
        self.assertContains(response, 'Double every number')
        self.assertContains(response, 'Understand and Plan')
        self.assertNotContains(response, 'name="source_code"')

    def test_catalog_lists_database_exercises_and_routes_by_slug(self):
        response = self.client.get(reverse('coding_quiz:home'))

        self.assertContains(response, 'Double every number')
        self.assertContains(response, 'Square every number')
        self.assertContains(response, 'Increment every number')
        square_url = reverse('coding_quiz:exercise_detail', args=('square-numbers',))
        self.assertContains(response, square_url)
        square_page = self.client.get(square_url)
        self.assertContains(square_page, 'square_numbers([2, -3])')

    def test_same_browser_has_independent_active_session_per_exercise(self):
        double_url = reverse('coding_quiz:exercise_detail', args=('double-numbers',))
        square_url = reverse('coding_quiz:exercise_detail', args=('square-numbers',))
        self.post_first_attempt(url=double_url)

        square_page = self.client.get(square_url)

        sessions = LearningSession.objects.filter(
            browser_session_key=self.client.session.session_key,
            ended_at__isnull=True,
        ).select_related('activity')
        self.assertEqual(sessions.count(), 2)
        self.assertEqual(
            set(sessions.values_list('activity__coding_exercise__slug', flat=True)),
            {'double-numbers', 'square-numbers'},
        )
        self.assertContains(square_page, 'Understand and Plan')
        self.assertContains(square_page, 'square_numbers([2, -3])')

    def test_database_rejects_two_active_sessions_for_same_exercise(self):
        self.client.get(self.url)
        existing = LearningSession.objects.get()

        with self.assertRaises(IntegrityError), transaction.atomic():
            LearningSession.objects.create(
                browser_session_key=existing.browser_session_key,
                topic=existing.topic,
                activity=existing.activity,
                active_slot=True,
            )

    def test_catalog_validation_command_accepts_the_versioned_catalog(self):
        output = StringIO()
        call_command('validate_coding_catalog', stdout=output)
        self.assertIn('Catalog valid: 4 exercise(s).', output.getvalue())

    def test_catalog_validation_rejects_unknown_runner_test_id(self):
        invalid_catalog = deepcopy(CODING_CATALOG)
        invalid_catalog[0]['hidden_test_ids'].append('unknown-hidden-case')

        errors = validate_catalog(invalid_catalog)

        self.assertTrue(any('unknown runner test IDs' in error for error in errors))

    def test_catalog_sync_dry_run_does_not_write_database(self):
        before_exercises = CodingExercise.objects.count()
        before_activities = LearningActivity.objects.count()
        output = StringIO()

        call_command('sync_coding_catalog', '--dry-run', stdout=output)

        self.assertEqual(CodingExercise.objects.count(), before_exercises)
        self.assertEqual(LearningActivity.objects.count(), before_activities)
        self.assertIn('Dry run:', output.getvalue())

    def test_active_exercise_model_validation_rejects_unknown_test_id(self):
        exercise = CodingExercise.objects.get(slug='double-numbers')
        exercise.public_test_ids = ['unknown-public-case']

        with self.assertRaises(ValidationError):
            exercise.full_clean()

    def test_invalid_database_rubric_blocks_plan_before_evidence_or_ai(self):
        self.client.get(self.url)
        exercise = CodingExercise.objects.select_related('activity').get(slug='double-numbers')
        invalid_rubric = deepcopy(exercise.activity.rubric)
        invalid_rubric['allowed_misconception_codes'] = []
        LearningActivity.objects.filter(pk=exercise.activity_id).update(rubric=invalid_rubric)

        response = self.client.post(self.url, self.plan_data())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'curated configuration is invalid')
        self.assertEqual(
            LearningSession.objects.get().current_state,
            WorkflowState.DIAGNOSTIC_QUIZ,
        )
        self.assertFalse(LearnerAttempt.objects.exists())
        self.assertFalse(CodingPlanEvidence.objects.exists())
        self.assertFalse(CoachInteraction.objects.exists())

    def test_plan_is_required_before_first_attempt_and_does_not_call_ai_or_runner(self):
        self.client.get(self.url)

        blocked = self.client.post(self.url, self.first_attempt_data())

        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, 'Complete Understand and Plan')
        self.assertFalse(LearnerAttempt.objects.exists())
        self.assertFalse(CoachInteraction.objects.exists())

        response = self.post_plan()

        self.assertRedirects(response, self.url)
        plan = CodingPlanEvidence.objects.get()
        session = LearningSession.objects.get()
        self.assertEqual(plan.solution_plan, self.plan_data()['solution_plan'])
        self.assertEqual(plan.predicted_output, '[2, 6]')
        self.assertEqual(session.current_state, WorkflowState.FIRST_ATTEMPT)
        self.assertFalse(LearnerAttempt.objects.exists())
        self.assertFalse(CoachInteraction.objects.exists())
        page = self.client.get(self.url)
        self.assertContains(page, 'Think-First / First Attempt')

    def test_plan_requires_both_fields_and_is_append_only(self):
        for field in ('solution_plan', 'predicted_output'):
            with self.subTest(field=field):
                response = self.post_plan(**{field: ''})
                self.assertContains(response, 'This field is required.')
                self.assertFalse(CodingPlanEvidence.objects.exists())

        self.post_plan()
        second = self.post_plan(solution_plan='Replace the original plan.')

        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'already been completed')
        self.assertEqual(CodingPlanEvidence.objects.count(), 1)
        self.assertNotEqual(
            CodingPlanEvidence.objects.get().solution_plan,
            'Replace the original plan.',
        )

    def test_reset_preserves_old_evidence_and_starts_a_new_session(self):
        self.post_first_attempt()
        old_session = LearningSession.objects.get()
        old_attempt = old_session.attempts.get()

        response = self.client.post(self.url, {'action': 'reset'}, follow=True)

        old_session.refresh_from_db()
        self.assertIsNotNone(old_session.ended_at)
        self.assertIsNone(old_session.active_slot)
        self.assertTrue(LearnerAttempt.objects.filter(pk=old_attempt.pk).exists())
        new_session = LearningSession.objects.exclude(pk=old_session.pk).get()
        self.assertIsNone(new_session.ended_at)
        self.assertEqual(new_session.activity_id, old_session.activity_id)
        self.assertContains(response, 'Understand and Plan')

    def test_untracked_browser_progress_is_resumed_without_deleting_evidence(self):
        self.client.get(self.url)
        learning_session = LearningSession.objects.get()
        LearnerAttempt.objects.create(
            learning_session=learning_session,
            activity=CodingExercise.objects.get(slug='double-numbers').activity,
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
        self.assertContains(response, '3. Diagnosis')
        self.assertEqual(LearnerAttempt.objects.count(), 1)

    def test_refresh_keeps_a_tracked_first_attempt_at_diagnosis(self):
        self.post_first_attempt()

        first_refresh = self.client.get(self.url)
        second_refresh = self.client.get(self.url)

        self.assertContains(first_refresh, '3. Diagnosis')
        self.assertContains(second_refresh, '3. Diagnosis')
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
        self.assertContains(page, '3. Diagnosis')
        self.assertContains(page, 'NOT_EXECUTED')
        self.assertNotContains(page, 'ExecutionStatus.NOT_EXECUTED')
        interaction = CoachInteraction.objects.get()
        self.assertEqual(interaction.source, CoachInteraction.Source.CURATED_FALLBACK)
        self.assertEqual(interaction.failure_code, 'AIServiceUnavailable')
        self.assertContains(page, 'Question source:</strong> CURATED_FALLBACK')

    @override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY)
    def test_passing_first_attempt_with_clear_reasoning_opens_teach_back(self):
        response = self.post_first_attempt(
            reasoning='Double and collect each current value during the loop.',
            confidence='4',
        )

        self.assertRedirects(response, self.url)
        session = LearningSession.objects.get()
        attempt = LearnerAttempt.objects.get()
        self.assertEqual(session.current_state, WorkflowState.TEACH_BACK)
        self.assertEqual(
            attempt.evaluation['response_evaluation']['outcome'],
            'READY_FOR_TEACH_BACK',
        )
        self.assertFalse(CoachInteraction.objects.exists())
        self.assertFalse(MisconceptionRecord.objects.exists())
        page = self.client.get(self.url)
        self.assertContains(page, '5. Teach-Back')
        self.assertContains(page, 'Why did the original approach work or fail?')

    @override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY)
    def test_passing_first_attempt_with_low_confidence_requires_verification(self):
        self.post_first_attempt(
            reasoning='Double and collect each current value during the loop.',
            confidence='3',
        )

        session = LearningSession.objects.get()
        attempt = LearnerAttempt.objects.get()
        self.assertEqual(session.current_state, WorkflowState.DIAGNOSIS)
        self.assertEqual(
            attempt.evaluation['response_evaluation']['outcome'],
            'VERIFICATION_REQUIRED',
        )
        self.assertEqual(CoachInteraction.objects.count(), 1)

    @override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY)
    def test_passing_first_attempt_with_unclear_reasoning_requires_diagnosis(self):
        self.post_first_attempt(reasoning='I used Python.', confidence='5')

        session = LearningSession.objects.get()
        attempt = LearnerAttempt.objects.get()
        self.assertEqual(session.current_state, WorkflowState.DIAGNOSIS)
        self.assertEqual(
            attempt.evaluation['response_evaluation']['outcome'],
            'DIAGNOSIS_REQUIRED',
        )
        self.assertEqual(CoachInteraction.objects.count(), 1)

    @override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY)
    def test_clear_first_attempt_teach_back_can_open_transfer(self):
        self.post_first_attempt(
            reasoning='Double and collect each current value during the loop.',
            confidence='5',
        )

        response = self.client.post(self.url, {
            'action': 'teach_back',
            'teach-original_issue': 'There was no failing issue in the first attempt.',
            'teach-failure_reason': 'It works because every current value is doubled and collected.',
            'teach-correction': 'No correction was needed; I doubled each current value before collecting it.',
            'teach-concept': 'A for loop processes one item at a time.',
            'teach-prevention': 'I will trace each loop item with a small test.',
        }, follow=True)

        session = LearningSession.objects.get()
        teach_back = TeachBackAttempt.objects.get()
        self.assertEqual(teach_back.evaluation, 'CLEAR_UNDERSTANDING')
        self.assertEqual(
            teach_back.rubric_evidence['response_path'],
            'PASSED_FIRST_ATTEMPT',
        )
        self.assertEqual(session.current_state, WorkflowState.TRANSFER_TASK)
        self.assertContains(response, '6. Transfer Check')

    @override_settings(AI_PROVIDER_CLASS=PASSING_AI_PROVIDER)
    def test_valid_ai_diagnostic_is_displayed_with_privacy_minimized_context(self):
        self.post_first_attempt()
        page = self.client.get(self.url)

        interaction = CoachInteraction.objects.get()
        serialized_context = json.dumps(interaction.request_context)
        self.assertEqual(interaction.source, CoachInteraction.Source.AI)
        self.assertTrue(interaction.request_context['data_minimized'])
        self.assertNotIn('def double_numbers', serialized_context)
        self.assertNotIn('Transform each current list value', serialized_context)
        self.assertContains(page, 'During one iteration, what value is stored in the loop variable?')
        self.assertContains(page, 'Question source:</strong> AI')

    @override_settings(AI_PROVIDER_CLASS=INVALID_AI_PROVIDER)
    def test_invalid_ai_output_falls_back_without_exposing_solution_or_mastery(self):
        self.post_first_attempt()
        page = self.client.get(self.url)

        interaction = CoachInteraction.objects.get()
        self.assertEqual(interaction.source, CoachInteraction.Source.CURATED_FALLBACK)
        self.assertEqual(interaction.failure_code, 'InvalidAIResponse')
        self.assertNotContains(page, 'The complete solution is forbidden')
        self.assertNotContains(page, 'MASTERED')
        self.assertContains(page, 'Inside the loop, which single value should be doubled')

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
        self.assertEqual(CoachInteraction.objects.count(), 1)

    def test_workflow_cannot_skip_diagnosis(self):
        response = self.client.post(self.url, {
            'action': 'diagnosis',
            'diagnosis_answer': 'Trying to skip ahead.',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available at this step')
        self.assertEqual(MisconceptionRecord.objects.count(), 0)

    def test_client_cannot_directly_set_mastery(self):
        self.client.get(self.url)
        response = self.client.post(self.url, {
            'action': 'set_mastery',
            'current_state': WorkflowState.MASTERED,
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.DIAGNOSTIC_QUIZ)
        self.assertFalse(ConceptMastery.objects.exists())

    def test_diagnosis_is_saved_and_opens_revision(self):
        self.advance_to_revision()
        self.assertEqual(
            list(MisconceptionRecord.objects.values_list('status', flat=True)),
            [MisconceptionRecord.Status.HYPOTHESIS, MisconceptionRecord.Status.DISMISSED],
        )
        learner_response = CoachLearnerResponse.objects.get()
        self.assertIn('loop variable is one current number', learner_response.response)
        response = self.client.get(self.url)
        self.assertContains(response, '4. Revision')

    def test_wrong_diagnosis_stays_locked_and_unlocks_an_easier_question(self):
        self.post_first_attempt()

        response = self.client.post(self.url, {
            'action': 'diagnosis',
            'diagnosis_answer': 'I do not know.',
        }, follow=True)

        session = LearningSession.objects.get()
        self.assertEqual(session.current_state, WorkflowState.DIAGNOSIS)
        interactions = list(CoachInteraction.objects.order_by('created_at', 'pk'))
        self.assertEqual(len(interactions), 2)
        self.assertEqual(interactions[-1].interaction_type, CoachInteraction.InteractionType.HINT)
        self.assertEqual(interactions[-1].response['hint_level'], 2)
        self.assertEqual(interactions[-1].response['response_type'], 'concept_reminder')
        self.assertEqual(CoachLearnerResponse.objects.count(), 1)
        self.assertContains(response, 'current level 2 of 4')
        self.assertContains(response, 'which current number must be doubled')
        self.assertNotContains(response, '4. Revision')

    def test_final_diagnosis_answer_must_be_reviewed_before_revision_opens(self):
        self.post_first_attempt()
        for answer in (
            'I do not know.',
            'Still unsure.',
            'No idea yet.',
            'I cannot answer.',
        ):
            self.client.post(self.url, {
                'action': 'diagnosis',
                'diagnosis_answer': answer,
            })

        session = LearningSession.objects.get()
        self.assertEqual(session.current_state, WorkflowState.DIAGNOSIS)
        reveal = CoachInteraction.objects.order_by('-created_at', '-pk').first()
        self.assertTrue(reveal.response['should_reveal_solution'])
        self.assertEqual(reveal.response['response_type'], 'solution_reveal')
        self.assertEqual(reveal.response['hint_level'], 4)
        page = self.client.get(self.url)
        self.assertContains(page, 'Correct conceptual answer:')
        self.assertContains(page, 'Double that number')
        self.assertNotContains(page, 'name="diagnosis_answer"')

        response = self.client.post(self.url, {
            'action': 'acknowledge_diagnosis_solution',
        }, follow=True)

        session.refresh_from_db()
        self.assertEqual(session.current_state, WorkflowState.GUIDED_REVISION)
        self.assertContains(response, '4. Revision')

    def test_diagnosis_solution_cannot_be_acknowledged_before_it_is_unlocked(self):
        self.post_first_attempt()

        response = self.client.post(self.url, {
            'action': 'acknowledge_diagnosis_solution',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'final diagnosis answer has not been unlocked')
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.DIAGNOSIS)

    def test_correct_answer_after_a_hint_resolves_misconception_and_opens_revision(self):
        self.post_first_attempt()
        self.client.post(self.url, {
            'action': 'diagnosis',
            'diagnosis_answer': 'I do not know.',
        })

        self.client.post(self.url, {
            'action': 'diagnosis',
            'diagnosis_answer': 'Double and append each current number during its iteration.',
        })

        session = LearningSession.objects.get()
        self.assertEqual(session.current_state, WorkflowState.GUIDED_REVISION)
        self.assertEqual(
            session.misconceptions.order_by('-created_at', '-pk').first().status,
            MisconceptionRecord.Status.RESOLVED,
        )

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

    @override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY)
    def test_interrupted_clear_passing_attempt_recovers_to_teach_back(self):
        self.post_first_attempt(
            reasoning='Double and collect each current value during the loop.',
            confidence='5',
        )
        learning_session = LearningSession.objects.get()
        learning_session.current_state = WorkflowState.FIRST_ATTEMPT
        learning_session.save(update_fields=('current_state', 'updated_at'))

        page = self.client.get(self.url)

        learning_session.refresh_from_db()
        self.assertEqual(learning_session.current_state, WorkflowState.TEACH_BACK)
        self.assertContains(page, '5. Teach-Back')
        self.assertFalse(CoachInteraction.objects.exists())

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

    def test_revision_final_solution_unlocks_only_after_level_four_and_another_revision(self):
        self.advance_to_revision()
        for expected_level in range(1, 5):
            self.client.post(self.url, {'action': 'hint'})
            self.assertEqual(
                HintUsage.objects.order_by('-created_at').first().level,
                expected_level,
            )
            self.client.post(self.url, {
                'action': 'save_revision',
                'revision-source_code': 'def double_numbers(values):\n    return values',
                'revision-reasoning': 'I am trying the next guided revision.',
                'revision-confidence': '2',
            })

        response = self.client.post(self.url, {'action': 'hint'}, follow=True)

        session = LearningSession.objects.get()
        self.assertEqual(session.current_state, WorkflowState.GUIDED_REVISION)
        reveal = session.coach_interactions.filter(
            request_context__phase='revision',
            response__should_reveal_solution=True,
        ).get()
        self.assertEqual(reveal.response['response_type'], 'solution_reveal')
        self.assertContains(response, 'Final Revision solution:')
        self.assertContains(response, 'result.append(number * 2)')

        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            completed = self.client.post(self.url, {
                'action': 'finish_revision',
                'revision-source_code': 'def double_numbers(numbers):\n    return [number * 2 for number in numbers]',
                'revision-reasoning': 'I apply the revealed concept to each current number.',
                'revision-confidence': '3',
            }, follow=True)
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.TEACH_BACK)
        self.assertContains(completed, '5. Teach-Back')

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
        self.assertContains(self.client.get(self.url), '5. Teach-Back')

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
        teach_back = TeachBackAttempt.objects.get()
        self.assertEqual(teach_back.evaluation, 'PARTIAL_UNDERSTANDING')
        self.assertEqual(
            teach_back.rubric_evidence['unmet_criterion'],
            'identify_original_issue',
        )
        self.assertEqual(
            teach_back.follow_up_question,
            'What value did your original loop use or transform incorrectly?',
        )
        self.assertContains(response, 'Teach-Back needs revision')
        self.assertEqual(response.content.decode().count('Focused follow-up:'), 1)

    @override_settings(AI_PROVIDER_CLASS=PARTIAL_TEACH_BACK_PROVIDER)
    def test_ai_accepts_a_concise_answer_when_core_ideas_are_present(self):
        self.advance_to_revision()
        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            self.client.post(self.url, {
                'action': 'finish_revision',
                'revision-source_code': 'def double_numbers(values):\n    return [value * 2 for value in values]',
                'revision-reasoning': 'Transform each current value.',
                'revision-confidence': '4',
            })
        submitted = {
            'original_issue': 'My first operation targeted the wrong thing.',
            'failure_reason': 'I have not explained this clearly yet.',
            'correction': 'I changed the operation applied inside the iteration.',
            'concept': 'The iterator represents one member at that moment.',
            'prevention': 'I will trace a tiny input next time.',
        }

        response = self.client.post(self.url, {
            'action': 'teach_back',
            **{f'teach-{field}': answer for field, answer in submitted.items()},
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.TRANSFER_TASK)
        teach_back = TeachBackAttempt.objects.get()
        self.assertEqual(teach_back.evaluation, 'CLEAR_UNDERSTANDING')
        self.assertEqual(teach_back.rubric_evidence['evaluation_source'], 'AI')
        self.assertEqual(teach_back.rubric_evidence['minimum_core_fields'], 2)

    def test_teach_back_can_report_misconception_remains_with_one_follow_up(self):
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
            'teach-original_issue': 'The original loop used the wrong current value.',
            'teach-failure_reason': 'Each current item was returned unchanged.',
            'teach-correction': 'I double the whole list after the loop.',
            'teach-concept': 'A for loop processes one item at a time.',
            'teach-prevention': 'I will trace each loop item with a small input.',
        }, follow=True)

        teach_back = TeachBackAttempt.objects.get()
        self.assertEqual(teach_back.evaluation, 'MISCONCEPTION_REMAINS')
        self.assertEqual(
            teach_back.rubric_evidence['misconception_code'],
            'loop-value-misuse',
        )
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.TEACH_BACK)
        latest_misconception = MisconceptionRecord.objects.order_by('-created_at', '-pk').first()
        self.assertEqual(latest_misconception.status, MisconceptionRecord.Status.CONFIRMED)
        self.assertEqual(response.content.decode().count('Focused follow-up:'), 1)
        self.assertContains(response, 'does the loop variable hold one item or the entire list?')

    def test_teach_back_final_answer_requires_acknowledgement_and_blocks_mastery(self):
        self.advance_to_revision()
        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            self.client.post(self.url, {
                'action': 'finish_revision',
                'revision-source_code': 'def double_numbers(values):\n    return [value * 2 for value in values]',
                'revision-reasoning': 'Transform each current value.',
                'revision-confidence': '4',
            })
        incomplete = {
            'action': 'teach_back',
            'teach-original_issue': 'Unsure.',
            'teach-failure_reason': 'I do not know.',
            'teach-correction': 'I do not know.',
            'teach-concept': 'I do not know.',
            'teach-prevention': 'I do not know.',
        }
        for expected_level in range(1, 5):
            response = self.client.post(self.url, incomplete)
            attempt = TeachBackAttempt.objects.order_by('-created_at', '-pk').first()
            self.assertEqual(attempt.rubric_evidence['hint_level'], expected_level)
            self.assertNotEqual(attempt.evaluation, 'ASSISTED_COMPLETION')
            self.assertEqual(response.status_code, 200)

        response = self.client.post(self.url, incomplete)
        assisted = TeachBackAttempt.objects.order_by('-created_at', '-pk').first()
        self.assertEqual(assisted.evaluation, 'ASSISTED_COMPLETION')
        self.assertTrue(assisted.rubric_evidence['solution_revealed'])
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.TEACH_BACK)
        self.assertContains(response, 'Correct conceptual answer:')
        self.assertNotContains(response, 'name="teach-original_issue"')

        transfer_page = self.client.post(self.url, {
            'action': 'acknowledge_teach_back_solution',
        }, follow=True)
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.TRANSFER_TASK)
        self.assertContains(transfer_page, '6. Transfer Check')

        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            self.client.post(self.url, {
                'action': 'transfer',
                'transfer-source_code': 'def word_lengths(words):\n    return [len(word) for word in words]',
                'transfer-reasoning': 'Transform each current word into its length.',
                'transfer-confidence': '4',
            })
        mastery = ConceptMastery.objects.get()
        self.assertEqual(mastery.status, ConceptMastery.Status.NEEDS_REVIEW)
        self.assertIn('Teach-Back', mastery.reason)

    @override_settings(CODE_RUNNER_URL='', CODE_RUNNER_GATEWAY_CLASS='')
    def test_unavailable_runner_saves_transfer_and_keeps_check_open_for_retry(self):
        self.advance_to_transfer()
        self.assertEqual(TeachBackAttempt.objects.count(), 1)
        page = self.client.get(self.url)
        self.assertContains(page, '6. Transfer Check')
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
        session = LearningSession.objects.get()
        self.assertEqual(session.current_state, WorkflowState.TRANSFER_TASK)
        self.assertFalse(ConceptMastery.objects.exists())
        retry_page = self.client.get(self.url)
        self.assertContains(retry_page, 'You may retry without losing the saved attempt')
        self.assertContains(retry_page, 'def word_lengths(words)')

    @override_settings(CODE_RUNNER_URL='', CODE_RUNNER_GATEWAY_CLASS='')
    def test_transfer_can_retry_after_not_executed_and_then_reach_mastery(self):
        self.advance_to_transfer()
        transfer_data = {
            'action': 'transfer',
            'transfer-source_code': 'def word_lengths(words):\n    return [len(word) for word in words]',
            'transfer-reasoning': 'Transform each current word into its length.',
            'transfer-confidence': '5',
        }
        first_response = self.client.post(self.url, transfer_data, follow=True)
        self.assertContains(first_response, 'This step remains open')

        with override_settings(CODE_RUNNER_GATEWAY_CLASS=PASSING_GATEWAY):
            retry_response = self.client.post(self.url, transfer_data, follow=True)

        evaluations = list(
            TransferAttempt.objects.order_by('created_at', 'pk')
            .values_list('evaluation__status', flat=True)
        )
        self.assertEqual(evaluations, ['NOT_EXECUTED', 'PASSED'])
        self.assertEqual(LearningSession.objects.get().current_state, WorkflowState.MASTERED)
        self.assertEqual(ConceptMastery.objects.get().status, ConceptMastery.Status.MASTERED)
        self.assertContains(retry_response, 'Learning session completed')

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
        self.assertContains(response, 'Mastered: The original exercise passed')
        self.assertContains(response, 'Status: PASSED')
        mastery = ConceptMastery.objects.get()
        self.assertEqual(mastery.status, ConceptMastery.Status.MASTERED)
        self.assertIn('unassisted Transfer Check passed', mastery.reason)

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
        self.assertEqual(LearningSession.objects.count(), 2)
        ended = LearningSession.objects.get(browser_session_key=self.client.session.session_key)
        self.assertIsNotNone(ended.ended_at)
        remaining = LearningSession.objects.get(browser_session_key=other.session.session_key)
        self.assertIsNone(remaining.ended_at)


@override_settings(AI_PROVIDER_CLASS='')
class CodingWorkflowServiceTests(TestCase):
    def setUp(self):
        self.exercise = ensure_demo_exercise()
        self.session, _ = get_demo_session(browser_session_key='service-browser', exercise=self.exercise)
        transition_session(self.session, WorkflowState.DIAGNOSTIC_QUIZ)
        submit_plan(
            learning_session=self.session,
            exercise=self.exercise,
            solution_plan='Transform each current value and collect the result.',
            predicted_output='[2, 6]',
        )

    def submit_first(self, gateway=None, ai_provider=None):
        return submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(values):\n    return values',
            reasoning='I will transform the values.',
            confidence=3,
            gateway=gateway,
            ai_provider=ai_provider,
        )

    def advance_confirmed_misconception_to_transfer(self, gateway):
        self.submit_first(gateway=gateway)
        diagnosis = submit_diagnosis(
            learning_session=self.session,
            answer='I think the whole list should be doubled after the loop.',
        )
        self.assertEqual(diagnosis.status, MisconceptionRecord.Status.CONFIRMED)
        for answer in ('I still do not know.', 'Maybe the collection changes.', 'I cannot explain it.'):
            submit_diagnosis(learning_session=self.session, answer=answer)
        acknowledge_diagnosis_solution(learning_session=self.session)
        submit_revision(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(values):\n    return [value * 2 for value in values]',
            reasoning='Double each current value.',
            confidence=4,
            gateway=gateway,
        )
        submit_teach_back(learning_session=self.session, response={
            'original_issue': 'The original attempt returned values without transforming them.',
            'failure_reason': 'It failed because every current item stayed unchanged.',
            'correction': 'I double each current value and append it to the result.',
            'concept': 'A for loop processes one item or value on every iteration.',
            'prevention': 'I will trace one loop iteration before submitting future code.',
        })

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

    def test_output_mismatch_is_stored_and_cannot_skip_diagnosis(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(
            status=ExecutionStatus.OUTPUT_MISMATCH,
            message='A public test returned an unexpected result.',
            tests=({
                'id': 'double-public',
                'passed': False,
                'expected': [2, 6],
                'actual': [1, 3],
            },),
        )

        attempt, result = submit_first_attempt(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(numbers):\n    return numbers',
            reasoning='Double and collect each current value.',
            confidence=5,
            gateway=gateway,
        )

        self.session.refresh_from_db()
        self.assertEqual(result.status, ExecutionStatus.OUTPUT_MISMATCH)
        self.assertEqual(attempt.evaluation['status'], 'OUTPUT_MISMATCH')
        self.assertEqual(
            attempt.evaluation['response_evaluation']['outcome'],
            'DIAGNOSIS_REQUIRED',
        )
        self.assertEqual(self.session.current_state, WorkflowState.DIAGNOSIS)
        self.assertFalse(self.session.teach_back_attempts.exists())
        self.assertFalse(self.session.mastery_records.exists())

    def test_square_exercise_uses_its_own_database_catalog_and_runner_ids(self):
        exercise = CodingExercise.objects.get(slug='square-numbers')
        session, _ = get_demo_session(
            browser_session_key='square-service-browser',
            exercise=exercise,
        )
        transition_session(session, WorkflowState.DIAGNOSTIC_QUIZ)
        submit_plan(
            learning_session=session,
            exercise=exercise,
            solution_plan='Square each current number and collect the result.',
            predicted_output='[4, 9]',
        )
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.PASSED, 'Passed')

        submit_first_attempt(
            learning_session=session,
            exercise=exercise,
            source_code='def square_numbers(numbers):\n    return [number ** 2 for number in numbers]',
            reasoning='Square and collect each current number.',
            confidence=3,
            gateway=gateway,
        )

        request = gateway.run.call_args.args[0]
        self.assertEqual(
            request.test_case_ids,
            ('square-public', 'empty-square', 'zero-square'),
        )
        self.assertEqual(session.activity_id, exercise.activity_id)
        question = session.coach_interactions.get(interaction_type='DIAGNOSTIC')
        self.assertIn('squared', question.response['message'])

    def test_ai_provider_receives_only_privacy_minimized_signals(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(
            status=ExecutionStatus.FAILED,
            message='Isolated test evidence',
        )
        provider = Mock()
        provider.generate.return_value = PassingDiagnosticProvider().generate()

        self.submit_first(gateway=gateway, ai_provider=provider)

        user_prompt = provider.generate.call_args.kwargs['user_prompt']
        self.assertNotIn('def double_numbers', user_prompt)
        self.assertNotIn('I will transform the values', user_prompt)
        self.assertIn('data_minimized', user_prompt)
        self.assertEqual(CoachInteraction.objects.get().source, CoachInteraction.Source.AI)

    def test_ai_semantically_accepts_diagnosis_without_keyword_rule_controlling_transition(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.FAILED, 'Failed')
        self.submit_first(gateway=gateway)
        provider = Mock()
        provider.generate.return_value = {
            'understood': True,
            'feedback': 'The learner identifies the per-iteration binding and transformation.',
            'possible_misconception': 'loop-value-misuse',
            'diagnostic_confidence': 0.9,
            'response_type': 'concept_reminder',
            'message': 'Which current number is transformed during one iteration?',
            'hint_level': 2,
            'should_reveal_solution': False,
        }

        record = submit_diagnosis(
            learning_session=self.session,
            answer='The temporary binding denotes a single member; scaling occurs before retention.',
            ai_provider=provider,
        )

        self.session.refresh_from_db()
        self.assertEqual(record.status, MisconceptionRecord.Status.DISMISSED)
        self.assertEqual(self.session.current_state, WorkflowState.GUIDED_REVISION)
        self.assertIn('AI diagnosis evaluation', record.evidence)
        prompt = provider.generate.call_args.kwargs['user_prompt']
        self.assertNotIn('def double_numbers', prompt)
        self.assertNotIn('service-browser', prompt)

    def test_diagnosis_preserves_hypothesis_then_confirms_or_dismisses_it(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.FAILED, 'Failed')
        self.submit_first(gateway=gateway)

        diagnosis = submit_diagnosis(
            learning_session=self.session,
            answer='I think the whole list should be doubled after the loop.',
        )

        records = list(MisconceptionRecord.objects.order_by('created_at', 'pk'))
        self.assertEqual([item.status for item in records], [
            MisconceptionRecord.Status.HYPOTHESIS,
            MisconceptionRecord.Status.CONFIRMED,
        ])
        self.assertEqual(diagnosis.supersedes, records[0])

    def test_teach_back_evaluation_uses_the_exercise_rubric(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.PASSED, 'Passed')
        self.submit_first(gateway=gateway)
        submit_diagnosis(
            learning_session=self.session,
            answer='Double and append each current loop value.',
        )
        submit_revision(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(values):\n    return [value * 2 for value in values]',
            reasoning='Double each current value.',
            confidence=4,
            gateway=gateway,
        )
        activity = self.exercise.activity
        activity.rubric = {
            **activity.rubric,
            'teach_back': {
                'criteria': [{
                    'id': 'exercise_specific_criterion',
                    'field': 'concept',
                    'required_groups': [['exercise-specific-evidence']],
                    'feedback': 'This exercise requires its own rubric evidence.',
                    'follow_up_question': 'What evidence is specific to this exercise?',
                }],
                'misconceptions': [],
            },
        }
        activity.save(update_fields=('rubric',))

        teach_back = submit_teach_back(learning_session=self.session, response={
            'original_issue': 'The original loop used the wrong current value.',
            'failure_reason': 'Each current item was returned unchanged.',
            'correction': 'I doubled each current value before collecting it.',
            'concept': 'A for loop processes one item at a time.',
            'prevention': 'I will trace each loop item with a small input.',
        })

        self.assertEqual(teach_back.evaluation, 'PARTIAL_UNDERSTANDING')
        self.assertEqual(
            teach_back.rubric_evidence['unmet_criterion'],
            'exercise_specific_criterion',
        )
        self.assertEqual(
            teach_back.follow_up_question,
            'What evidence is specific to this exercise?',
        )

    def test_ai_accepts_semantic_main_idea_without_exact_fallback_keywords(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.PASSED, 'Passed')
        self.submit_first(gateway=gateway)
        submit_diagnosis(
            learning_session=self.session,
            answer='Double the member available at that moment.',
        )
        submit_revision(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def double_numbers(values):\n    return [value * 2 for value in values]',
            reasoning='Transform the member exposed by the iterator.',
            confidence=4,
            gateway=gateway,
        )
        provider = Mock()
        provider.generate.return_value = {
            'field_evaluations': [
                {'field': field, 'understood': True, 'feedback': ''}
                for field in ('original_issue', 'failure_reason', 'correction', 'concept', 'prevention')
            ],
            'misconception_code': 'none',
            'follow_up_question': '',
        }

        teach_back = submit_teach_back(
            learning_session=self.session,
            response={
                'original_issue': 'I acted on the wrong object.',
                'failure_reason': 'At a single pass, the exposed member was left with the wrong output.',
                'correction': 'I now change that member before storing the outcome.',
                'concept': 'The iterator refers to one member at that moment.',
                'prevention': 'I will walk through a tiny case by hand.',
            },
            ai_provider=provider,
        )

        self.assertEqual(teach_back.evaluation, 'CLEAR_UNDERSTANDING')
        self.assertEqual(teach_back.rubric_evidence['evaluation_source'], 'AI')
        self.assertTrue(teach_back.rubric_evidence['data_minimized'])
        user_prompt = provider.generate.call_args.kwargs['user_prompt']
        self.assertNotIn('def double_numbers', user_prompt)
        self.assertNotIn('service-browser', user_prompt)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

    def test_passing_transfer_resolves_a_confirmed_misconception(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.PASSED, 'Passed')
        self.advance_confirmed_misconception_to_transfer(gateway)

        submit_transfer_check(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def word_lengths(words):\n    return [len(word) for word in words]',
            reasoning='Transform each current word into its length.',
            confidence=5,
            gateway=gateway,
        )

        self.session.refresh_from_db()
        latest = self.session.misconceptions.order_by('-created_at', '-pk').first()
        self.assertEqual(latest.status, MisconceptionRecord.Status.RESOLVED)
        self.assertEqual(self.session.current_state, WorkflowState.MASTERED)
        self.assertEqual(
            self.session.mastery_records.get().status,
            ConceptMastery.Status.MASTERED,
        )

    def test_repeated_misconception_blocks_mastery_even_when_transfer_tests_pass(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.PASSED, 'Passed')
        self.advance_confirmed_misconception_to_transfer(gateway)

        submit_transfer_check(
            learning_session=self.session,
            exercise=self.exercise,
            source_code='def word_lengths(words):\n    return [len(word) for word in words]',
            reasoning='I handled the whole list at once.',
            confidence=5,
            gateway=gateway,
        )

        self.session.refresh_from_db()
        repeated = self.session.misconceptions.get(status=MisconceptionRecord.Status.REPEATED)
        mastery = self.session.mastery_records.get()
        self.assertEqual(self.session.current_state, WorkflowState.NEEDS_REVIEW)
        self.assertEqual(mastery.status, ConceptMastery.Status.NEEDS_REVIEW)
        self.assertIn(repeated.code, mastery.reason)
        self.assertIn(repeated.pk, mastery.evidence['misconception_record_ids'])

    def test_terminal_transition_requires_a_stored_mastery_decision(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(ExecutionStatus.PASSED, 'Passed')
        self.advance_confirmed_misconception_to_transfer(gateway)

        with self.assertRaisesMessage(InvalidWorkflowTransition, 'stored mastery decision'):
            transition_session(self.session, WorkflowState.MASTERED)

        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

    def test_full_service_flow_with_stub_gateway_can_reach_mastered(self):
        gateway = Mock()
        gateway.run.return_value = ExecutionResult(
            status=ExecutionStatus.PASSED,
            message='Passed in isolated stub.',
        )
        self.submit_first(gateway=gateway)
        submit_diagnosis(
            learning_session=self.session,
            answer='Double and append each current loop value.',
        )
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
        submit_diagnosis(
            learning_session=self.session,
            answer='Double and append each current loop value.',
        )
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
        submit_diagnosis(
            learning_session=self.session,
            answer='Double and append the current loop item.',
        )
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


class CatalogValidationEdgeCaseTests(SimpleTestCase):
    def test_validate_catalog_rejects_empty_allowed_misconception_codes(self):
        catalog = deepcopy(CODING_CATALOG)
        catalog[0]['rubric']['allowed_misconception_codes'] = []
        errors = validate_catalog(catalog)
        self.assertTrue(any('allowed_misconception_codes' in err for err in errors))

    def test_validate_catalog_rejects_non_string_allowed_misconception_codes(self):
        catalog = deepcopy(CODING_CATALOG)
        catalog[0]['rubric']['allowed_misconception_codes'] = [123, '']
        errors = validate_catalog(catalog)
        self.assertTrue(any('allowed_misconception_codes' in err for err in errors))

    def test_validate_catalog_rejects_malformed_service_consumed_fields(self):
        cases = (
            (
                'unhashable slug',
                lambda item: item.__setitem__('slug', []),
                '.slug must be a non-empty string',
            ),
            (
                'diagnosis object',
                lambda item: item['rubric'].__setitem__('diagnosis', []),
                '.rubric.diagnosis must be an object',
            ),
            (
                'non-object activity rubric',
                lambda item: item.__setitem__('rubric', []),
                '.rubric must be an object',
            ),
            (
                'unhashable public test ID',
                lambda item: item.__setitem__('public_test_ids', [[]]),
                '.public_test_ids',
            ),
            (
                'diagnosis hint',
                lambda item: item['rubric']['diagnosis']['hints'].__setitem__('3', ''),
                '.rubric.diagnosis.hints.3',
            ),
            (
                'revision hint count',
                lambda item: item['rubric'].__setitem__('revision_hints', ['One?']),
                '.rubric.revision_hints must contain exactly 4 items',
            ),
            (
                'teach-back marker group',
                lambda item: item['rubric']['teach_back']['criteria'][0].__setitem__(
                    'required_groups', [[]]
                ),
                '.required_groups[0]',
            ),
            (
                'uncurated teach-back misconception',
                lambda item: item['rubric']['teach_back']['misconceptions'][0].__setitem__(
                    'code', 'uncurated-code'
                ),
                'must appear in allowed_misconception_codes',
            ),
            (
                'transfer action terms',
                lambda item: item['transfer'].__setitem__('action_terms', [123]),
                '.transfer.action_terms',
            ),
        )

        for label, mutate, expected_error in cases:
            with self.subTest(label=label):
                catalog = deepcopy(CODING_CATALOG)
                mutate(catalog[0])

                errors = validate_catalog(catalog)

                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )
