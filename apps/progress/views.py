from django.shortcuts import render

from .services import subject_progress_detail


def dashboard(request):
    return render(
        request,
        'progress/dashboard.html',
        {'subjects': subject_progress_detail(request.session.session_key)},
    )
