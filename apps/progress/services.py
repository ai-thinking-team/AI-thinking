from apps.learning_core.models import LearningSession, Subject
from apps.learning_core.state_machine import WorkflowState


def sessions_for_browser(browser_session_key):
    if not browser_session_key:
        return LearningSession.objects.none()
    return LearningSession.objects.filter(
        browser_session_key=browser_session_key
    ).select_related('topic__subject').prefetch_related('misconceptions').order_by('-updated_at')


def _is_review_item(session):
    """A topic needs review if the final Transfer Check failed, or a confirmed
    misconception is still open. 'Still open' is approximated as 'not yet
    Mastered', since MisconceptionRecord.resolved_at is never set by the
    current Coding implementation."""
    if session.current_state == WorkflowState.NEEDS_REVIEW:
        return True
    if session.current_state == WorkflowState.MASTERED:
        return False
    # session.misconceptions.all() reuses the prefetch_related() cache above
    # instead of firing one extra query per session (an N+1 query pattern).
    return any(m.confirmed for m in session.misconceptions.all())


def _badge_text(bucket):
    parts = []
    if bucket['mastered']:
        parts.append(f"{bucket['mastered']} mastered")
    if bucket['needs_review']:
        parts.append(f"{bucket['needs_review']} to review")
    if bucket['in_progress']:
        parts.append(f"{bucket['in_progress']} in progress")
    return ' · '.join(parts) if parts else 'Not started yet'


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
    for bucket in summary.values():
        bucket['badge'] = _badge_text(bucket)
    return summary


def summary_from_detail(subjects_detail):
    """Same shape as subject_progress_summary(), built from an already-fetched
    subject_progress_detail() result instead of querying the database again."""
    summary = {}
    for entry in subjects_detail:
        bucket = summary.setdefault(entry['subject'].slug, {'mastered': 0, 'needs_review': 0, 'in_progress': 0})
        for topic in entry['topics']:
            if topic['is_mastered']:
                bucket['mastered'] += 1
            elif topic['is_review_item']:
                bucket['needs_review'] += 1
            else:
                bucket['in_progress'] += 1
    for bucket in summary.values():
        bucket['badge'] = _badge_text(bucket)
    return summary


def overall_progress_totals(summary):
    """Grand totals across all subjects, for the Home page's overall summary widget."""
    totals = {'mastered': 0, 'needs_review': 0, 'in_progress': 0}
    for bucket in summary.values():
        totals['mastered'] += bucket['mastered']
        totals['needs_review'] += bucket['needs_review']
        totals['in_progress'] += bucket['in_progress']
    return totals


def subject_progress_detail(browser_session_key):
    """Per-subject, per-topic breakdown for the Progress page. Subjects with
    no sessions yet are still included, as an empty 'not started' entry."""
    by_subject = {
        subject.slug: {'subject': subject, 'topics': [], 'mastered': 0}
        for subject in Subject.objects.order_by('name')
    }
    for session in sessions_for_browser(browser_session_key):
        subject = session.topic.subject
        entry = by_subject.setdefault(subject.slug, {'subject': subject, 'topics': [], 'mastered': 0})
        is_mastered = session.current_state == WorkflowState.MASTERED
        if is_mastered:
            entry['mastered'] += 1
        entry['topics'].append({
            'name': session.topic.name,
            'state_label': session.get_current_state_display(),
            'is_review_item': _is_review_item(session),
            'is_mastered': is_mastered,
        })
    for entry in by_subject.values():
        entry['topics'].sort(key=lambda topic: not topic['is_review_item'])
        entry['total'] = len(entry['topics'])
    return list(by_subject.values())
