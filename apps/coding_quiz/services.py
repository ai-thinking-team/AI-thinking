import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.code_runner.runner import ExecutionStatus, get_code_execution_gateway
from apps.code_runner.test_service import build_python_request
from apps.learning_core.models import (
    Concept,
    HintUsage,
    LearnerAttempt,
    LearningActivity,
    LearningSession,
    MisconceptionRecord,
    Subject,
    TeachBackAttempt,
    Topic,
    TransferAttempt,
)
from apps.learning_core.services import (
    get_or_create_demo_session,
    mastery_requirements_met,
    transition_session,
)
from apps.learning_core.state_machine import WorkflowState, hints_allowed
from apps.learning_core.validators import validate_first_attempt

from .models import CodingExercise

CURATED_HINTS = (
    'Which value changes on each pass through the loop?',
    'A loop processes each item in order; check which variable represents the current item.',
    'In a different list, `for colour in colours` gives one colour at a time. Compare that pattern with yours.',
    'Keep the loop header and result container, then fill in only the expression that transforms the current item.',
)

DIAGNOSTIC_QUESTION = (
    'Inside the loop, which single value should be doubled, and when should it be added '
    'to the result list?'
)

TEACH_BACK_MIN_LENGTH = 20
CONCEPT_TERMS = ('loop', 'for', 'iteration', 'item', 'value', 'vòng lặp', 'phần tử')
CORRECTION_TERMS = ('double', 'multiply', '* 2', 'twice', 'nhân', 'gấp đôi')


def _execution_evidence(result):
    return {
        'status': result.status.value,
        'message': result.message,
        'tests': list(result.tests),
    }


def _original_test_case_ids(exercise):
    public_ids = exercise.activity.rubric.get('public_test_ids', ())
    return tuple(public_ids) + tuple(exercise.hidden_test_ids)


def _evaluate_teach_back(response):
    feedback = []
    for field_name, answer in response.items():
        if len(answer.strip()) < TEACH_BACK_MIN_LENGTH:
            readable_name = field_name.replace('_', ' ').title()
            feedback.append(f'{readable_name} needs a more specific explanation.')

    concept_text = response.get('concept', '').lower()
    if not any(term in concept_text for term in CONCEPT_TERMS):
        feedback.append('Name the loop/item concept that explains the correction.')
    correction_text = response.get('correction', '').lower()
    if not any(term in correction_text for term in CORRECTION_TERMS):
        feedback.append('Explain how each current value is transformed in the correction.')

    if feedback:
        return 'PARTIAL_UNDERSTANDING', ' '.join(feedback)
    return 'CLEAR_UNDERSTANDING', (
        'The explanation covers the error, cause, correction, concept, and prevention.'
    )


@transaction.atomic
def ensure_transfer_activity(exercise):
    activity, _ = LearningActivity.objects.get_or_create(
        concept=exercise.activity.concept,
        title='Word lengths transfer check',
        defaults={
            'activity_type': 'coding_transfer',
            'prompt': exercise.transfer_prompt,
            'rubric': {
                'concept': 'loop_values',
                'hidden_test_ids': ['empty-words', 'mixed-word-lengths'],
                'unassisted': True,
            },
        },
    )
    return activity


@transaction.atomic
def ensure_demo_exercise():
    subject, _ = Subject.objects.get_or_create(
        slug='coding', defaults={'name': 'Coding', 'description': 'Beginner Python'}
    )
    topic, _ = Topic.objects.get_or_create(
        subject=subject,
        slug='python-loops',
        defaults={'name': 'Python loops', 'description': 'Iterating over lists'},
    )
    concept, _ = Concept.objects.get_or_create(
        topic=topic,
        slug='loop-values',
        defaults={'name': 'Loop variables', 'description': 'Use each loop value deliberately.'},
    )
    activity, _ = LearningActivity.objects.get_or_create(
        concept=concept,
        title='Double every number',
        defaults={
            'activity_type': 'coding',
            'prompt': 'Write a function that returns a new list containing twice each input number.',
            'rubric': {'concept': 'loop_values', 'requires_transfer': True},
        },
    )
    required_rubric = {
        **activity.rubric,
        'concept': 'loop_values',
        'requires_transfer': True,
        'public_test_ids': ['double-public'],
    }
    if activity.rubric != required_rubric:
        activity.rubric = required_rubric
        activity.save(update_fields=('rubric',))
    exercise, _ = CodingExercise.objects.get_or_create(
        activity=activity,
        defaults={
            'starter_code': 'def double_numbers(numbers):\n    result = []\n    # Add your loop here\n    return result',
            'public_test_description': 'double_numbers([1, 3]) should return [2, 6].',
            'hidden_test_ids': ['empty-list', 'negative-values'],
            'transfer_prompt': 'Return the length of each word in a new list.',
        },
    )
    return exercise


