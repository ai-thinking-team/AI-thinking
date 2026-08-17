import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from apps.ai_engine.client import ai_provider_configured, ai_provider_status
from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState, ai_assistance_allowed
from apps.code_runner.runner import code_runner_status
from apps.learning_core.models import Topic

from .forms import (
    CodingAttemptForm,
    CodingPlanForm,
    DiagnosisForm,
    RevisionForm,
    TeachBackForm,
    TransferAttemptForm,
)
from .models import CodingExercise
from .services import (
    acknowledge_diagnosis_solution,
    acknowledge_teach_back_solution,
    execution_status_feedback,
    get_demo_session,
    recover_interrupted_first_attempt,
    request_curated_hint,
    reset_demo_session,
    submit_diagnosis,
    submit_first_attempt,
    submit_plan,
    submit_revision,
    submit_teach_back,
    submit_transfer_check,
)


DISPLAY_STAGES = (
    ('plan', 'Understand & Plan'),
    ('first', 'First Attempt'),
    ('diagnosis', 'Diagnosis'),
    ('revision', 'Revision'),
    ('teach_back', 'Teach-Back'),
    ('transfer', 'Transfer Check'),
    ('completed', 'Completed'),
)

STATE_TO_STAGE = {
    WorkflowState.TOPIC_SELECTED: 'plan',
    WorkflowState.DIAGNOSTIC_QUIZ: 'plan',
    WorkflowState.FIRST_ATTEMPT: 'first',
    WorkflowState.RESPONSE_EVALUATION: 'diagnosis',
    WorkflowState.DIAGNOSIS: 'diagnosis',
    WorkflowState.GUIDED_REVISION: 'revision',
    WorkflowState.TEACH_BACK: 'teach_back',
    WorkflowState.TRANSFER_TASK: 'transfer',
    WorkflowState.MASTERED: 'completed',
    WorkflowState.NEEDS_REVIEW: 'completed',
}

CODING_SESSION_TRACKING_KEY = 'coding_demo_learning_session_id'


def home(request):
    topics = Topic.objects.filter(
        subject__slug='coding',
        concepts__activities__coding_exercise__active=True,
    ).annotate(
        exercise_count=Count(
            'concepts__activities__coding_exercise',
            filter=Q(concepts__activities__coding_exercise__active=True),
            distinct=True,
        ),
    ).order_by('name')
    return render(request, 'coding_quiz/home.html', {
        'topics': topics,
        'ai_status': ai_provider_status(),
    })


def topic_exercises(request, topic_slug):
    topic = get_object_or_404(
        Topic.objects.filter(subject__slug='coding'),
        slug=topic_slug,
    )
    exercises = CodingExercise.objects.filter(
        active=True,
        activity__concept__topic=topic,
    ).select_related('activity__concept__topic')
    return render(request, 'coding_quiz/topic_exercises.html', {
        'topic': topic,
        'exercises': exercises,
        'ai_status': ai_provider_status(),
    })


def _session_tracking_key(exercise):
    if exercise.slug == 'double-numbers':
        return CODING_SESSION_TRACKING_KEY
    return f'{CODING_SESSION_TRACKING_KEY}:{exercise.slug}'


def _browser_learning_session(request, exercise):
    if request.session.session_key is None:
        request.session.create()
    learning_session, _ = get_demo_session(
        browser_session_key=request.session.session_key,
        exercise=exercise,
    )
    request.session[_session_tracking_key(exercise)] = learning_session.pk
    if learning_session.current_state == WorkflowState.TOPIC_SELECTED:
        transition_session(learning_session, WorkflowState.DIAGNOSTIC_QUIZ)
    recover_interrupted_first_attempt(learning_session=learning_session)
    return learning_session


def _bound_form(request, form_class, action, *, prefix=None, initial=None):
    is_action = request.method == 'POST' and request.POST.get('action') == action
    return form_class(request.POST if is_action else None, prefix=prefix, initial=initial)


