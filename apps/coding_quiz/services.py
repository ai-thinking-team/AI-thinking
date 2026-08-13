from copy import deepcopy
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.ai_engine.orchestrator import (
    orchestrate_diagnostic,
    orchestrate_diagnosis_evaluation,
    orchestrate_hint,
    orchestrate_teach_back,
)
from apps.ai_engine.schemas import DiagnosticResponse
from apps.code_runner.runner import ExecutionStatus, get_code_execution_gateway
from apps.code_runner.test_service import build_python_request
from apps.learning_core.models import (
    CoachInteraction,
    CoachLearnerResponse,
    HintUsage,
    LearnerAttempt,
    LearningSession,
    MisconceptionRecord,
    TeachBackAttempt,
    TransferAttempt,
)
from apps.learning_core.services import (
    get_or_create_demo_session,
    record_mastery_decision,
    transition_session,
)
from apps.learning_core.state_machine import WorkflowState, hints_allowed
from apps.learning_core.validators import validate_first_attempt

from .ai_prompts import (
    DIAGNOSTIC_SYSTEM_PROMPT,
    DIAGNOSIS_EVALUATION_SYSTEM_PROMPT,
    REVISION_HINT_SYSTEM_PROMPT,
    TEACH_BACK_SYSTEM_PROMPT,
)
from .catalog_validation import validate_database_exercise
from .models import CodingExercise, CodingPlanEvidence
from .misconception_rules import (
    LOOP_VALUE_MISCONCEPTION,
    diagnosis_confirms_misconception,
    diagnosis_confirms_loop_value_misconception,
    transfer_repeats_misconception,
    transfer_repeats_loop_value_misconception,
)
from .teach_back_rubric import evaluate_teach_back

CURATED_HINTS = (
    'Which value changes on each pass through the loop?',
    'A loop processes one item at a time; which variable represents that current item?',
    'In `for colour in colours`, `colour` is one current item; which variable has that role in your number loop?',
    'Complete only this partial operation: `result.append(____)`; what expression doubles the current number?',
)
CURATED_REVISION_SOLUTION = (
    '```python\n'
    'def double_numbers(numbers):\n'
    '    result = []\n'
    '    for number in numbers:\n'
    '        result.append(number * 2)\n'
    '    return result\n'
    '```\n'
    'The loop variable is one current number, so that number is doubled before it is appended.'
)

DIAGNOSTIC_QUESTION = (
    'Inside the loop, which single value should be doubled, and when should it be added '
    'to the result list?'
)
CURATED_DIAGNOSTIC_FALLBACK = DiagnosticResponse(
    possible_misconception=LOOP_VALUE_MISCONCEPTION,
    diagnostic_confidence=0.5,
    response_type='guiding_question',
    message=DIAGNOSTIC_QUESTION,
    hint_level=1,
    should_reveal_solution=False,
)
DIAGNOSIS_HINT_TYPES = {
    2: 'concept_reminder',
    3: 'related_example',
    4: 'partial_method',
}
DIAGNOSIS_HINT_INSTRUCTIONS = {
    2: (
        'State that the loop variable is one current item, then ask which operation the '
        'exercise requires for that item. Do not ask for terminology.'
    ),
    3: (
        'Give one short example using different object names, then ask the learner to map '
        'that example back to the current number. Ask only one question.'
    ),
    4: (
        'Give an incomplete verbal sequence: take current number, ___ it, append result. '
        'Ask the learner to fill only the missing operation.'
    ),
}
CURATED_DIAGNOSIS_HINTS = {
    2: (
        'A for-loop variable represents one current item at a time. Which current value '
        'must be changed in this exercise?'
    ),
    3: (
        'In `for colour in colours`, `colour` is one item. In your number loop, what does '
        'the loop variable represent?'
    ),
    4: (
        'Complete this idea in words: take the current number, change it, then store it. '
        'What change must happen before storing it?'
    ),
}
CURATED_DIAGNOSIS_ANSWER = (
    'The loop variable holds one current number during each iteration. The correct idea is to '
    'double that current number and append the doubled value to the result list before moving '
    'to the next item.'
)
TEACH_BACK_HINT_INSTRUCTIONS = {
    1: 'Ask one focused question about the most important missing core idea.',
    2: 'State that one iteration has one current item, then ask one direct question about the failed field.',
    3: 'Use one short different-context loop example, then ask one question mapping it to this concept.',
    4: 'Give an incomplete conceptual sentence with one blank and ask what belongs in the blank.',
}
CURATED_TEACH_BACK_FOLLOWUPS = {
    1: 'During one iteration, what value does the loop variable hold and what should happen to it?',
    2: 'The loop variable holds one current number; what operation must happen before that number is stored?',
    3: 'If `colour` is one item in `for colour in colours`, what is `number` in your number loop?',
    4: 'Complete the idea: take one current number, ___ it, then append the result; what fills the blank?',
}
CURATED_TEACH_BACK_ANSWER = (
    'The original approach used the loop value incorrectly, so each iteration did not produce the '
    'required doubled result. During one iteration, the loop variable represents one current number. '
    'The correction doubles that current number and appends the transformed value to a new result '
    'list. A useful prevention check is to trace one small input item through a single iteration.'
)


