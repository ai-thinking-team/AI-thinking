from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render

from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState, ai_assistance_allowed

from .forms import CodingAttemptForm
from .services import ensure_demo_exercise, get_demo_session, submit_first_attempt


def home(request):
    return render(request, 'coding_quiz/home.html')


def exercise(request):
    demo_exercise = ensure_demo_exercise()
    form = CodingAttemptForm(request.POST or None)
    result = None
    learning_session = None

    if request.method == 'POST' and form.is_valid():
        if request.session.session_key is None:
            request.session.create()
        learning_session, _ = get_demo_session(
            browser_session_key=request.session.session_key,
            exercise=demo_exercise,
        )
        try:
            if learning_session.current_state == WorkflowState.TOPIC_SELECTED:
                transition_session(learning_session, WorkflowState.DIAGNOSTIC_QUIZ)
            _, result = submit_first_attempt(
                learning_session=learning_session,
                exercise=demo_exercise,
                **form.cleaned_data,
            )
            messages.info(request, result.message)
        except ValidationError as exc:
            form.add_error(None, exc)

    return render(request, 'coding_quiz/exercise.html', {
        'form': form,
        'exercise': demo_exercise,
        'execution_result': result,
        'ai_enabled': bool(learning_session and ai_assistance_allowed(learning_session.current_state)),
    })