def _handle_action(request, learning_session, exercise, forms):
    action = request.POST.get('action', '')
    form = forms.get(action)
    if form is not None and not form.is_valid():
        return None

    if action == 'plan':
        submit_plan(
            learning_session=learning_session,
            exercise=exercise,
            **form.cleaned_data,
        )
        messages.success(request, 'Your plan and predicted output were saved. Submit your First Attempt.')
    elif action == 'first_attempt':
        _, result = submit_first_attempt(
            learning_session=learning_session,
            exercise=exercise,
            **form.cleaned_data,
        )
        feedback = execution_status_feedback(result.status)
        messages.info(request, f'{feedback["label"]}: {feedback["guidance"]}')
    elif action == 'diagnosis':
        submit_diagnosis(
            learning_session=learning_session,
            answer=form.cleaned_data['diagnosis_answer'],
        )
        if learning_session.current_state == WorkflowState.GUIDED_REVISION:
            messages.success(request, 'Your answer shows the core idea. You can now revise your work.')
        else:
            latest_interaction = learning_session.coach_interactions.order_by(
                '-created_at', '-pk'
            ).first()
            if latest_interaction and latest_interaction.response.get('should_reveal_solution'):
                messages.warning(request, 'The final guided answer is now available. Review it before continuing.')
            else:
                messages.warning(request, 'Not clear yet. A more concrete hint has been unlocked.')
    elif action == 'acknowledge_diagnosis_solution':
        acknowledge_diagnosis_solution(learning_session=learning_session)
        messages.info(request, 'The guided answer was recorded as assistance. Continue with your own revision.')
    elif action == 'hint':
        hint = request_curated_hint(learning_session=learning_session)
        if getattr(hint, 'solution_revealed', False):
            messages.warning(request, 'The final Revision solution was unlocked. Study it, then submit a passing revision.')
        else:
            messages.success(request, f'Hint level {hint.level} was unlocked.')
    elif action in {'save_revision', 'finish_revision'}:
        _, result = submit_revision(
            learning_session=learning_session,
            exercise=exercise,
            finish=action == 'finish_revision',
            **form.cleaned_data,
        )
        if action == 'finish_revision' and result.status.value != 'PASSED':
            feedback = execution_status_feedback(result.status)
            messages.warning(request, (
                f'Revision saved, but Teach-Back remains locked. Execution status: '
                f'{feedback["label"]} ({feedback["status"]}). {feedback["guidance"]}'
            ))
        else:
            verb = 'saved' if action == 'save_revision' else 'verified and completed'
            feedback = execution_status_feedback(result.status)
            messages.info(request, f'Revision {verb}. {feedback["label"]}: {feedback["guidance"]}')
    elif action == 'teach_back':
        teach_back = submit_teach_back(
            learning_session=learning_session,
            response=form.cleaned_data,
        )
        if teach_back.evaluation == 'CLEAR_UNDERSTANDING':
            messages.success(request, 'Teach-Back is clear. Complete the unassisted Transfer Check.')
        else:
            for field_evaluation in teach_back.rubric_evidence.get('field_evaluations', []):
                field_name = field_evaluation.get('field')
                if (
                    not field_evaluation.get('understood', False)
                    and field_name in form.fields
                ):
                    form.add_error(field_name, field_evaluation.get('feedback') or 'Please revise this answer.')
            messages.warning(request, f'Teach-Back needs revision: {teach_back.feedback}')
            # Render the same bound form so the learner can edit without re-entering answers.
            return None
    elif action == 'acknowledge_teach_back_solution':
        acknowledge_teach_back_solution(learning_session=learning_session)
        messages.warning(request, (
            'The assisted Teach-Back was recorded. Complete the unassisted Transfer Check; '
            'this session cannot be mastered without a clear Teach-Back.'
        ))
    elif action == 'transfer':
        _, result = submit_transfer_check(
            learning_session=learning_session,
            exercise=exercise,
            **form.cleaned_data,
        )
        if result.status.value in {'NOT_EXECUTED', 'RUNNER_ERROR'}:
            feedback = execution_status_feedback(result.status)
            messages.warning(request, (
                f'Transfer Check saved but not evaluated: {feedback["guidance"]} '
                'This step remains open so you can retry when the isolated runner is available.'
            ))
        else:
            feedback = execution_status_feedback(result.status)
            messages.info(request, f'Transfer Check saved. {feedback["label"]}: {feedback["guidance"]}')
    elif action == 'reset':
        reset_demo_session(
            browser_session_key=request.session.session_key,
            exercise=exercise,
        )
        request.session.pop(_session_tracking_key(exercise), None)
        messages.success(request, 'This learning session was ended and its evidence was preserved.')
    else:
        return HttpResponseBadRequest('This action is not available. Return to the current step and try again.')
    return redirect(request.path)


