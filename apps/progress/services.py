from apps.learning_core.models import LearningSession
from apps.learning_core.state_machine import WorkflowState


def sessions_for_browser(browser_session_key):
    if not browser_session_key:
        return LearningSession.objects.none()
    return LearningSession.objects.filter(
        browser_session_key=browser_session_key
    ).select_related('topic__subject').order_by('-updated_at')


def _is_review_item(session):
    """A topic needs review if the final Transfer Check failed, or a confirmed
    misconception is still open. 'Still open' is approximated as 'not yet
    Mastered', since MisconceptionRecord.resolved_at is never set by the
    current Coding implementation."""
    if session.current_state == WorkflowState.NEEDS_REVIEW:
        return True
    if session.current_state == WorkflowState.MASTERED:
        return False
    return session.misconceptions.filter(confirmed=True).exists()


def subject_progress_summary(browser_session_key):
    """Per-subject counts for the Home page's brief overview badges."""
    summary = {}
    for session in sessions_for_browser(browser_session_key):
        slug = session.topic.subject.slug
        bucket = summary.setdefault(slug, {'mastered': 0, 'needs_review': 0, 'in_progress': 0})
        if session.current_state == WorkflowState.MASTERED:
            bucket['mastered'] += 1
        elif _is_review_item(session):
            bucket['needs_review'] += 1
        else:
            bucket['in_progress'] += 1
    return summary


def subject_progress_detail(browser_session_key):
    """Per-subject, per-topic breakdown for the Progress page."""
    by_subject = {}
    for session in sessions_for_browser(browser_session_key):
        subject = session.topic.subject
        entry = by_subject.setdefault(subject.slug, {'subject': subject, 'topics': []})
        entry['topics'].append({
            'name': session.topic.name,
            'state_label': session.get_current_state_display(),
            'is_review_item': _is_review_item(session),
        })
    return list(by_subject.values())