def _require_valid_exercise_configuration(exercise):
    if validate_database_exercise(exercise):
        raise ValidationError(
            'This Coding exercise is unavailable because its curated configuration is invalid.'
        )


def _exercise_for_activity(activity):
    exercise = CodingExercise.objects.select_related(
        'activity__concept__topic', 'transfer_activity'
    ).filter(activity=activity).first()
    if exercise is None:
        raise ValidationError('This Coding exercise has no curated configuration.')
    _require_valid_exercise_configuration(exercise)
    return exercise


@transaction.atomic
def submit_plan(*, learning_session, exercise, solution_plan, predicted_output):
    _require_valid_exercise_configuration(exercise)
    solution_plan = str(solution_plan).strip()
    predicted_output = str(predicted_output).strip()
    if not solution_plan or not predicted_output:
        raise ValidationError(
            'Understand and Plan requires both a solution plan and predicted output.'
        )
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.DIAGNOSTIC_QUIZ:
        raise ValidationError('Understand and Plan has already been completed for this session.')
    if locked_session.activity_id != exercise.activity_id:
        raise ValidationError('The plan does not belong to this Coding exercise.')
    if CodingPlanEvidence.objects.filter(learning_session=locked_session).exists():
        raise ValidationError('Understand and Plan evidence has already been saved.')
    evidence = CodingPlanEvidence.objects.create(
        learning_session=locked_session,
        activity=exercise.activity,
        solution_plan=solution_plan,
        predicted_output=predicted_output,
    )
    transition_session(locked_session, WorkflowState.FIRST_ATTEMPT)
    learning_session.current_state = locked_session.current_state
    return evidence

def _execution_evidence(result):
    return {
        'status': result.status.value,
        'message': result.message,
        'tests': list(result.tests),
    }


def _first_attempt_response_evaluation(*, result, reasoning, confidence, activity):
    reasoning_clear = not diagnosis_confirms_misconception(
        reasoning,
        concept=activity.rubric.get('concept'),
        misconception_code=(activity.rubric.get('allowed_misconception_codes') or [LOOP_VALUE_MISCONCEPTION])[0],
        action_terms=activity.rubric.get('diagnosis_action_terms', ()),
    )
    if result.status != ExecutionStatus.PASSED:
        outcome = 'DIAGNOSIS_REQUIRED'
        reason = 'The original code was not runner-verified as passed.'
    elif not reasoning_clear:
        outcome = 'DIAGNOSIS_REQUIRED'
        reason = 'The code passed, but the reasoning does not yet explain the current item and operation.'
    elif confidence < 4:
        outcome = 'VERIFICATION_REQUIRED'
        reason = 'The code and reasoning passed, but low confidence requires verification.'
    else:
        outcome = 'READY_FOR_TEACH_BACK'
        reason = 'The code passed with clear reasoning and confidence high enough to continue.'
    return {
        'outcome': outcome,
        'reason': reason,
        'runner_passed': result.status == ExecutionStatus.PASSED,
        'reasoning_clear': reasoning_clear,
        'confidence': confidence,
    }


def _original_test_case_ids(exercise):
    return tuple(exercise.public_test_ids) + tuple(exercise.hidden_test_ids)


def _latest_misconceptions_by_code(learning_session):
    latest = {}
    for record in learning_session.misconceptions.order_by('created_at', 'pk'):
        latest[record.code] = record
    return latest


def _allowed_misconception_codes(activity):
    return tuple(activity.rubric.get(
        'allowed_misconception_codes',
        (LOOP_VALUE_MISCONCEPTION,),
    ))


def _diagnosis_config(activity):
    return activity.rubric.get('diagnosis', {})


def _diagnostic_request_context(*, learning_session, exercise, attempt):
    normalized_source = attempt.answer.casefold()
    test_items = attempt.evaluation.get('tests', [])
    return {
        'exercise': {
            'title': exercise.activity.title,
            'target_concept': exercise.activity.rubric.get('concept'),
            'target_operation': exercise.activity.rubric.get('operation', ''),
            'allowed_misconception_codes': list(
                _allowed_misconception_codes(exercise.activity)
            ),
        },
        'attempt_signals': {
            'confidence': attempt.confidence,
            'execution_status': attempt.evaluation.get('status'),
            'test_count': len(test_items),
            'failed_test_count': sum(not item.get('passed', False) for item in test_items),
            'source_line_count': len(attempt.answer.splitlines()),
            'uses_for_loop': 'for ' in normalized_source,
            'uses_append': '.append(' in normalized_source,
            'uses_list_comprehension': '[' in normalized_source and ' for ' in normalized_source,
            'reasoning_was_provided': bool(attempt.reasoning.strip()),
        },
        'history_signals': {
            'formal_attempt_count': learning_session.attempts.count(),
            'highest_hint_level': (
                HintUsage.objects.filter(learner_attempt__learning_session=learning_session)
                .order_by('-level').values_list('level', flat=True).first() or 0
            ),
        },
        'data_minimized': True,
    }


