from django.shortcuts import render
from apps.learning_core.models import LearningSession


def home(request):
    return subject_selection(request)


def subject_selection(request):
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

    return render(request, 'core/subject_selection.html', {
        'mastered_subjects': mastered_subjects,
        'mastered_sessions': mastered_sessions,
    })

