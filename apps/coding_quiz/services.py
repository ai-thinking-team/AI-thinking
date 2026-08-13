import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.ai_engine.client import generate_ai_response
from apps.ai_engine.exceptions import AIEngineError
from apps.code_runner.runner import ExecutionStatus, get_code_execution_gateway
from apps.code_runner.test_service import build_python_request
from apps.learning_core.models import (
    Concept,
    DiagnosticQuizAttempt,
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

from . import ai_prompts
from .models import CodingExercise

CONFIDENT_THRESHOLD = 4  # 1-5 scale; 4 = "fairly confident", 5 = "can explain"

CURATED_HINTS = (
    'Which value changes on each pass through the loop?',
    'A loop processes each item in order; check which variable represents the current item.',
    'In a different list, `for colour in colours` gives one colour at a time. Compare that pattern with yours.',
    'Keep the loop header and result container, then fill in only the expression that transforms the current item.',
    'Last resort — the complete solution: '
    'def double_numbers(numbers):\n    result = []\n    for number in numbers:\n        result.append(number * 2)\n    return result',
)

FALLBACK_DIAGNOSTIC_QUIZ_QUESTION = (
    'Before you start: what does a `for item in a_list:` loop do, in your own words?'
)
FALLBACK_DIAGNOSIS_QUESTION = (
    'Inside the loop, which single value should be doubled, and when should it be added '
    'to the result list?'
)
FALLBACK_VERIFICATION_QUESTION = (
    'You passed the tests — in your own words, why does your loop double every number, '
    'not just the first one?'
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


def _evaluate_teach_back_heuristic(response):
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
        return 'PARTIAL_UNDERSTANDING', ' '.join(feedback), ''
    return (
        'CLEAR_UNDERSTANDING',
        'The explanation covers the error, cause, correction, concept, and prevention.',
        '',
    )


def _next_state_after_evaluation(*, status, confidence):
    if status == ExecutionStatus.PASSED and confidence >= CONFIDENT_THRESHOLD:
        return WorkflowState.TEACH_BACK
    if status == ExecutionStatus.PASSED:
        return WorkflowState.VERIFICATION
    return WorkflowState.DIAGNOSIS


def _generate_diagnostic_quiz_question(*, topic):
    try:
        text = generate_ai_response(
            system_prompt=ai_prompts.DIAGNOSTIC_QUIZ_SYSTEM_PROMPT,
            user_prompt=f'Topic: {topic.name}\nDescription: {topic.description}',
            response_schema=ai_prompts.DIAGNOSTIC_QUIZ_SCHEMA,
        )
        return json.loads(text)['question'], DiagnosticQuizAttempt.Source.AI
    except (AIEngineError, json.JSONDecodeError, KeyError):
        return FALLBACK_DIAGNOSTIC_QUIZ_QUESTION, DiagnosticQuizAttempt.Source.CURATED


def _generate_diagnosis_question(*, exercise, attempt):
    try:
        text = generate_ai_response(
            system_prompt=ai_prompts.DIAGNOSIS_SYSTEM_PROMPT,
            user_prompt=(
                f'Exercise: {exercise.activity.prompt}\n\n'
                f"Learner's code:\n{attempt.answer}\n\n"
                f"Learner's reasoning: {attempt.reasoning}"
            ),
            response_schema=ai_prompts.DIAGNOSIS_SCHEMA,
        )
        data = json.loads(text)
        return data['question'], data['possible_misconception']
    except (AIEngineError, json.JSONDecodeError, KeyError):
        return FALLBACK_DIAGNOSIS_QUESTION, ''


def _generate_verification_question(*, exercise, attempt):
    try:
        text = generate_ai_response(
            system_prompt=ai_prompts.VERIFICATION_SYSTEM_PROMPT,
            user_prompt=(
                f'Exercise: {exercise.activity.prompt}\n\n'
                f"Learner's code:\n{attempt.answer}\n\n"
                f"Learner's reasoning: {attempt.reasoning}"
            ),
            response_schema=ai_prompts.VERIFICATION_SCHEMA,
        )
        return json.loads(text)['question']
    except (AIEngineError, json.JSONDecodeError, KeyError):
        return FALLBACK_VERIFICATION_QUESTION


def _generate_hint_content(*, level, exercise, attempt):
    try:
        text = generate_ai_response(
            system_prompt=ai_prompts.HINT_SYSTEM_PROMPT,
            user_prompt=(
                f'Hint level requested: {level}\n'
                f'Exercise: {exercise.activity.prompt}\n\n'
                f"Learner's current code:\n{attempt.answer}\n\n"
                f"Learner's reasoning: {attempt.reasoning}"
            ),
            response_schema=ai_prompts.HINT_SCHEMA,
        )
        return json.loads(text)['content'], 'ai'
    except (AIEngineError, json.JSONDecodeError, KeyError):
        return CURATED_HINTS[level - 1], 'curated'


def _evaluate_teach_back_ai(*, response, exercise):
    try:
        text = generate_ai_response(
            system_prompt=ai_prompts.TEACH_BACK_SYSTEM_PROMPT,
            user_prompt=(
                f'Exercise: {exercise.activity.prompt}\n\n'
                + '\n'.join(f'{field}: {answer}' for field, answer in response.items())
            ),
            response_schema=ai_prompts.TEACH_BACK_SCHEMA,
        )
        data = json.loads(text)
        return data['evaluation'], data['feedback'], data['follow_up_question']
    except (AIEngineError, json.JSONDecodeError, KeyError):
        return _evaluate_teach_back_heuristic(response)


def _generate_review_recommendation(*, learning_session):
    misconception = learning_session.misconceptions.order_by('-created_at').first()
    teach_back = learning_session.teach_back_attempts.order_by('-created_at').first()
    hint_count = HintUsage.objects.filter(learner_attempt__learning_session=learning_session).count()
    try:
        text = generate_ai_response(
            system_prompt=ai_prompts.REVIEW_RECOMMENDATION_SYSTEM_PROMPT,
            user_prompt=(
                f'Suspected misconception: {misconception.evidence if misconception else "none recorded"}\n'
                f'Hints used: {hint_count}\n'
                f'Teach-Back feedback: {teach_back.feedback if teach_back else "none recorded"}'
            ),
            response_schema=ai_prompts.REVIEW_RECOMMENDATION_SCHEMA,
        )
        return json.loads(text)['recommendation']
    except (AIEngineError, json.JSONDecodeError, KeyError):
        return None


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
def ensure_diagnostic_quiz(*, learning_session):
    try:
        return learning_session.diagnostic_quiz_attempt
    except DiagnosticQuizAttempt.DoesNotExist:
        pass
    question, source = _generate_diagnostic_quiz_question(topic=learning_session.topic)
    return DiagnosticQuizAttempt.objects.create(
        learning_session=learning_session,
        question=question,
        source=source,
    )


@transaction.atomic
def submit_diagnostic_quiz(*, learning_session, answer):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.DIAGNOSTIC_QUIZ:
        raise ValidationError('The diagnostic quiz is not available at this step.')
    answer = answer.strip()
    if not answer:
        raise ValidationError('Answer the diagnostic quiz question before continuing.')
    quiz = DiagnosticQuizAttempt.objects.select_for_update().get(learning_session=locked_session)
    if quiz.answer:
        raise ValidationError('The diagnostic quiz has already been answered.')
    quiz.answer = answer
    quiz.answered_at = timezone.now()
    quiz.save(update_fields=('answer', 'answered_at'))
    return quiz


@transaction.atomic
def submit_first_attempt(*, learning_session, exercise, source_code, reasoning, confidence, gateway=None):
    validate_first_attempt(answer=source_code, reasoning=reasoning, confidence=confidence)
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.DIAGNOSTIC_QUIZ:
        raise ValidationError('Your first attempt has already been submitted. Continue with the current step.')
    quiz = DiagnosticQuizAttempt.objects.filter(learning_session=locked_session).first()
    if not quiz or not quiz.answer:
        raise ValidationError('Complete the diagnostic quiz before your first attempt.')
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
    transition_session(locked_session, WorkflowState.RESPONSE_EVALUATION)

    target = _next_state_after_evaluation(status=result.status, confidence=confidence)
    if target == WorkflowState.DIAGNOSIS:
        question, misconception = _generate_diagnosis_question(exercise=exercise, attempt=attempt)
        attempt.diagnosis_question = question
        attempt.suspected_misconception = misconception
    elif target == WorkflowState.VERIFICATION:
        attempt.verification_question = _generate_verification_question(exercise=exercise, attempt=attempt)
    attempt.save()
    transition_session(locked_session, target)
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
    latest_attempt = locked_session.attempts.order_by('-revision_number', '-created_at').first()
    misconception_code = slugify(latest_attempt.suspected_misconception) if latest_attempt else ''
    record = MisconceptionRecord.objects.create(
        learning_session=locked_session,
        concept=locked_session.topic.concepts.first(),
        code=misconception_code or 'loop-value-diagnosis',
        evidence=answer,
        confirmed=False,
    )
    transition_session(locked_session, WorkflowState.GUIDED_REVISION)
    learning_session.current_state = locked_session.current_state
    return record


@transaction.atomic
def submit_verification(*, learning_session, answer):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.VERIFICATION:
        raise ValidationError('The verification question is not available at this step.')
    answer = answer.strip()
    if not answer:
        raise ValidationError('Answer the verification question before continuing.')
    latest_attempt = locked_session.attempts.order_by('-revision_number', '-created_at').first()
    if latest_attempt is not None:
        latest_attempt.verification_answer = answer
        latest_attempt.save(update_fields=('verification_answer',))
    transition_session(locked_session, WorkflowState.TEACH_BACK)
    learning_session.current_state = locked_session.current_state
    return latest_attempt


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
    exercise = verified_revision.activity.coding_exercise
    evaluation, feedback, follow_up_question = _evaluate_teach_back_ai(response=response, exercise=exercise)
    teach_back = TeachBackAttempt.objects.create(
        learning_session=locked_session,
        response=json.dumps(response, ensure_ascii=False),
        evaluation=evaluation,
        feedback=feedback,
        follow_up_question=follow_up_question,
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
        raise PermissionDenied('The five-level hint ladder is complete.')
    exercise = latest_attempt.activity.coding_exercise
    content, _source = _generate_hint_content(level=next_level, exercise=exercise, attempt=latest_attempt)
    return HintUsage.objects.create(
        learner_attempt=latest_attempt,
        level=next_level,
        content=content,
    )


def build_outcome_summary(*, learning_session, transfer_attempt):
    if learning_session.current_state == WorkflowState.MASTERED:
        return 'Mastered: all required evidence was verified.', ''
    if transfer_attempt and transfer_attempt.evaluation.get('status') == 'NOT_EXECUTED':
        return (
            'Needs review: the Transfer Check could not be executed safely.',
            'Configure an isolated runner, then repeat the loop-values Transfer Check.',
        )
    recommendation = _generate_review_recommendation(learning_session=learning_session)
    if recommendation is None:
        recommendation = (
            'Review how a loop transforms each current item into a new result list, then try again.'
        )
    return 'Needs review: the independent Transfer Check was not verified as passed.', recommendation


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
    first_attempt = locked_session.attempts.filter(revision_number=0).first()
    if not first_attempt:
        return learning_session
    if locked_session.current_state == WorkflowState.FIRST_ATTEMPT:
        transition_session(locked_session, WorkflowState.RESPONSE_EVALUATION)
    if locked_session.current_state == WorkflowState.RESPONSE_EVALUATION:
        status = ExecutionStatus(first_attempt.evaluation.get('status', ExecutionStatus.NOT_EXECUTED.value))
        target = _next_state_after_evaluation(status=status, confidence=first_attempt.confidence)
        transition_session(locked_session, target)
    learning_session.current_state = locked_session.current_state
    return learning_session


@transaction.atomic
def reset_demo_session(*, browser_session_key, exercise):
    LearningSession.objects.filter(
        browser_session_key=browser_session_key,
        topic=exercise.activity.concept.topic,
    ).delete()