def _ensure_diagnostic_interaction(*, learning_session, exercise, attempt, ai_provider=None):
    _require_valid_exercise_configuration(exercise)
    existing = CoachInteraction.objects.filter(
        learning_session=learning_session,
        learner_attempt=attempt,
        interaction_type=CoachInteraction.InteractionType.DIAGNOSTIC,
    ).order_by('created_at', 'pk').first()
    if existing:
        return existing

    context = _diagnostic_request_context(
        learning_session=learning_session,
        exercise=exercise,
        attempt=attempt,
    )
    allowed_codes = _allowed_misconception_codes(exercise.activity)
    diagnosis_config = _diagnosis_config(exercise.activity)
    curated_fallback = DiagnosticResponse(
        possible_misconception=allowed_codes[0],
        diagnostic_confidence=0.5,
        response_type='guiding_question',
        message=diagnosis_config.get('question', DIAGNOSTIC_QUESTION),
        hint_level=1,
        should_reveal_solution=False,
    )
    orchestration = orchestrate_diagnostic(
        system_prompt=DIAGNOSTIC_SYSTEM_PROMPT,
        user_prompt=(
            'Return one diagnostic response for these data-minimized learner signals:\n'
            f'{json.dumps(context, ensure_ascii=False)}'
        ),
        curated_fallback=curated_fallback,
        allowed_misconception_codes=allowed_codes,
        provider=ai_provider,
    )
    interaction = CoachInteraction.objects.create(
        learning_session=learning_session,
        learner_attempt=attempt,
        interaction_type=CoachInteraction.InteractionType.DIAGNOSTIC,
        source=orchestration.source,
        request_context=context,
        response=orchestration.response.to_dict(),
        failure_code=orchestration.failure_code,
    )
    MisconceptionRecord.objects.create(
        learning_session=learning_session,
        concept=exercise.activity.concept,
        code=orchestration.response.possible_misconception,
        status=MisconceptionRecord.Status.HYPOTHESIS,
        evidence=(
            f'{orchestration.source} diagnostic hypothesis with confidence '
            f'{orchestration.response.diagnostic_confidence:.2f}.'
        ),
    )
    return interaction


@transaction.atomic
def ensure_transfer_activity(exercise):
    if exercise.transfer_activity is None:
        raise ValidationError('This exercise has no curated Transfer Check activity.')
    return exercise.transfer_activity


@transaction.atomic
def ensure_demo_exercise():
    return CodingExercise.objects.select_related(
        'activity__concept__topic', 'transfer_activity'
    ).get(slug='double-numbers', active=True)


@transaction.atomic
def submit_first_attempt(*, learning_session, exercise, source_code, reasoning, confidence,
                         gateway=None, ai_provider=None):
    _require_valid_exercise_configuration(exercise)
    validate_first_attempt(answer=source_code, reasoning=reasoning, confidence=confidence)
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state == WorkflowState.DIAGNOSTIC_QUIZ:
        raise ValidationError('Complete Understand and Plan before submitting your first attempt.')
    if locked_session.current_state != WorkflowState.FIRST_ATTEMPT:
        raise ValidationError('Your first attempt has already been submitted. Continue with the current step.')
    if not CodingPlanEvidence.objects.filter(
        learning_session=locked_session,
        activity=exercise.activity,
    ).exists():
        raise ValidationError('Complete Understand and Plan before submitting your first attempt.')
    if locked_session.attempts.filter(revision_number=0).exists():
        raise ValidationError('Your first attempt has already been saved.')

    attempt = LearnerAttempt.objects.create(
        learning_session=locked_session,
        activity=exercise.activity,
        answer=source_code,
        reasoning=reasoning,
        confidence=confidence,
    )
    runner = gateway or get_code_execution_gateway()
    result = runner.run(build_python_request(
        source_code=source_code,
        test_case_ids=_original_test_case_ids(exercise),
    ))
    attempt.evaluation = _execution_evidence(result)
    response_evaluation = _first_attempt_response_evaluation(
        result=result,
        reasoning=reasoning,
        confidence=confidence,
        activity=exercise.activity,
    )
    attempt.evaluation['response_evaluation'] = response_evaluation
    attempt.save(update_fields=('evaluation',))
    transition_session(locked_session, WorkflowState.RESPONSE_EVALUATION)
    if response_evaluation['outcome'] == 'READY_FOR_TEACH_BACK':
        transition_session(locked_session, WorkflowState.TEACH_BACK)
    else:
        transition_session(locked_session, WorkflowState.DIAGNOSIS)
        _ensure_diagnostic_interaction(
            learning_session=locked_session,
            exercise=exercise,
            attempt=attempt,
            ai_provider=ai_provider,
        )
    learning_session.current_state = locked_session.current_state
    return attempt, result