def exercise(request, slug='double-numbers'):
    selected_exercise = get_object_or_404(
        CodingExercise.objects.select_related(
            'activity__concept__topic', 'transfer_activity'
        ),
        slug=slug,
        active=True,
    )
    learning_session = _browser_learning_session(request, selected_exercise)
    first_attempt = learning_session.attempts.filter(revision_number=0).first()
    latest_attempt = learning_session.attempts.order_by('-revision_number', '-created_at').first()
    latest_transfer_attempt = learning_session.transfer_attempts.order_by('-created_at', '-pk').first()
    latest_teach_back_attempt = learning_session.teach_back_attempts.order_by('-created_at', '-pk').first()
    try:
        latest_teach_back_response = json.loads(latest_teach_back_attempt.response) if latest_teach_back_attempt else {}
    except (json.JSONDecodeError, TypeError):
        latest_teach_back_response = {}

    forms = {
        'plan': _bound_form(request, CodingPlanForm, 'plan'),
        'first_attempt': _bound_form(
            request,
            CodingAttemptForm,
            'first_attempt',
            initial={'source_code': selected_exercise.starter_code},
        ),
        'diagnosis': _bound_form(request, DiagnosisForm, 'diagnosis'),
        'save_revision': _bound_form(
            request,
            RevisionForm,
            'save_revision',
            prefix='revision',
            initial={
                'source_code': latest_attempt.answer if latest_attempt else selected_exercise.starter_code,
                'reasoning': latest_attempt.reasoning if latest_attempt else '',
                'confidence': latest_attempt.confidence if latest_attempt else None,
            },
        ),
        'finish_revision': _bound_form(
            request,
            RevisionForm,
            'finish_revision',
            prefix='revision',
            initial={
                'source_code': latest_attempt.answer if latest_attempt else selected_exercise.starter_code,
                'reasoning': latest_attempt.reasoning if latest_attempt else '',
                'confidence': latest_attempt.confidence if latest_attempt else None,
            },
        ),
        'teach_back': _bound_form(
            request,
            TeachBackForm,
            'teach_back',
            prefix='teach',
            initial=latest_teach_back_response,
        ),
        'transfer': _bound_form(
            request,
            TransferAttemptForm,
            'transfer',
            prefix='transfer',
            initial={
                'source_code': latest_transfer_attempt.response if latest_transfer_attempt else '',
                'reasoning': latest_transfer_attempt.reasoning if latest_transfer_attempt else '',
                'confidence': latest_transfer_attempt.confidence if latest_transfer_attempt else None,
            },
        ),
    }

    if request.method == 'POST':
        try:
            response = _handle_action(request, learning_session, selected_exercise, forms)
        except (ValidationError, PermissionDenied) as exc:
            error_text = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, error_text)
            response = None
        if response is not None:
            return response

    learning_session.refresh_from_db()
    planning_evidence = getattr(learning_session, 'coding_plan', None)
    attempts = list(learning_session.attempts.order_by('revision_number', 'created_at'))
    hints = list(
        learning_session.attempts.order_by('created_at')
        .prefetch_related('hint_usage')
    )
    hint_usage = [hint for attempt in hints for hint in attempt.hint_usage.all()]
    current_stage = STATE_TO_STAGE[WorkflowState(learning_session.current_state)]
    stage_names = [key for key, _ in DISPLAY_STAGES]
    stage_labels = dict(DISPLAY_STAGES)
    current_index = stage_names.index(current_stage)
    progress_steps = [
        {
            'key': key,
            'label': label,
            'current': key == current_stage,
            'complete': index < current_index,
            'locked': index > current_index,
        }
        for index, (key, label) in enumerate(DISPLAY_STAGES)
    ]
    latest_evaluation = latest_attempt.evaluation if latest_attempt else None
    latest_execution_feedback = (
        execution_status_feedback(latest_evaluation.get('status'))
        if latest_evaluation else None
    )
    diagnosis_records = list(learning_session.misconceptions.order_by('created_at'))
    coach_interactions = list(
        learning_session.coach_interactions.order_by('created_at', 'pk')
        .select_related('learner_attempt')
    )
    teach_back_attempts = list(learning_session.teach_back_attempts.order_by('created_at'))
    transfer_attempt = learning_session.transfer_attempts.order_by('-created_at', '-pk').first()
    diagnosis_interactions = list(
        learning_session.coach_interactions.filter(
            interaction_type__in=('DIAGNOSTIC', 'HINT'),
        ).order_by('created_at', 'pk')
    )
    diagnostic_interaction = diagnosis_interactions[-1] if diagnosis_interactions else None
    mastery_record = learning_session.mastery_records.order_by('-created_at').first()
    revision_solution_interaction = learning_session.coach_interactions.filter(
        interaction_type='HINT',
        request_context__phase='revision',
        response__should_reveal_solution=True,
    ).order_by('-created_at', '-pk').first()
    if mastery_record:
        final_result_message = f'{mastery_record.get_status_display()}: {mastery_record.reason}'
        review_recommendation = mastery_record.recommendation
    else:
        final_result_message = 'No mastery decision has been recorded yet.'
        review_recommendation = ''

    return render(request, 'coding_quiz/exercise.html', {
        'exercise': selected_exercise,
        'learning_session': learning_session,
        'current_stage': current_stage,
        'current_stage_label': stage_labels[current_stage],
        'progress_steps': progress_steps,
        'plan_form': forms['plan'],
        'planning_required': learning_session.current_state == WorkflowState.DIAGNOSTIC_QUIZ,
        'planning_evidence': planning_evidence,
        'first_form': forms['first_attempt'],
        'diagnosis_form': forms['diagnosis'],
        'revision_form': forms['finish_revision'] if request.POST.get('action') == 'finish_revision' else forms['save_revision'],
        'teach_back_form': forms['teach_back'],
        'transfer_form': forms['transfer'],
        'diagnostic_question': (
            diagnostic_interaction.response.get('message')
            if diagnostic_interaction
            else 'Which value changes during one iteration, and what should happen to it?'
        ),
        'diagnostic_source': diagnostic_interaction.source if diagnostic_interaction else '',
        'diagnostic_hint_level': (
            diagnostic_interaction.response.get('hint_level', 1)
            if diagnostic_interaction else 1
        ),
        'diagnosis_solution_revealed': bool(
            diagnostic_interaction
            and diagnostic_interaction.response.get('should_reveal_solution')
        ),
        'diagnosis_interactions': diagnosis_interactions,
        'first_attempt': first_attempt,
        'attempts': attempts,
        'hint_usage': hint_usage,
        'latest_evaluation': latest_evaluation,
        'latest_execution_feedback': latest_execution_feedback,
        'diagnosis_records': diagnosis_records,
        'coach_interactions': coach_interactions,
        'teach_back_attempts': teach_back_attempts,
        'transfer_attempt': transfer_attempt,
        'mastery_record': mastery_record,
        'final_result_message': final_result_message,
        'review_recommendation': review_recommendation,
        'revision_solution_interaction': revision_solution_interaction,
        'ai_enabled': ai_assistance_allowed(learning_session.current_state),
        'ai_configured': ai_provider_configured(),
        'ai_status': ai_provider_status(
            assistance_enabled=ai_assistance_allowed(learning_session.current_state),
        ),
        'code_runner_status': code_runner_status(),
    })
