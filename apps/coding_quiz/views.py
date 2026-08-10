from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render

from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState, ai_assistance_allowed

from .forms import (
    CodingAttemptForm,
    DiagnosisForm,
    RevisionForm,
    TeachBackForm,
    TransferAttemptForm,
)
from .services import (
    DIAGNOSTIC_QUESTION,
    ensure_demo_exercise,
    get_demo_session,
    recover_interrupted_first_attempt,
    request_curated_hint,
    reset_demo_session,
    submit_diagnosis,
    submit_first_attempt,
    submit_revision,
    submit_teach_back,
    submit_transfer_check,
)


DISPLAY_STAGES = (
    ('first', 'First Attempt'),
    ('diagnosis', 'Diagnosis'),
    ('revision', 'Revision'),
    ('teach_back', 'Teach-Back'),
    ('transfer', 'Transfer Check'),
    ('completed', 'Completed'),
)

STATE_TO_STAGE = {
    WorkflowState.TOPIC_SELECTED: 'first',
    WorkflowState.DIAGNOSTIC_QUIZ: 'first',
    WorkflowState.FIRST_ATTEMPT: 'diagnosis',
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
    return render(request, 'coding_quiz/home.html')


def _browser_learning_session(request, demo_exercise):
    if request.session.session_key is None:
        request.session.create()
    learning_session, created = get_demo_session(
        browser_session_key=request.session.session_key,
        exercise=demo_exercise,
    )
    tracked_session_id = request.session.get(CODING_SESSION_TRACKING_KEY)
    if not created and tracked_session_id != learning_session.pk:
        reset_demo_session(
            browser_session_key=request.session.session_key,
            exercise=demo_exercise,
        )
        learning_session, _ = get_demo_session(
            browser_session_key=request.session.session_key,
            exercise=demo_exercise,
        )
    request.session[CODING_SESSION_TRACKING_KEY] = learning_session.pk
    if learning_session.current_state == WorkflowState.TOPIC_SELECTED:
        transition_session(learning_session, WorkflowState.DIAGNOSTIC_QUIZ)
    recover_interrupted_first_attempt(learning_session=learning_session)
    return learning_session


def _bound_form(request, form_class, action, *, prefix=None, initial=None):
    is_action = request.method == 'POST' and request.POST.get('action') == action
    return form_class(request.POST if is_action else None, prefix=prefix, initial=initial)


def _handle_action(request, learning_session, demo_exercise, forms):
    action = request.POST.get('action', '')
    form = forms.get(action)
    if form is not None and not form.is_valid():
        return None

    if action == 'first_attempt':
        _, result = submit_first_attempt(
            learning_session=learning_session,
            exercise=demo_exercise,
            **form.cleaned_data,
        )
        messages.info(request, f'{result.status.value}: {result.message}')
    elif action == 'diagnosis':
        submit_diagnosis(
            learning_session=learning_session,
            answer=form.cleaned_data['diagnosis_answer'],
        )
        messages.success(request, 'Your diagnosis answer was saved. You can now revise your work.')
    elif action == 'hint':
        hint = request_curated_hint(learning_session=learning_session)
        messages.success(request, f'Hint level {hint.level} was unlocked.')
    elif action in {'save_revision', 'finish_revision'}:
        _, result = submit_revision(
            learning_session=learning_session,
            exercise=demo_exercise,
            finish=action == 'finish_revision',
            **form.cleaned_data,
        )
        if action == 'finish_revision' and result.status.value != 'PASSED':
            messages.warning(request, (
                f'Revision saved, but Teach-Back remains locked. Execution status: '
                f'{result.status.value}. An isolated runner must verify PASSED first.'
            ))
        else:
            verb = 'saved' if action == 'save_revision' else 'verified and completed'
            messages.info(request, f'Revision {verb}. {result.status.value}: {result.message}')
    elif action == 'teach_back':
        teach_back = submit_teach_back(
            learning_session=learning_session,
            response=form.cleaned_data,
        )
        if teach_back.evaluation == 'CLEAR_UNDERSTANDING':
            messages.success(request, 'Teach-Back is clear. Complete the unassisted Transfer Check.')
        else:
            messages.warning(request, f'Teach-Back needs revision: {teach_back.feedback}')
    elif action == 'transfer':
        _, result = submit_transfer_check(
            learning_session=learning_session,
            exercise=demo_exercise,
            **form.cleaned_data,
        )
        messages.info(request, f'Transfer Check saved. {result.status.value}: {result.message}')
    elif action == 'reset':
        reset_demo_session(
            browser_session_key=request.session.session_key,
            exercise=demo_exercise,
        )
        request.session.pop(CODING_SESSION_TRACKING_KEY, None)
        messages.success(request, 'This browser session was reset. Other learners were not affected.')
    else:
        return HttpResponseBadRequest('This action is not available. Return to the current step and try again.')
    return redirect('coding_quiz:exercise')


def exercise(request):
    demo_exercise = ensure_demo_exercise()
    learning_session = _browser_learning_session(request, demo_exercise)
    first_attempt = learning_session.attempts.filter(revision_number=0).first()
    latest_attempt = learning_session.attempts.order_by('-revision_number', '-created_at').first()

    forms = {
        'first_attempt': _bound_form(
            request,
            CodingAttemptForm,
            'first_attempt',
            initial={'source_code': demo_exercise.starter_code},
        ),
        'diagnosis': _bound_form(request, DiagnosisForm, 'diagnosis'),
        'save_revision': _bound_form(
            request,
            RevisionForm,
            'save_revision',
            prefix='revision',
            initial={
                'source_code': latest_attempt.answer if latest_attempt else demo_exercise.starter_code,
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
                'source_code': latest_attempt.answer if latest_attempt else demo_exercise.starter_code,
                'reasoning': latest_attempt.reasoning if latest_attempt else '',
                'confidence': latest_attempt.confidence if latest_attempt else None,
            },
        ),
        'teach_back': _bound_form(request, TeachBackForm, 'teach_back', prefix='teach'),
        'transfer': _bound_form(
            request,
            TransferAttemptForm,
            'transfer',
            prefix='transfer',
        ),
    }

    if request.method == 'POST':
        try:
            response = _handle_action(request, learning_session, demo_exercise, forms)
        except (ValidationError, PermissionDenied) as exc:
            error_text = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, error_text)
            response = None
        if response is not None:
            return response

    learning_session.refresh_from_db()
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
    diagnosis_records = list(learning_session.misconceptions.order_by('created_at'))
    teach_back_attempts = list(learning_session.teach_back_attempts.order_by('created_at'))
    transfer_attempt = learning_session.transfer_attempts.order_by('-created_at').first()
    if learning_session.current_state == WorkflowState.MASTERED:
        final_result_message = 'Mastered: all required evidence was verified.'
        review_recommendation = ''
    elif transfer_attempt and transfer_attempt.evaluation.get('status') == 'NOT_EXECUTED':
        final_result_message = 'Needs review: the Transfer Check could not be executed safely.'
        review_recommendation = 'Configure an isolated runner, then repeat the loop-values Transfer Check.'
    else:
        final_result_message = 'Needs review: the independent Transfer Check was not verified as passed.'
        review_recommendation = (
            'Review how a loop transforms each current item into a new result list, then try again.'
        )

    return render(request, 'coding_quiz/exercise.html', {
        'exercise': demo_exercise,
        'learning_session': learning_session,
        'current_stage': current_stage,
        'current_stage_label': stage_labels[current_stage],
        'progress_steps': progress_steps,
        'first_form': forms['first_attempt'],
        'diagnosis_form': forms['diagnosis'],
        'revision_form': forms['finish_revision'] if request.POST.get('action') == 'finish_revision' else forms['save_revision'],
        'teach_back_form': forms['teach_back'],
        'transfer_form': forms['transfer'],
        'diagnostic_question': DIAGNOSTIC_QUESTION,
        'first_attempt': first_attempt,
        'attempts': attempts,
        'hint_usage': hint_usage,
        'latest_evaluation': latest_evaluation,
        'diagnosis_records': diagnosis_records,
        'teach_back_attempts': teach_back_attempts,
        'transfer_attempt': transfer_attempt,
        'final_result_message': final_result_message,
        'review_recommendation': review_recommendation,
        'ai_enabled': ai_assistance_allowed(learning_session.current_state),
        'ai_configured': False,
    })