def _diagnosis_fallback(*, answer, next_level, response_type, reveal_solution,
                        misconception_code=LOOP_VALUE_MISCONCEPTION,
                        action_terms=None, diagnosis_config=None, concept=None):
    diagnosis_config = diagnosis_config or {}
    hints = diagnosis_config.get('hints', {})
    understood = not diagnosis_confirms_misconception(
        answer,
        misconception_code=misconception_code,
        concept=concept,
        action_terms=action_terms,
    )
    return {
        'understood': understood,
        'feedback': (
            'Your answer connects the current loop item with the required transformation.'
            if understood
            else 'Your answer does not yet explain both the current loop item and what happens to it.'
        ),
        'possible_misconception': misconception_code,
        'diagnostic_confidence': 0.6,
        'response_type': response_type,
        'message': (
            diagnosis_config.get('answer', CURATED_DIAGNOSIS_ANSWER)
            if reveal_solution
            else hints.get(str(next_level), CURATED_DIAGNOSIS_HINTS[next_level])
        ),
        'hint_level': next_level,
        'should_reveal_solution': reveal_solution,
    }


def _latest_diagnosis_interaction(learning_session):
    return learning_session.coach_interactions.filter(
        interaction_type__in=(
            CoachInteraction.InteractionType.DIAGNOSTIC,
            CoachInteraction.InteractionType.HINT,
        ),
    ).order_by('-created_at', '-pk').first()


@transaction.atomic
def submit_diagnosis(*, learning_session, answer, ai_provider=None):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.DIAGNOSIS:
        raise ValidationError('The diagnosis question is not available at this step.')
    answer = answer.strip()
    if not answer:
        raise ValidationError('Answer the diagnosis question before continuing.')
    interaction = _latest_diagnosis_interaction(locked_session)
    if interaction is None:
        raise ValidationError('The diagnostic question was not recorded safely.')
    if interaction.response.get('should_reveal_solution'):
        raise ValidationError('Review the correct answer before continuing to Revision.')
    if hasattr(interaction, 'learner_response'):
        raise ValidationError('The diagnostic question has already been answered.')
    CoachLearnerResponse.objects.create(interaction=interaction, response=answer)
    misconception_code = interaction.response.get('possible_misconception')
    previous = _latest_misconceptions_by_code(locked_session).get(misconception_code)
    if previous is None:
        raise ValidationError('The diagnosis has no active misconception hypothesis to evaluate.')

    current_level = interaction.response.get('hint_level', 1)
    activity = interaction.learner_attempt.activity
    _exercise_for_activity(activity)
    allowed_codes = _allowed_misconception_codes(activity)
    diagnosis_config = _diagnosis_config(activity)
    action_terms = activity.rubric.get('diagnosis_action_terms', ())
    reveal_solution = current_level >= 4
    next_level = 4 if reveal_solution else current_level + 1
    response_type = 'solution_reveal' if reveal_solution else DIAGNOSIS_HINT_TYPES[next_level]
    prompt_context = {
        'target_concept': activity.concept.description,
        'target_operation': activity.rubric.get('operation', ''),
        'current_question': interaction.response.get('message', ''),
        'learner_answer': answer,
        'current_hint_level': current_level,
        'server_selected_next_level': next_level,
        'server_selected_response_type': response_type,
        'server_selected_hint_instruction': (
            'Give the correct conceptual explanation without source code.'
            if reveal_solution
            else DIAGNOSIS_HINT_INSTRUCTIONS[next_level]
        ),
        'server_allows_solution_reveal': reveal_solution,
        'allowed_misconception_codes': list(allowed_codes),
        'data_minimized': True,
    }
    orchestration = orchestrate_diagnosis_evaluation(
        system_prompt=DIAGNOSIS_EVALUATION_SYSTEM_PROMPT,
        user_prompt=(
            'Evaluate this privacy-minimized diagnostic answer and prepare the server-selected '
            f'next response:\n{json.dumps(prompt_context, ensure_ascii=False)}'
        ),
        curated_fallback=_diagnosis_fallback(
            answer=answer,
            next_level=next_level,
            response_type=response_type,
            reveal_solution=reveal_solution,
            misconception_code=misconception_code,
            action_terms=action_terms,
            diagnosis_config=diagnosis_config,
            concept=activity.rubric.get('concept'),
        ),
        allowed_misconception_codes=allowed_codes,
        response_type=response_type,
        hint_level=next_level,
        should_reveal_solution=reveal_solution,
        provider=ai_provider,
    )
    understood = orchestration.response.understood
    if understood:
        status = (
            MisconceptionRecord.Status.RESOLVED
            if previous.status == MisconceptionRecord.Status.CONFIRMED
            else MisconceptionRecord.Status.DISMISSED
        )
    else:
        status = MisconceptionRecord.Status.CONFIRMED
    record = MisconceptionRecord.objects.create(
        learning_session=locked_session,
        concept=previous.concept,
        code=previous.code,
        evidence=(
            f'{orchestration.source} diagnosis evaluation: '
            f'{orchestration.response.feedback}'
        ),
        status=status,
        supersedes=previous,
    )
    if understood:
        transition_session(locked_session, WorkflowState.GUIDED_REVISION)
    else:
        CoachInteraction.objects.create(
            learning_session=locked_session,
            learner_attempt=interaction.learner_attempt,
            interaction_type=CoachInteraction.InteractionType.HINT,
            source=orchestration.source,
            request_context={
                'evaluated_interaction_id': interaction.pk,
                'answer_character_count': len(answer),
                'current_hint_level': current_level,
                'data_minimized': True,
            },
            response=orchestration.response.to_dict(),
            failure_code=orchestration.failure_code,
        )
    learning_session.current_state = locked_session.current_state
    return record


