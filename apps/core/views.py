from django.shortcuts import render

from apps.progress.services import overall_progress_totals, subject_progress_summary


def _progress_context(request):
    """Per-subject badges plus the overall totals bar.

    core/home.html includes core/subject_selection.html, and that partial is
    also served on its own at /subjects/ — so both entry points need this
    context or the standalone page silently renders "Not started yet" for
    every subject (Django swallows missing template variables).
    """
    progress_summary = subject_progress_summary(request.session.session_key)
    return {
        'progress_summary': progress_summary,
        'overall_progress': overall_progress_totals(progress_summary),
    }


def home(request):
    return render(request, 'core/home.html', _progress_context(request))


def subject_selection(request):
    return render(request, 'core/subject_selection.html', _progress_context(request))
