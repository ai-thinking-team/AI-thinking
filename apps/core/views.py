from django.shortcuts import render

from apps.progress.services import subject_progress_summary


def home(request):
    return render(request, 'core/home.html', {
        'progress_summary': subject_progress_summary(request.session.session_key),
    })


def subject_selection(request):
    return render(request, 'core/subject_selection.html')