@transaction.atomic
def acknowledge_diagnosis_solution(*, learning_session):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.DIAGNOSIS:
        raise ValidationError('The diagnosis answer can be acknowledged only during Diagnosis.')
    interaction = _latest_diagnosis_interaction(locked_session)
    if interaction is None or not interaction.response.get('should_reveal_solution'):
        raise ValidationError('The final diagnosis answer has not been unlocked.')
    transition_session(locked_session, WorkflowState.GUIDED_REVISION)
    learning_session.current_state = locked_session.current_state
    return interaction


@transaction.atomic
def submit_revision(*, learning_session, exercise, source_code, reasoning, confidence, gateway=None,
                    finish=True):
    _require_valid_exercise_configuration(exercise)
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


def _curated_teach_back_payload(response, rubric, *, hint_level=1, followups=None):
    outcome = evaluate_teach_back(response, rubric)
    field_evaluations = outcome.rubric_evidence.get('field_evaluations', [])
    followups = followups or {}
    fallback_followup = outcome.follow_up_question
    if not fallback_followup:
        unmet = next(
            (criterion for criterion in rubric['criteria']
             if not next(
                 (item['understood'] for item in field_evaluations
                  if item['field'] == criterion['field']),
                 False,
             )),
            None,
        )
        fallback_followup = unmet['follow_up_question'] if unmet else CURATED_TEACH_BACK_FOLLOWUPS[1]
    return {
        'field_evaluations': field_evaluations,
        'misconception_code': outcome.misconception_code or 'none',
        'follow_up_question': (
            '' if outcome.result == 'CLEAR_UNDERSTANDING' and all(
                item.get('understood') for item in field_evaluations
            )
            else (
                fallback_followup
                if hint_level == 1
                else followups.get(
                    str(hint_level),
                    CURATED_TEACH_BACK_FOLLOWUPS[hint_level],
                )
            )
        ),
    }


def _teach_back_rubric_for_attempt(activity_rubric, attempt):
    rubric = deepcopy(activity_rubric.get('teach_back'))
    passed_without_revision = (
        attempt.revision_number == 0
        and attempt.evaluation.get('status') == ExecutionStatus.PASSED.value
    )
    # The original-attempt variant is specific to the loop-values exercise.
    # Keep specialized Dictionary/Function/List rubrics intact.
    if not passed_without_revision or activity_rubric.get('concept') != 'loop_values':
        return rubric, 'REVISED_SOLUTION'

    correction = next(
        criterion for criterion in rubric['criteria']
        if criterion['id'] == 'explain_correction'
    )
    outcome = next(
        criterion for criterion in rubric['criteria']
        if criterion['id'] == 'explain_failure_reason'
    )
    outcome['meaning'] = (
        'Explains why the original solution works by connecting one current item '
        'to the required operation and collected result.'
    )
    outcome['required_groups'] = deepcopy(correction['required_groups'])
    outcome['feedback'] = (
        'The explanation does not yet connect one current item and the required operation '
        'to the correct result.'
    )
    outcome['follow_up_question'] = (
        'During one iteration, what happens to the current item before it is collected?'
    )
    return rubric, 'PASSED_FIRST_ATTEMPT'


def _teach_back_prompt_context(response, rubric, *, hint_level=1, operation=''):
    return {
        'rubric': {
            'criteria': [{
                'id': criterion['id'],
                'field': criterion['field'],
                'meaning': criterion.get('meaning', criterion['feedback']),
                'required_for_clear': criterion.get('required_for_clear', True),
            } for criterion in rubric['criteria']],
            'misconceptions': [{
                'code': misconception['code'],
                'meaning': misconception['feedback'],
            } for misconception in rubric.get('misconceptions', [])],
        },
        'answers': {criterion['field']: response.get(criterion['field'], '') for criterion in rubric['criteria']},
        'target_operation': operation,
        'server_selected_hint_level': hint_level,
        'server_selected_hint_instruction': TEACH_BACK_HINT_INSTRUCTIONS[hint_level],
        'data_minimized': True,
    }


