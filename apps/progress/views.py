from django.shortcuts import render

from .services import sessions_for_browser


def dashboard(request):
    return render(
        request,
        'progress/dashboard.html',
        {'learning_sessions': sessions_for_browser(request.session.session_key)},
    )
