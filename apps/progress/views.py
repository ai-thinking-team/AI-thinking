from django.http import Http404
from django.shortcuts import render

from .services import (
    coding_dashboard_for_browser,
    coding_session_detail,
    coding_session_for_browser,
)


def dashboard(request):
    return render(
        request,
        'progress/dashboard.html',
        {'dashboard': coding_dashboard_for_browser(request.session.session_key)},
    )


def session_detail(request, session_id):
    learning_session = coding_session_for_browser(request.session.session_key, session_id)
    if learning_session is None:
        raise Http404('Learning session not found.')
    return render(
        request,
        'progress/session_detail.html',
        {
            'learning_session': learning_session,
            'evidence': coding_session_detail(learning_session),
        },
    )
