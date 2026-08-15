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
    form = CodingAttemptForm(request.POST or None)
    result = None
    exercise_data = {
        'title': 'Double every number',
        'prompt': 'Write a function that returns a new list containing twice each input number.',
        'starter_code': 'def double_numbers(numbers):\n    result = []\n    # Add your loop here\n    return result',
        'public_test_description': 'double_numbers([1, 3]) should return [2, 6].',
    }
    learning_session = None

    if request.method == 'POST' and form.is_valid():
        if request.session.session_key is None:
            request.session.create()
        demo_exercise = ensure_demo_exercise()
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
        'exercise': exercise_data,
        'execution_result': result,
        'ai_enabled': bool(learning_session and ai_assistance_allowed(learning_session.current_state)),
    })
