from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .dev_seed import clear_demo_progress, seed_demo_progress
from .services import overall_progress_totals, subject_progress_detail, summary_from_detail


def dashboard(request):
    subjects = subject_progress_detail(request.session.session_key)
    focused_subject = None
    subject_slug = request.GET.get('subject')
    if subject_slug:
        focused_subject = next(
            (entry for entry in subjects if entry['subject'].slug == subject_slug), None
        )
    if focused_subject:
        return render(request, 'progress/dashboard.html', {
            'focused_subject': focused_subject,
        })

    for entry in subjects:
        entry['preview_topics'] = entry['topics'][:3]
        entry['more_count'] = entry['total'] - 3
    summary = summary_from_detail(subjects)
    return render(request, 'progress/dashboard.html', {
        'subjects': subjects,
        'overall_progress': overall_progress_totals(summary),
    })


def dev_tools(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, 'progress/dev_tools.html')


@require_POST
def dev_seed(request):
    if not settings.DEBUG:
        raise Http404
    if request.session.session_key is None:
        request.session.create()
    seed_demo_progress(request.session.session_key)
    return redirect('progress:dashboard')


@require_POST
def dev_clear(request):
    if not settings.DEBUG:
        raise Http404
    if request.session.session_key:
        clear_demo_progress(request.session.session_key)
    return redirect('progress:dashboard')
