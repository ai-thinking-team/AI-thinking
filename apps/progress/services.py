from dataclasses import dataclass

from django.db.models import Count, Prefetch

from apps.learning_core.models import LearningSession, MisconceptionRecord, Subject
from apps.learning_core.state_machine import WorkflowState
# Maths and Other Subjects track progress in their own models rather than in
# learning_core, so this page reads those directly. Aliased because both app
# and learning_core define a ConceptMastery / Question / Subject.
from apps.math_quiz.models import ConceptMastery as MathConceptMastery
from apps.math_quiz.models import MasteryState as MathMasteryState
from apps.other_quiz.models import Question as OtherQuestion
from apps.other_quiz.models import QuestionAttempt

# This module stays subject-neutral; the one exception is asking coding.py
# whether a row has a drill-down page, so subject_progress_detail() can link
# to it. coding.py does not import back, so there is no import cycle.
from .coding import has_detail_page


def sessions_for_browser(browser_session_key):
    if not browser_session_key:
        return LearningSession.objects.none()
    return LearningSession.objects.filter(
        browser_session_key=browser_session_key
    ).select_related(
        'topic__subject',
        # Lets has_detail_page() answer from this one query instead of firing
        # a lookup per session.
        'activity__coding_exercise',
    ).prefetch_related(
        # Ordered explicitly because _is_review_item() keeps the last row per
        # code as the current one; an unordered prefetch would make which
        # record wins depend on the database's arbitrary row order.
        Prefetch(
            'misconceptions',
            queryset=MisconceptionRecord.objects.order_by('created_at', 'pk'),
        ),
    ).order_by('-updated_at')


def _is_review_item(session):
    """A topic needs review if the final Transfer Check failed, or a confirmed
    misconception is still open.

    MisconceptionRecord is append-only: re-diagnosing the same `code` writes a
    new row rather than editing the old one, so only the newest row per code
    describes the learner's current state. CONFIRMED/REPEATED mean still open;
    DISMISSED/RESOLVED mean closed. This mirrors coding.py's
    _unresolved_misconceptions(), which does the same grouping for the
    per-session drill-down.
    """
    if session.current_state == WorkflowState.NEEDS_REVIEW:
        return True
    if session.current_state == WorkflowState.MASTERED:
        return False
    # session.misconceptions.all() reuses the prefetch_related() cache above
    # instead of firing one extra query per session (an N+1 query pattern).
    latest_by_code = {}
    for record in session.misconceptions.all():
        latest_by_code[record.code] = record
    return any(
        record.status in {
            MisconceptionRecord.Status.CONFIRMED,
            MisconceptionRecord.Status.REPEATED,
        }
        for record in latest_by_code.values()
    )


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
    """Per-subject counts for the Home page's brief overview badges.

    Delegates so Home and the Progress page can never disagree: both now
    have to account for the subjects that keep progress outside
    learning_core (see _adapted_subject_topics), and duplicating that here
    is how the two would drift apart.
    """
    return summary_from_detail(subject_progress_detail(browser_session_key))


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


@dataclass(frozen=True)
class _SubjectStandIn:
    """Stands in for a learning_core.Subject row that does not exist.

    The templates only ever read .slug and .name, and creating real rows as
    a side effect of loading a page would be a write on a GET, so missing
    subjects get this instead.
    """
    slug: str
    name: str


# The four learning areas Home offers (core/subject_selection.html). A
# learning_core.Subject row only appears once something writes one — Coding
# at migration time, Languages on a learner's first visit, Maths and Other
# Subjects never, since they store progress in their own apps. Seeding the
# grid from this list instead means the card set does not change depending
# on which subjects happen to have been used already.
KNOWN_SUBJECTS = (
    ('math', 'Mathematics'),
    ('coding', 'Coding'),
    ('languages', 'Languages'),
    ('other', 'Other Subjects'),
)