@transaction.atomic
def submit_first_attempt(*, learning_session, exercise, source_code, reasoning, confidence, gateway=None):
    validate_first_attempt(answer=source_code, reasoning=reasoning, confidence=confidence)
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.DIAGNOSTIC_QUIZ:
        raise ValidationError('Your first attempt has already been submitted. Continue with the current step.')
    if locked_session.attempts.filter(revision_number=0).exists():
        raise ValidationError('Your first attempt has already been saved.')

    attempt = LearnerAttempt.objects.create(
        learning_session=locked_session,
        activity=exercise.activity,
        answer=source_code,
        reasoning=reasoning,
        confidence=confidence,
    )
    transition_session(locked_session, WorkflowState.FIRST_ATTEMPT)
    runner = gateway or get_code_execution_gateway()
    result = runner.run(build_python_request(
        source_code=source_code,
        test_case_ids=_original_test_case_ids(exercise),
    ))
    attempt.evaluation = _execution_evidence(result)
    attempt.save(update_fields=('evaluation',))
    transition_session(locked_session, WorkflowState.RESPONSE_EVALUATION)
    transition_session(locked_session, WorkflowState.DIAGNOSIS)
    learning_session.current_state = locked_session.current_state
    return attempt, result


@transaction.atomic
def submit_diagnosis(*, learning_session, answer):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.DIAGNOSIS:
        raise ValidationError('The diagnosis question is not available at this step.')
    answer = answer.strip()
    if not answer:
        raise ValidationError('Answer the diagnosis question before continuing.')
    record = MisconceptionRecord.objects.create(
        learning_session=locked_session,
        concept=locked_session.topic.concepts.first(),
        code='loop-value-diagnosis',
        evidence=answer,
        confirmed=False,
    )
    transition_session(locked_session, WorkflowState.GUIDED_REVISION)
    learning_session.current_state = locked_session.current_state
    return record


@transaction.atomic
def submit_revision(*, learning_session, exercise, source_code, reasoning, confidence, gateway=None,
                    finish=True):
    validate_first_attempt(answer=source_code, reasoning=reasoning, confidence=confidence)
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.GUIDED_REVISION:
        raise ValidationError('A revision can be submitted only during the Revision step.')
    latest_number = locked_session.attempts.order_by('-revision_number').values_list(
        'revision_number', flat=True
    ).first()
    attempt = LearnerAttempt.objects.create(
        learning_session=locked_session,
        activity=exercise.activity,
        answer=source_code,
        reasoning=reasoning,
        confidence=confidence,
        revision_number=(latest_number or 0) + 1,
    )
    runner = gateway or get_code_execution_gateway()
    result = runner.run(build_python_request(
        source_code=source_code,
        test_case_ids=_original_test_case_ids(exercise),
    ))
    attempt.evaluation = _execution_evidence(result)
    attempt.save(update_fields=('evaluation',))
    if finish and result.status == ExecutionStatus.PASSED:
        transition_session(locked_session, WorkflowState.TEACH_BACK)
        learning_session.current_state = locked_session.current_state
    return attempt, result


@transaction.atomic
def submit_teach_back(*, learning_session, response):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.TEACH_BACK:
        raise ValidationError('Teach-Back is not available at this step.')
    verified_revision = locked_session.attempts.order_by('-revision_number', '-created_at').first()
    if not verified_revision or verified_revision.evaluation.get('status') != ExecutionStatus.PASSED.value:
        raise ValidationError('Teach-Back requires a revision verified as PASSED by the isolated runner.')
    evaluation, feedback = _evaluate_teach_back(response)
    teach_back = TeachBackAttempt.objects.create(
        learning_session=locked_session,
        response=json.dumps(response, ensure_ascii=False),
        evaluation=evaluation,
        feedback=feedback,
    )
    if evaluation == 'CLEAR_UNDERSTANDING':
        transition_session(locked_session, WorkflowState.TRANSFER_TASK)
        learning_session.current_state = locked_session.current_state
    return teach_back


