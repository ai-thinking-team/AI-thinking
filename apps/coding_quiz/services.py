from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.code_runner.runner import UnavailableCodeExecutionGateway
from apps.code_runner.test_service import build_python_request
from apps.learning_core.models import (
    Concept,
    HintUsage,
    LearnerAttempt,
    LearningActivity,
    Subject,
    Topic,
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
    if learning_session.current_state != WorkflowState.DIAGNOSTIC_QUIZ:
        raise ValidationError('A first attempt is accepted only after the diagnostic stage begins.')

    attempt = LearnerAttempt.objects.create(
        learning_session=learning_session,
        activity=exercise.activity,
        answer=source_code,
        reasoning=reasoning,
        confidence=confidence,
    )
    transition_session(learning_session, WorkflowState.FIRST_ATTEMPT)
    runner = gateway or UnavailableCodeExecutionGateway()
    result = runner.run(build_python_request(
        source_code=source_code,
        test_case_ids=exercise.hidden_test_ids,
    ))
    attempt.evaluation = {'status': result.status.value, 'message': result.message}
    attempt.save(update_fields=('evaluation',))
    return attempt, result


@transaction.atomic
def request_curated_hint(*, learning_session):
    if not hints_allowed(learning_session.current_state):
        raise PermissionDenied('Hints are available only during guided revision.')
    latest_attempt = learning_session.attempts.order_by('-created_at').first()
    if latest_attempt is None:
        raise PermissionDenied('Submit an attempt before requesting a hint.')

    latest_hint = HintUsage.objects.filter(
        learner_attempt__learning_session=learning_session
    ).order_by('-created_at').first()
    if latest_hint and not learning_session.attempts.filter(
        pk__gt=latest_hint.learner_attempt_id
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