def _math_topics(browser_session_key):
    """Maths sections this browser has worked on, as progress topic rows.

    Source is ConceptMastery rather than SectionSession because
    SectionSession is deleted and recreated whenever a learner restarts a
    section, while ConceptMastery persists across restarts — restarting a
    section should not erase it from the Progress page. Its mastery_state
    already carries the same four values this page groups by, so the
    mapping is direct.
    """
    if not browser_session_key:
        return []
    records = MathConceptMastery.objects.filter(
        browser_session_key=browser_session_key,
    ).exclude(
        mastery_state=MathMasteryState.NOT_STARTED,
    ).select_related('section__unit').order_by('-updated_at')
    return [
        {
            # str(Section) is "<unit> - <title>", which keeps sections from
            # different courses apart in a flat list.
            'name': str(record.section),
            'state_label': record.get_mastery_state_display(),
            'is_review_item': record.mastery_state == MathMasteryState.NEEDS_REVIEW,
            'is_mastered': record.mastery_state == MathMasteryState.MASTERED,
            'detail_session_id': None,
        }
        for record in records
    ]


def _other_subject_topics(browser_session_key):
    """Other Subjects courses this browser has answered questions in.

    other_quiz has no workflow states to read, only right/wrong answers, so
    mastery is derived: every question answered correctly is mastered, any
    wrong answer means review, and a partly-finished course is in progress.
    """
    if not browser_session_key:
        return []
    attempts = QuestionAttempt.objects.filter(
        browser_session_key=browser_session_key,
    ).select_related('question__lesson__subject')

    per_course = {}
    for attempt in attempts:
        course = attempt.question.lesson.subject
        bucket = per_course.setdefault(course.id, {'course': course, 'answered': 0, 'correct': 0})
        bucket['answered'] += 1
        bucket['correct'] += 1 if attempt.is_correct else 0

    if not per_course:
        return []
    # One grouped query for the denominators, rather than one per course.
    question_totals = dict(
        OtherQuestion.objects.filter(lesson__subject_id__in=per_course)
        .values_list('lesson__subject_id')
        .annotate(total=Count('id'))
    )

    topics = []
    for course_id, bucket in per_course.items():
        total = question_totals.get(course_id, 0)
        is_mastered = total > 0 and bucket['correct'] == total
        topics.append({
            'name': bucket['course'].title,
            'state_label': f"{bucket['correct']}/{total} correct",
            'is_review_item': not is_mastered and bucket['answered'] > bucket['correct'],
            'is_mastered': is_mastered,
            'detail_session_id': None,
        })
    return topics


def _merge_adapted_topics(by_subject, slug, topics):
    """Fold topics sourced outside learning_core into the same grid.

    Merges rather than replaces: in DEBUG, dev_seed.py fabricates
    learning_core sessions under these same slugs, and dropping either side
    would silently hide real work or make the dev tools look broken.
    """
    entry = by_subject[slug]
    entry['topics'].extend(topics)
    entry['mastered'] += sum(1 for topic in topics if topic['is_mastered'])


def subject_progress_detail(browser_session_key):
    """Per-subject, per-topic breakdown for the Progress page. Subjects with
    no sessions yet are still included, as an empty 'not started' entry."""
    by_subject = {
        subject.slug: {'subject': subject, 'topics': [], 'mastered': 0}
        for subject in Subject.objects.order_by('name')
    }
    for slug, name in KNOWN_SUBJECTS:
        by_subject.setdefault(
            slug, {'subject': _SubjectStandIn(slug=slug, name=name), 'topics': [], 'mastered': 0},
        )
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
            # None unless a drill-down page exists for this row. Coding is the
            # only subject with one so far; when another subject grows one,
            # widen this rather than adding a second key.
            'detail_session_id': session.pk if has_detail_page(session) else None,
        })

    # Maths and Other Subjects never write to learning_core, so the loop
    # above cannot see them; they are read from their own apps instead.
    _merge_adapted_topics(by_subject, 'math', _math_topics(browser_session_key))
    _merge_adapted_topics(by_subject, 'other', _other_subject_topics(browser_session_key))

    for entry in by_subject.values():
        entry['topics'].sort(key=lambda topic: not topic['is_review_item'])
        entry['total'] = len(entry['topics'])
    # Sorted by name because the adapted subjects are appended after the
    # learning_core ones, which would otherwise leave the grid half-ordered.
    return sorted(by_subject.values(), key=lambda entry: entry['subject'].name)