@transaction.atomic
def submit_transfer_check(*, learning_session, exercise, source_code, reasoning, confidence,
                          gateway=None):
    validate_first_attempt(answer=source_code, reasoning=reasoning, confidence=confidence)
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.TRANSFER_TASK:
        raise ValidationError('The Transfer Check is not available at this step.')
    if locked_session.transfer_attempts.exists():
        raise ValidationError('Your Transfer Check has already been saved.')
    original_attempt = locked_session.attempts.order_by('-revision_number', '-created_at').first()
    original_passed = bool(
        original_attempt and original_attempt.evaluation.get('status') == ExecutionStatus.PASSED.value
    )
    if not original_passed:
        raise ValidationError('Transfer Check requires a revision verified as PASSED by the isolated runner.')
    teach_back = locked_session.teach_back_attempts.order_by('-created_at').first()
    teach_back_clear = bool(
        teach_back and teach_back.evaluation == 'CLEAR_UNDERSTANDING'
    )
    if not teach_back_clear:
        raise ValidationError('Transfer Check requires a clear Teach-Back evaluation.')

    transfer_activity = ensure_transfer_activity(exercise)
    test_case_ids = transfer_activity.rubric.get('hidden_test_ids', ())
    runner = gateway or get_code_execution_gateway()
    result = runner.run(build_python_request(
        source_code=source_code,
        test_case_ids=test_case_ids,
    ))
    transfer = TransferAttempt.objects.create(
        learning_session=locked_session,
        activity=transfer_activity,
        response=source_code,
        reasoning=reasoning,
        confidence=confidence,
        used_assistance=False,
        passed=result.status == ExecutionStatus.PASSED,
        evaluation=_execution_evidence(result),
    )
    mastered = mastery_requirements_met(
        original_passed=original_passed,
        teach_back_clear=teach_back_clear,
        transfer_passed=transfer.passed,
        transfer_unassisted=not transfer.used_assistance,
        misconception_repeated=False,
    )
    target = WorkflowState.MASTERED if mastered else WorkflowState.NEEDS_REVIEW
    transition_session(locked_session, target)
    learning_session.current_state = locked_session.current_state
    return transfer, result


@transaction.atomic
def request_curated_hint(*, learning_session):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if not hints_allowed(locked_session.current_state):
        raise PermissionDenied('Hints are available only during guided revision.')
    latest_attempt = locked_session.attempts.order_by('-created_at').first()
    if latest_attempt is None:
        raise PermissionDenied('Submit an attempt before requesting a hint.')

    latest_hint = HintUsage.objects.filter(
        learner_attempt__learning_session=locked_session
    ).order_by('-created_at').first()
    if latest_hint and not locked_session.attempts.filter(
        created_at__gt=latest_hint.created_at
    ).exists():
        raise PermissionDenied('Revise your work before unlocking the next hint.')
    next_level = 1 if latest_hint is None else latest_hint.level + 1
    if next_level > len(CURATED_HINTS):
        raise PermissionDenied('The four-level hint ladder is complete.')
    return HintUsage.objects.create(
        learner_attempt=latest_attempt,
        level=next_level,
        content=CURATED_HINTS[next_level - 1],
    )


def begin_teach_back(*, learning_session, original_passed):
    if not original_passed:
        raise PermissionDenied('Teach-Back requires the original exercise to pass isolated tests.')
    return transition_session(learning_session, WorkflowState.TEACH_BACK)


def begin_transfer_check(*, learning_session, teach_back_evaluation):
    if teach_back_evaluation != 'CLEAR_UNDERSTANDING':
        raise PermissionDenied('Transfer Check requires an acceptable Teach-Back.')
    return transition_session(learning_session, WorkflowState.TRANSFER_TASK)


def complete_transfer_check(*, learning_session, original_passed, teach_back_clear,
                            transfer_passed, used_assistance, misconception_repeated):
    mastered = mastery_requirements_met(
        original_passed=original_passed,
        teach_back_clear=teach_back_clear,
        transfer_passed=transfer_passed,
        transfer_unassisted=not used_assistance,
        misconception_repeated=misconception_repeated,
    )
    target = WorkflowState.MASTERED if mastered else WorkflowState.NEEDS_REVIEW
    transition_session(learning_session, target)
    return target


def get_demo_session(*, browser_session_key, exercise):
    return get_or_create_demo_session(
        browser_session_key=browser_session_key,
        topic=exercise.activity.concept.topic,
    )


@transaction.atomic
def recover_interrupted_first_attempt(*, learning_session):
    """Finish transient transitions left by an interrupted older request."""
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    has_first_attempt = locked_session.attempts.filter(revision_number=0).exists()
    if not has_first_attempt:
        return learning_session
    if locked_session.current_state == WorkflowState.FIRST_ATTEMPT:
        transition_session(locked_session, WorkflowState.RESPONSE_EVALUATION)
    if locked_session.current_state == WorkflowState.RESPONSE_EVALUATION:
        transition_session(locked_session, WorkflowState.DIAGNOSIS)
    learning_session.current_state = locked_session.current_state
    return learning_session


@transaction.atomic
def reset_demo_session(*, browser_session_key, exercise):
    LearningSession.objects.filter(
        browser_session_key=browser_session_key,
        topic=exercise.activity.concept.topic,
    ).delete()
