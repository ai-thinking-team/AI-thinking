from apps.learning_core.models import LearningSession


def sessions_for_browser(browser_session_key):
    if not browser_session_key:
        return LearningSession.objects.none()
    return LearningSession.objects.filter(
        browser_session_key=browser_session_key
    ).select_related(
        'topic__subject',
        'activity__concept',
        'coding_plan',
    ).prefetch_related('mastery_records').order_by('-started_at', '-pk')
