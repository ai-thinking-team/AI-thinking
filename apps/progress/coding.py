"""Read-only Coding progress projections from append-only learning evidence.

Kept in its own module rather than in services.py because everything here is
Coding-specific: sessions_for_browser() below filters on
`activity__coding_exercise`, and the projections read apps.coding_quiz's
CodingExercise/CodingPlanEvidence. services.py stays subject-neutral and
summarises every subject for the dashboard; this module powers the one
drill-down level below that (see progress/urls.py's coding/sessions/<id>/).
"""

import json
from dataclasses import dataclass

from django.db.models import Prefetch

from apps.learning_core.models import (
    CoachInteraction,
    ConceptMastery,
    LearnerAttempt,
    LearningSession,
    MisconceptionRecord,
    TeachBackAttempt,
    TransferAttempt,
)


TEACH_BACK_FIELD_LABELS = {
    'original_issue': 'Original issue',
    'failure_reason': 'Why the original approach failed',
    'correction': 'Correction',
    'concept': 'Underlying concept',
    'prevention': 'How to prevent this error',
}


def _ordered_prefetches():
    return (
        Prefetch(
            'attempts',
            queryset=LearnerAttempt.objects.order_by('revision_number', 'created_at', 'pk').prefetch_related(
                'hint_usage'
            ),
            to_attr='progress_attempts',
        ),
        Prefetch(
            'teach_back_attempts',
            queryset=TeachBackAttempt.objects.order_by('created_at', 'pk'),
            to_attr='progress_teach_back_attempts',
        ),
        Prefetch(
            'transfer_attempts',
            queryset=TransferAttempt.objects.select_related('activity').order_by('created_at', 'pk'),
            to_attr='progress_transfer_attempts',
        ),
        Prefetch(
            'misconceptions',
            queryset=MisconceptionRecord.objects.select_related('concept').order_by('created_at', 'pk'),
            to_attr='progress_misconceptions',
        ),
        Prefetch(
            'mastery_records',
            queryset=ConceptMastery.objects.select_related('concept').order_by('created_at', 'pk'),
            to_attr='progress_mastery_records',
        ),
    )


def sessions_for_browser(browser_session_key, *, include_evidence=False):
    """Return only sessions owned by the current browser, newest first."""
    if not browser_session_key:
        return LearningSession.objects.none()
    sessions = LearningSession.objects.filter(
        browser_session_key=browser_session_key,
        activity__coding_exercise__isnull=False,
    ).select_related(
        'topic__subject',
        'activity__concept',
        'activity__coding_exercise',
        'coding_plan',
    ).order_by('-started_at', '-pk')
    return sessions.prefetch_related(*_ordered_prefetches()) if include_evidence else sessions


def has_detail_page(session):
    """Whether views.coding_session_detail can render this session.

    The same condition as sessions_for_browser()'s
    `activity__coding_exercise__isnull=False` filter, but evaluated in Python
    so services.subject_progress_detail() can decide per row whether to link,
    without a second query — it select_related()s the same relation. Sessions
    without a coding exercise do occur: dev_seed.py seeds Coding topics with
    no activity at all, and linking those would 404.
    """
    activity = session.activity
    # A missing reverse one-to-one raises RelatedObjectDoesNotExist, which
    # Django deliberately makes an AttributeError subclass, so getattr's
    # default covers both "no activity" and "activity isn't a coding one".
    return activity is not None and getattr(activity, 'coding_exercise', None) is not None


def _status_badge(status):
    if status in {ConceptMastery.Status.MASTERED, 'CLEAR_UNDERSTANDING', 'PASSED', 'RESOLVED'}:
        return 'success'
    if status in {ConceptMastery.Status.NEEDS_REVIEW, 'REPEATED', 'CONFIRMED'}:
        return 'danger'
    return 'warning'


def _latest(records):
    return records[-1] if records else None


def _latest_misconceptions_by_code(records):
    latest = {}
    for record in records:
        latest[record.code] = record
    return tuple(latest.values())


def _unresolved_misconceptions(records):
    return tuple(
        record for record in _latest_misconceptions_by_code(records)
        if record.status in {
            MisconceptionRecord.Status.CONFIRMED,
            MisconceptionRecord.Status.REPEATED,
        }
    )


