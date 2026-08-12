from django.shortcuts import render

from apps.progress.services import overall_progress_totals, subject_progress_summary


def home(request):
    progress_summary = subject_progress_summary(request.session.session_key)
    return render(request, 'core/home.html', {
        'progress_summary': progress_summary,
        'overall_progress': overall_progress_totals(progress_summary),
    })


def subject_selection(request):
    return render(request, 'core/subject_selection.html')