@transaction.atomic
def submit_teach_back(*, learning_session, response, ai_provider=None):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.TEACH_BACK:
        raise ValidationError('Teach-Back is not available at this step.')
    verified_revision = locked_session.attempts.order_by('-revision_number', '-created_at').first()
    if not verified_revision or verified_revision.evaluation.get('status') != ExecutionStatus.PASSED.value:
        raise ValidationError('Teach-Back requires a revision verified as PASSED by the isolated runner.')
    activity_rubric = verified_revision.activity.rubric
    _exercise_for_activity(verified_revision.activity)
    rubric, response_path = _teach_back_rubric_for_attempt(
        activity_rubric,
        verified_revision,
    )
    latest_teach_back = locked_session.teach_back_attempts.order_by('-created_at', '-pk').first()
    if latest_teach_back and latest_teach_back.evaluation == 'ASSISTED_COMPLETION':
        raise ValidationError('Review and acknowledge the final Teach-Back answer before continuing.')
    previous_hint_level = (
        latest_teach_back.rubric_evidence.get('hint_level', 0)
        if latest_teach_back and latest_teach_back.evaluation != 'CLEAR_UNDERSTANDING'
        else 0
    )
    hint_level = min(previous_hint_level + 1, 4)
    reveal_if_still_incomplete = previous_hint_level >= 4
    # The local evaluator both validates the rubric and provides a deterministic fallback.
    curated_fallback = _curated_teach_back_payload(
        response,
        rubric,
        hint_level=hint_level,
        followups=activity_rubric.get('teach_back_followups'),
    )
    expected_fields = tuple(criterion['field'] for criterion in rubric['criteria'])
    allowed_misconceptions = tuple(item['code'] for item in rubric.get('misconceptions', []))
    prompt_context = _teach_back_prompt_context(
        response,
        rubric,
        hint_level=hint_level,
        operation=activity_rubric.get('operation', ''),
    )
    orchestration = orchestrate_teach_back(
        system_prompt=TEACH_BACK_SYSTEM_PROMPT,
        user_prompt=(
            'Evaluate these privacy-minimized Teach-Back answers semantically:\n'
            f'{json.dumps(prompt_context, ensure_ascii=False)}'
        ),
        curated_fallback=curated_fallback,
        expected_fields=expected_fields,
        allowed_misconception_codes=allowed_misconceptions,
        provider=ai_provider,
    )
    evaluations = {item.field: item for item in orchestration.response.field_evaluations}
    required_fields = tuple(
        criterion['field']
        for criterion in rubric['criteria']
        if criterion.get('required_for_clear', True)
    )
    failed_required_fields = [
        field for field in required_fields if not evaluations[field].understood
    ]
    passed_required_fields = [
        field for field in required_fields if evaluations[field].understood
    ]
    # A Teach-Back is evidence of understanding, not a terminology exam. For the
    # coding MVP, most core ideas are sufficient; optional prevention/original-issue
    # fields remain useful evidence but do not block progress.
    minimum_core_fields = max(1, (len(required_fields) * 2 + 2) // 3)
    misconception_code = orchestration.response.misconception_code
    if misconception_code != 'none':
        result = 'MISCONCEPTION_REMAINS'
    elif len(passed_required_fields) < minimum_core_fields:
        result = 'PARTIAL_UNDERSTANDING'
    else:
        result = 'CLEAR_UNDERSTANDING'

    assisted_completion = result != 'CLEAR_UNDERSTANDING' and reveal_if_still_incomplete
    if assisted_completion:
        result = 'ASSISTED_COMPLETION'

    if result == 'CLEAR_UNDERSTANDING':
        feedback = (
            f'The Teach-Back shows understanding of the core {activity_rubric.get("concept", "concept")} concept.'
        )
        follow_up_question = ''
    elif assisted_completion:
        feedback = activity_rubric.get('teach_back_answer', CURATED_TEACH_BACK_ANSWER)
        follow_up_question = ''
    else:
        first_failed = failed_required_fields[0] if failed_required_fields else next(
            (item.field for item in orchestration.response.field_evaluations if not item.understood),
            required_fields[0],
        )
        feedback = evaluations[first_failed].feedback
        follow_up_question = orchestration.response.follow_up_question
        if not follow_up_question:
            criterion = next(item for item in rubric['criteria'] if item['field'] == first_failed)
            follow_up_question = criterion['follow_up_question']

    rubric_evidence = {
        'rubric_valid': True,
        'response_path': response_path,
        'evaluation_source': orchestration.source,
        'failure_code': orchestration.failure_code,
        'data_minimized': True,
        'required_fields': list(required_fields),
        'failed_required_fields': failed_required_fields,
        'passed_required_fields': passed_required_fields,
        'minimum_core_fields': minimum_core_fields,
        'grading_mode': 'core_ideas_majority',
        'hint_level': hint_level,
        'solution_revealed': assisted_completion,
        'field_evaluations': [item.to_dict() for item in orchestration.response.field_evaluations],
    }
    first_unmet_field = next(
        (item.field for item in orchestration.response.field_evaluations if not item.understood),
        None,
    )
    if first_unmet_field:
        failed_criterion = next(
            item for item in rubric['criteria'] if item['field'] == first_unmet_field
        )
        rubric_evidence['unmet_criterion'] = failed_criterion['id']
    rubric_evidence['passed_criteria'] = [
        criterion['id'] for criterion in rubric['criteria']
        if evaluations[criterion['field']].understood
    ]
    if misconception_code != 'none':
        rubric_evidence['misconception_code'] = misconception_code

    teach_back = TeachBackAttempt.objects.create(
        learning_session=locked_session,
        response=json.dumps(response, ensure_ascii=False),
        evaluation=result,
        feedback=feedback,
        follow_up_question=follow_up_question,
        rubric_evidence=rubric_evidence,
    )
    if misconception_code != 'none':
        previous = _latest_misconceptions_by_code(locked_session).get(misconception_code)
        MisconceptionRecord.objects.create(
            learning_session=locked_session,
            concept=verified_revision.activity.concept,
            code=misconception_code,
            evidence=(
                f'Teach-Back evidence: {feedback} '
                f'Focused follow-up: {follow_up_question}'
            ),
            status=MisconceptionRecord.Status.CONFIRMED,
            supersedes=previous,
        )
    if result == 'CLEAR_UNDERSTANDING':
        transition_session(locked_session, WorkflowState.TRANSFER_TASK)
        learning_session.current_state = locked_session.current_state
    return teach_back


@transaction.atomic
def acknowledge_teach_back_solution(*, learning_session):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.TEACH_BACK:
        raise ValidationError('The Teach-Back answer can be acknowledged only during Teach-Back.')
    latest = locked_session.teach_back_attempts.order_by('-created_at', '-pk').first()
    if latest is None or latest.evaluation != 'ASSISTED_COMPLETION':
        raise ValidationError('The final Teach-Back answer has not been unlocked.')
    transition_session(locked_session, WorkflowState.TRANSFER_TASK)
    learning_session.current_state = locked_session.current_state
    return latest


@transaction.atomic
def submit_transfer_check(*, learning_session, exercise, source_code, reasoning, confidence,
                          gateway=None):
    _require_valid_exercise_configuration(exercise)
    validate_first_attempt(answer=source_code, reasoning=reasoning, confidence=confidence)
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if locked_session.current_state != WorkflowState.TRANSFER_TASK:
        raise ValidationError('The Transfer Check is not available at this step.')
    latest_transfer = locked_session.transfer_attempts.order_by('-created_at', '-pk').first()
    if (
        latest_transfer
        and latest_transfer.evaluation.get('status') != ExecutionStatus.NOT_EXECUTED.value
    ):
        raise ValidationError('Your Transfer Check has already been evaluated.')
    original_attempt = locked_session.attempts.order_by('-revision_number', '-created_at').first()
    original_passed = bool(
        original_attempt and original_attempt.evaluation.get('status') == ExecutionStatus.PASSED.value
    )
    if not original_passed:
        raise ValidationError('Transfer Check requires a revision verified as PASSED by the isolated runner.')
    teach_back = locked_session.teach_back_attempts.order_by('-created_at').first()
    teach_back_clear = bool(teach_back and teach_back.evaluation == 'CLEAR_UNDERSTANDING')
    teach_back_assisted = bool(teach_back and teach_back.evaluation == 'ASSISTED_COMPLETION')
    if not (teach_back_clear or teach_back_assisted):
        raise ValidationError('Transfer Check requires a clear or acknowledged assisted Teach-Back.')

    transfer_activity = ensure_transfer_activity(exercise)
    test_case_ids = exercise.transfer_test_ids
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
    if result.status == ExecutionStatus.NOT_EXECUTED:
        learning_session.current_state = locked_session.current_state
        return transfer, result

    repeated_records = []
    latest_misconceptions = _latest_misconceptions_by_code(locked_session)
    for code, misconception in latest_misconceptions.items():
        if misconception.status != MisconceptionRecord.Status.CONFIRMED:
            continue
        repeated = transfer_repeats_misconception(
            source_code=source_code,
            reasoning=reasoning,
            misconception_code=code,
            action_terms=transfer_activity.rubric.get('action_terms'),
        )
        if not repeated and not transfer.passed:
            continue
        outcome = MisconceptionRecord.objects.create(
            learning_session=locked_session,
            concept=misconception.concept,
            code=code,
            evidence=(
                'Transfer Check repeated the confirmed misconception.'
                if repeated
                else 'Transfer Check demonstrated the concept without repeating the confirmed misconception.'
            ),
            status=(
                MisconceptionRecord.Status.REPEATED
                if repeated
                else MisconceptionRecord.Status.RESOLVED
            ),
            supersedes=misconception,
        )
        if repeated:
            repeated_records.append(outcome)

    mastery = record_mastery_decision(
        learning_session=locked_session,
        concept=exercise.activity.concept,
        original_passed=original_passed,
        teach_back_clear=teach_back_clear,
        transfer_passed=transfer.passed,
        transfer_unassisted=not transfer.used_assistance,
        repeated_misconception_codes=[record.code for record in repeated_records],
        evidence={
            'original_attempt_id': original_attempt.pk,
            'teach_back_attempt_id': teach_back.pk,
            'transfer_attempt_id': transfer.pk,
            'misconception_record_ids': list(
                locked_session.misconceptions.order_by('created_at', 'pk').values_list('pk', flat=True)
            ),
        },
    )
    target = WorkflowState(mastery.status)
    transition_session(locked_session, target)
    learning_session.current_state = locked_session.current_state
    return transfer, result


@transaction.atomic
def request_curated_hint(*, learning_session, ai_provider=None):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    if not hints_allowed(locked_session.current_state):
        raise PermissionDenied('Hints are available only during guided revision.')
    latest_attempt = locked_session.attempts.order_by(
        '-revision_number', '-created_at', '-pk'
    ).first()
    if latest_attempt is None:
        raise PermissionDenied('Submit an attempt before requesting a hint.')

    existing_reveal = locked_session.coach_interactions.filter(
        interaction_type=CoachInteraction.InteractionType.HINT,
        request_context__phase='revision',
        response__should_reveal_solution=True,
    ).order_by('-created_at', '-pk').first()
    if existing_reveal:
        raise PermissionDenied('The final Revision solution has already been unlocked.')
    latest_hint = HintUsage.objects.filter(
        learner_attempt__learning_session=locked_session
    ).order_by('-created_at', '-pk').first()
    if latest_hint and latest_hint.learner_attempt_id == latest_attempt.pk:
        raise PermissionDenied('Revise your work before unlocking the next hint.')
    reveal_solution = bool(latest_hint and latest_hint.level == 4)
    next_level = 4 if reveal_solution else (1 if latest_hint is None else latest_hint.level + 1)
    response_type = (
        'solution_reveal'
        if reveal_solution
        else ('guiding_question', 'concept_reminder', 'related_example', 'partial_method')[next_level - 1]
    )
    activity_rubric = latest_attempt.activity.rubric
    _exercise_for_activity(latest_attempt.activity)
    revision_hints = activity_rubric.get('revision_hints', CURATED_HINTS)
    if not isinstance(revision_hints, list) or len(revision_hints) != 4:
        revision_hints = CURATED_HINTS
    allowed_codes = _allowed_misconception_codes(latest_attempt.activity)
    test_items = latest_attempt.evaluation.get('tests', [])
    context = {
        'exercise': {
            'title': latest_attempt.activity.title,
            'target_concept': latest_attempt.activity.rubric.get('concept'),
            'target_operation': latest_attempt.activity.rubric.get('operation', ''),
        },
        'attempt_signals': {
            'execution_status': latest_attempt.evaluation.get('status'),
            'failed_test_count': sum(not item.get('passed', False) for item in test_items),
            'confidence': latest_attempt.confidence,
            'revision_number': latest_attempt.revision_number,
        },
        'server_selected_hint_level': next_level,
        'server_selected_response_type': response_type,
        'server_allows_solution_reveal': reveal_solution,
        'data_minimized': True,
    }
    curated_fallback = {
        'possible_misconception': allowed_codes[0],
        'response_type': response_type,
        'message': (
            activity_rubric.get('revision_solution', CURATED_REVISION_SOLUTION)
            if reveal_solution
            else revision_hints[next_level - 1]
        ),
        'hint_level': next_level,
        'should_reveal_solution': reveal_solution,
    }
    orchestration = orchestrate_hint(
        system_prompt=REVISION_HINT_SYSTEM_PROMPT,
        user_prompt=(
            'Generate the server-selected Revision support from these privacy-minimized signals:\n'
            f'{json.dumps(context, ensure_ascii=False)}'
        ),
        curated_fallback=curated_fallback,
        allowed_misconception_codes=allowed_codes,
        response_type=response_type,
        hint_level=next_level,
        should_reveal_solution=reveal_solution,
        provider=ai_provider,
    )
    CoachInteraction.objects.create(
        learning_session=locked_session,
        learner_attempt=latest_attempt,
        interaction_type=CoachInteraction.InteractionType.HINT,
        source=orchestration.source,
        request_context={**context, 'phase': 'revision'},
        response=orchestration.response.to_dict(),
        failure_code=orchestration.failure_code,
    )
    hint = HintUsage.objects.create(
        learner_attempt=latest_attempt,
        level=next_level,
        content=orchestration.response.message,
    )
    hint.solution_revealed = reveal_solution
    return hint


def begin_teach_back(*, learning_session, original_passed):
    if not original_passed:
        raise PermissionDenied('Teach-Back requires the original exercise to pass isolated tests.')
    return transition_session(learning_session, WorkflowState.TEACH_BACK)


def begin_transfer_check(*, learning_session, teach_back_evaluation):
    if teach_back_evaluation not in {'CLEAR_UNDERSTANDING', 'ASSISTED_COMPLETION'}:
        raise PermissionDenied('Transfer Check requires an acceptable Teach-Back.')
    return transition_session(learning_session, WorkflowState.TRANSFER_TASK)


def get_demo_session(*, browser_session_key, exercise):
    return get_or_create_demo_session(
        browser_session_key=browser_session_key,
        topic=exercise.activity.concept.topic,
        activity=exercise.activity,
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
        attempt = locked_session.attempts.filter(revision_number=0).first()
        response_outcome = (
            attempt.evaluation.get('response_evaluation', {}).get('outcome')
            if attempt else None
        )
        target = (
            WorkflowState.TEACH_BACK
            if response_outcome == 'READY_FOR_TEACH_BACK'
            else WorkflowState.DIAGNOSIS
        )
        transition_session(locked_session, target)
    if locked_session.current_state == WorkflowState.DIAGNOSIS:
        attempt = locked_session.attempts.filter(revision_number=0).first()
        exercise = CodingExercise.objects.filter(activity=attempt.activity).first() if attempt else None
        if attempt and exercise:
            _ensure_diagnostic_interaction(
                learning_session=locked_session,
                exercise=exercise,
                attempt=attempt,
            )
    learning_session.current_state = locked_session.current_state
    return learning_session


@transaction.atomic
def reset_demo_session(*, browser_session_key, exercise):
    LearningSession.objects.filter(
        browser_session_key=browser_session_key,
        activity=exercise.activity,
        ended_at__isnull=True,
    ).update(ended_at=timezone.now(), active_slot=None)