def _confidence_change(attempts):
    if not attempts:
        return 'No code attempt yet.'
    first = attempts[0].confidence
    latest = attempts[-1].confidence
    return f'{first}/5' if first == latest else f'{first}/5 → {latest}/5'


def _highest_hint_level(attempts):
    return max(
        (hint.level for attempt in attempts for hint in attempt.hint_usage.all()),
        default=0,
    )


@dataclass(frozen=True)
class CodingSessionSummary:
    session: LearningSession
    title: str
    concept: str
    state: str
    state_label: str
    active: bool
    attempt_count: int
    confidence_change: str
    highest_hint_level: int
    teach_back: TeachBackAttempt | None
    transfer: TransferAttempt | None
    mastery: ConceptMastery | None
    unresolved_misconceptions: tuple

    @property
    def mastery_badge(self):
        return _status_badge(self.mastery.status) if self.mastery else 'warning'

    @property
    def teach_back_badge(self):
        return _status_badge(self.teach_back.evaluation) if self.teach_back else 'warning'

    @property
    def transfer_badge(self):
        return 'success' if self.transfer and self.transfer.passed else 'warning'


def coding_session_summary(session):
    """Build one template-ready summary without querying related managers."""
    attempts = getattr(session, 'progress_attempts', ())
    teach_back_attempts = getattr(session, 'progress_teach_back_attempts', ())
    transfer_attempts = getattr(session, 'progress_transfer_attempts', ())
    misconceptions = getattr(session, 'progress_misconceptions', ())
    mastery_records = getattr(session, 'progress_mastery_records', ())
    activity = session.activity
    return CodingSessionSummary(
        session=session,
        title=activity.title if activity else session.topic.name,
        concept=activity.concept.name if activity else '',
        state=session.current_state,
        state_label=session.get_current_state_display(),
        active=session.ended_at is None,
        attempt_count=len(attempts),
        confidence_change=_confidence_change(attempts),
        highest_hint_level=_highest_hint_level(attempts),
        teach_back=_latest(teach_back_attempts),
        transfer=_latest(transfer_attempts),
        mastery=_latest(mastery_records),
        unresolved_misconceptions=_unresolved_misconceptions(misconceptions),
    )


def _teach_back_fields(response):
    try:
        values = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(values, dict):
        return ()
    return tuple(
        {'label': label, 'value': str(values.get(field, '')).strip()}
        for field, label in TEACH_BACK_FIELD_LABELS.items()
        if str(values.get(field, '')).strip()
    )


def coding_session_detail(session):
    """Project a fully prefetched session into labelled, privacy-safe evidence."""
    summary = coding_session_summary(session)
    attempts = getattr(session, 'progress_attempts', ())
    interactions = getattr(session, 'progress_coach_interactions', ())
    teach_back_attempts = getattr(session, 'progress_teach_back_attempts', ())
    transfers = getattr(session, 'progress_transfer_attempts', ())
    misconceptions = getattr(session, 'progress_misconceptions', ())
    mastery_records = getattr(session, 'progress_mastery_records', ())
    return {
        'summary': summary,
        'plan': getattr(session, 'coding_plan', None),
        'attempts': attempts,
        'interactions': interactions,
        'teach_back_attempts': tuple({
            'attempt': attempt,
            'response_fields': _teach_back_fields(attempt.response),
            'badge': _status_badge(attempt.evaluation),
        } for attempt in teach_back_attempts),
        'transfer_attempts': transfers,
        'misconceptions': misconceptions,
        'unresolved_misconceptions': summary.unresolved_misconceptions,
        'mastery_records': mastery_records,
    }


def coding_session_for_browser(browser_session_key, session_id):
    """Fetch one browser-owned session with all detail evidence in fixed query count."""
    return sessions_for_browser(browser_session_key, include_evidence=True).prefetch_related(
        Prefetch(
            'coach_interactions',
            queryset=CoachInteraction.objects.select_related('learner_attempt').prefetch_related(
                'learner_response'
            ).order_by('created_at', 'pk'),
            to_attr='progress_coach_interactions',
        ),
    ).filter(pk=session_id).first()
