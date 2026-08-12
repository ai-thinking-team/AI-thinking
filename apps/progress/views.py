from django.shortcuts import get_object_or_404, render

from .services import sessions_for_browser


def dashboard(request):
    return render(
        request,
        'progress/dashboard.html',
        {'learning_sessions': sessions_for_browser(request.session.session_key)},
    )


def session_detail(request, session_id):
    learning_session = get_object_or_404(
        sessions_for_browser(request.session.session_key).prefetch_related(
            'attempts__hint_usage',
            'coach_interactions__learner_attempt',
            'coach_interactions__learner_response',
            'teach_back_attempts',
            'transfer_attempts',
            'misconceptions',
            'mastery_records',
        ),
        pk=session_id,
    )
    return render(
        request,
        'progress/session_detail.html',
        {'learning_session': learning_session},
    )
