from django.shortcuts import render

from apps.learning_core.models import LearningSession


def _mastered_context(request):
    """Subjects this browser session has already mastered.

    Both entry points below render the same subject cards, so the lookup lives
    here rather than being duplicated or tied to just one of them.
    """
    session_key = request.session.session_key
    mastered_subjects = set()
    mastered_sessions = []
    if session_key:
        mastered_sessions = list(LearningSession.objects.filter(
            browser_session_key=session_key,
            mastered=True,
        ).select_related('topic__subject'))
        for s in mastered_sessions:
            if s.topic and s.topic.subject:
                mastered_subjects.add(s.topic.subject.slug)

    return {
        'mastered_subjects': mastered_subjects,
        'mastered_sessions': mastered_sessions,
    }


def home(request):
    return render(request, 'core/home.html', _mastered_context(request))


def subject_selection(request):
    return render(request, 'core/subject_selection.html', _mastered_context(request))
