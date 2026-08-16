import json

from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.coding_quiz.models import CodingExercise
from apps.learning_core.models import (
    CoachInteraction,
    Concept,
    ConceptMastery,
    HintUsage,
    LearnerAttempt,
    LearningSession,
    MisconceptionRecord,
    Subject,
    TeachBackAttempt,
    Topic,
    TransferAttempt,
)
from apps.learning_core.state_machine import WorkflowState
from apps.math_quiz.models import ConceptMastery as MathConceptMastery
from apps.math_quiz.models import MasteryState as MathMasteryState
from apps.math_quiz.models import Section, Unit
from apps.other_quiz.models import Lesson as OtherLesson
from apps.other_quiz.models import Question as OtherQuestion
from apps.other_quiz.models import QuestionAttempt
from apps.other_quiz.models import Subject as OtherSubject

from .services import subject_progress_detail, subject_progress_summary


class ProgressRouteTests(TestCase):
    def test_dashboard_loads(self):
        self.assertEqual(self.client.get(reverse('progress:dashboard')).status_code, 200)


class ClassificationTests(TestCase):
    """subject_progress_summary()を通じて、_is_review_item()の判定ロジックを確認する。"""

    def setUp(self):
        self.session_key = 'classification-test-session'
        self.subject = Subject.objects.get_or_create(slug='coding', defaults={'name': 'Coding'})[0]
        concept_topic = Topic.objects.create(subject=self.subject, name='Concept host', slug='concept-host')
        self.concept = Concept.objects.create(topic=concept_topic, name='Loop values', slug='loop-values')

    def _make_session(self, slug, state):
        topic = Topic.objects.create(subject=self.subject, name=slug, slug=slug)
        return LearningSession.objects.create(
            browser_session_key=self.session_key, topic=topic, current_state=state,
        )

    def test_mastered_state_counts_as_mastered(self):
        self._make_session('mastered-topic', WorkflowState.MASTERED)
        bucket = subject_progress_summary(self.session_key)['coding']
        self.assertEqual((bucket['mastered'], bucket['needs_review'], bucket['in_progress']), (1, 0, 0))

    def test_needs_review_state_counts_as_needs_review(self):
        self._make_session('review-topic', WorkflowState.NEEDS_REVIEW)
        bucket = subject_progress_summary(self.session_key)['coding']
        self.assertEqual((bucket['mastered'], bucket['needs_review'], bucket['in_progress']), (0, 1, 0))

    def test_confirmed_misconception_counts_as_needs_review(self):
        session = self._make_session('misconception-topic', WorkflowState.FIRST_ATTEMPT)
        MisconceptionRecord.objects.create(
            learning_session=session, concept=self.concept, code='off-by-one', evidence='...', status=MisconceptionRecord.Status.CONFIRMED,
        )
        bucket = subject_progress_summary(self.session_key)['coding']
        self.assertEqual((bucket['mastered'], bucket['needs_review'], bucket['in_progress']), (0, 1, 0))

    def test_unconfirmed_misconception_counts_as_in_progress(self):
        session = self._make_session('unconfirmed-topic', WorkflowState.FIRST_ATTEMPT)
        MisconceptionRecord.objects.create(
            learning_session=session, concept=self.concept, code='off-by-one', evidence='...', status=MisconceptionRecord.Status.HYPOTHESIS,
        )
        bucket = subject_progress_summary(self.session_key)['coding']
        self.assertEqual((bucket['mastered'], bucket['needs_review'], bucket['in_progress']), (0, 0, 1))

    def test_plain_non_terminal_state_counts_as_in_progress(self):
        self._make_session('plain-topic', WorkflowState.TEACH_BACK)
        bucket = subject_progress_summary(self.session_key)['coding']
        self.assertEqual((bucket['mastered'], bucket['needs_review'], bucket['in_progress']), (0, 0, 1))


class SubjectFilterTests(TestCase):
    def setUp(self):
        session = self.client.session
        session.save()
        self.session_key = session.session_key
        subject = Subject.objects.get_or_create(slug='coding', defaults={'name': 'Coding'})[0]
        topic = Topic.objects.create(subject=subject, name='Loops', slug='loops')
        LearningSession.objects.create(
            browser_session_key=self.session_key, topic=topic, current_state=WorkflowState.MASTERED,
        )

    def test_valid_subject_slug_shows_only_that_subject(self):
        response = self.client.get(reverse('progress:dashboard'), {'subject': 'coding'})
        self.assertContains(response, 'Loops')
        self.assertContains(response, 'All subjects')

    def test_unknown_subject_slug_falls_back_to_the_grid(self):
        response = self.client.get(reverse('progress:dashboard'), {'subject': 'does-not-exist'})
        self.assertNotContains(response, 'All subjects')
        self.assertContains(response, 'Coding')


class KnownSubjectTests(TestCase):
    def test_all_four_subjects_appear_before_anything_is_used(self):
        """learning_core only grows a Subject row once a subject writes one —
        Languages waits until a learner's first visit, Maths and Other never
        write at all — so the grid must not depend on those rows existing."""
        slugs = [entry['subject'].slug for entry in subject_progress_detail('unused-browser')]

        self.assertEqual(sorted(slugs), ['coding', 'languages', 'math', 'other'])

    def test_a_real_subject_row_is_preferred_over_the_stand_in(self):
        Subject.objects.get_or_create(slug='languages', defaults={'name': 'Languages'})

        entry = next(
            entry for entry in subject_progress_detail('unused-browser')
            if entry['subject'].slug == 'languages'
        )
        self.assertIsInstance(entry['subject'], Subject)


class EmptySubjectTests(TestCase):
    def test_subject_with_no_sessions_still_shows_as_not_started(self):
        Subject.objects.get_or_create(slug='coding', defaults={'name': 'Coding'})[0]
        Subject.objects.get_or_create(slug='math', defaults={'name': 'Mathematics'})[0]

        response = self.client.get(reverse('progress:dashboard'))
        self.assertContains(response, 'Coding')
        self.assertContains(response, 'Mathematics')
        self.assertContains(response, 'Not started yet')


class SessionIsolationTests(TestCase):
    def test_other_browsers_sessions_are_not_shown(self):
        session = self.client.session
        session.save()
        my_key = session.session_key

        subject = Subject.objects.get_or_create(slug='coding', defaults={'name': 'Coding'})[0]
        my_topic = Topic.objects.create(subject=subject, name='My Topic', slug='my-topic')
        someone_elses_topic = Topic.objects.create(subject=subject, name='Someone Elses Topic', slug='someone-else')
        LearningSession.objects.create(
            browser_session_key=my_key, topic=my_topic, current_state=WorkflowState.MASTERED,
        )
        LearningSession.objects.create(
            browser_session_key='someone-elses-session', topic=someone_elses_topic,
            current_state=WorkflowState.MASTERED,
        )

        response = self.client.get(reverse('progress:dashboard'))
        self.assertContains(response, 'My Topic')
        self.assertNotContains(response, 'Someone Elses Topic')


class DevToolsTests(TestCase):
    """manage.py test always runs with DEBUG=False (Django forces this), so tests
    that need the DEBUG-only code paths must opt in with @override_settings(DEBUG=True)."""

    def test_dev_seed_rejects_get(self):
        self.assertEqual(self.client.get(reverse('progress:dev_seed')).status_code, 405)

    @override_settings(DEBUG=True)
    def test_dev_seed_creates_sessions_on_post(self):
        self.assertEqual(LearningSession.objects.count(), 0)
        self.client.post(reverse('progress:dev_seed'))
        self.assertGreater(LearningSession.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_dev_clear_removes_sessions_on_post(self):
        self.client.post(reverse('progress:dev_seed'))
        self.assertGreater(LearningSession.objects.count(), 0)
        self.client.post(reverse('progress:dev_clear'))
        self.assertEqual(LearningSession.objects.count(), 0)

    def test_dev_tools_page_404s_when_debug_is_off(self):
        self.assertEqual(self.client.get(reverse('progress:dev_tools')).status_code, 404)

    def test_dev_seed_404s_when_debug_is_off(self):
        self.assertEqual(self.client.post(reverse('progress:dev_seed')).status_code, 404)


class QueryCountTests(TestCase):
    def setUp(self):
        session = self.client.session
        session.save()
        session_key = session.session_key
        subject = Subject.objects.get_or_create(slug='coding', defaults={'name': 'Coding'})[0]
        concept_topic = Topic.objects.create(subject=subject, name='Concept host', slug='concept-host')
        concept = Concept.objects.create(topic=concept_topic, name='C', slug='c')
        for i in range(5):
            topic = Topic.objects.create(subject=subject, name=f'Topic {i}', slug=f'topic-{i}')
            learning_session = LearningSession.objects.create(
                browser_session_key=session_key, topic=topic, current_state=WorkflowState.FIRST_ATTEMPT,
            )
            MisconceptionRecord.objects.create(
                learning_session=learning_session, concept=concept, code='x', evidence='y', status=MisconceptionRecord.Status.CONFIRMED,
            )

    def test_dashboard_grid_query_count_does_not_scale_with_topic_count(self):
        """Guards against the N+1 query pattern in _is_review_item() coming back.

        5 queries, none of them per-topic: all subjects, sessions, prefetched
        misconceptions, then one each for the subjects that keep progress
        outside learning_core (Maths' ConceptMastery, Other Subjects'
        QuestionAttempt). Other Subjects takes a sixth to count questions,
        but only once it has attempts to count them for.
        """
        with self.assertNumQueries(5):
            self.client.get(reverse('progress:dashboard'))


class MathProgressTests(TestCase):
    """Maths writes to its own ConceptMastery, never to learning_core, so the
    grid only shows it via services._math_topics()."""

    def setUp(self):
        self.session_key = 'math-progress-browser'
        unit = Unit.objects.create(name='Algebra')
        self.section = Section.objects.create(unit=unit, title='Linear equations')

    def _mastery(self, state, *, section=None):
        return MathConceptMastery.objects.create(
            section=section or self.section,
            browser_session_key=self.session_key,
            mastery_state=state,
        )

    def _math_entry(self):
        return next(
            entry for entry in subject_progress_detail(self.session_key)
            if entry['subject'].slug == 'math'
        )

    def test_mastered_section_appears_as_mastered(self):
        self._mastery(MathMasteryState.MASTERED)

        topics = self._math_entry()['topics']
        self.assertEqual([topic['name'] for topic in topics], ['Algebra - Linear equations'])
        self.assertTrue(topics[0]['is_mastered'])

    def test_needs_review_section_appears_as_review_item(self):
        self._mastery(MathMasteryState.NEEDS_REVIEW)

        topics = self._math_entry()['topics']
        self.assertTrue(topics[0]['is_review_item'])
        self.assertFalse(topics[0]['is_mastered'])

    def test_untouched_sections_are_left_out(self):
        self._mastery(MathMasteryState.NOT_STARTED)

        self.assertEqual(self._math_entry()['topics'], [])

    def test_another_browsers_maths_progress_is_not_shown(self):
        MathConceptMastery.objects.create(
            section=self.section,
            browser_session_key='someone-else',
            mastery_state=MathMasteryState.MASTERED,
        )

        self.assertEqual(self._math_entry()['topics'], [])


class OtherSubjectProgressTests(TestCase):
    """Other Subjects has no workflow states, so services._other_subject_topics()
    derives them from right/wrong answers."""

    def setUp(self):
        self.session_key = 'other-progress-browser'
        self.course = OtherSubject.objects.create(id='sub_hist', title='History')
        lesson = OtherLesson.objects.create(
            id='les_ww2', subject=self.course, chapter='1', title='WWII',
        )
        self.questions = [
            OtherQuestion.objects.create(
                lesson=lesson, title=f'Q{index}', prompt='...', correct_answer='a',
            )
            for index in range(3)
        ]

    def _answer(self, question, is_correct):
        QuestionAttempt.objects.create(
            question=question, browser_session_key=self.session_key, is_correct=is_correct,
        )

    def _other_entry(self):
        return next(
            entry for entry in subject_progress_detail(self.session_key)
            if entry['subject'].slug == 'other'
        )

    def test_all_questions_correct_counts_as_mastered(self):
        for question in self.questions:
            self._answer(question, True)

        topic = self._other_entry()['topics'][0]
        self.assertEqual(topic['name'], 'History')
        self.assertEqual(topic['state_label'], '3/3 correct')
        self.assertTrue(topic['is_mastered'])

    def test_a_wrong_answer_counts_as_review(self):
        self._answer(self.questions[0], True)
        self._answer(self.questions[1], False)

        topic = self._other_entry()['topics'][0]
        self.assertTrue(topic['is_review_item'])
        self.assertFalse(topic['is_mastered'])

    def test_partly_answered_course_counts_as_in_progress(self):
        self._answer(self.questions[0], True)

        topic = self._other_entry()['topics'][0]
        self.assertFalse(topic['is_mastered'])
        self.assertFalse(topic['is_review_item'])

    def test_another_browsers_answers_are_not_shown(self):
        QuestionAttempt.objects.create(
            question=self.questions[0], browser_session_key='someone-else', is_correct=True,
        )

        self.assertEqual(self._other_entry()['topics'], [])


class CodingSessionEvidenceTests(TestCase):
    """The Coding drill-down at progress:coding_session_detail. Its own
    class because these build real Coding evidence via coding_quiz views,
    unlike the subject-neutral dashboard tests above."""

    def test_coding_subject_page_links_each_session_to_its_detail(self):
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        learning_session = LearningSession.objects.get(
            browser_session_key=self.client.session.session_key,
        )

        response = self.client.get(reverse('progress:dashboard'), {'subject': 'coding'})

        self.assertContains(
            response,
            reverse('progress:coding_session_detail', args=(learning_session.pk,)),
        )

    def test_sessions_without_a_coding_exercise_are_not_linked(self):
        """dev_seed seeds Coding topics with no activity; linking those 404s."""
        session_key = 'no-activity-browser'
        subject, _ = Subject.objects.get_or_create(slug='coding', defaults={'name': 'Coding'})
        topic = Topic.objects.create(subject=subject, name='Seeded topic', slug='seeded-topic')
        LearningSession.objects.create(
            browser_session_key=session_key,
            topic=topic,
            current_state=WorkflowState.FIRST_ATTEMPT,
        )

        entry = next(
            entry for entry in subject_progress_detail(session_key)
            if entry['subject'].slug == 'coding'
        )
        seeded = next(topic for topic in entry['topics'] if topic['name'] == 'Seeded topic')
        self.assertIsNone(seeded['detail_session_id'])

    def test_detail_shows_exercise_history(self):
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercise = CodingExercise.objects.get(slug='double-numbers')
        learning_session = LearningSession.objects.get(
            browser_session_key=browser_key,
            activity=exercise.activity,
        )
        LearnerAttempt.objects.create(
            learning_session=learning_session,
            activity=exercise.activity,
            answer='def double_numbers(values):\n    return values',
            reasoning='My preserved reasoning',
            confidence=2,
            evaluation={'status': 'FAILED'},
        )

        detail = self.client.get(reverse('progress:coding_session_detail', args=(learning_session.pk,)))

        self.assertContains(detail, 'def double_numbers(values)')
        self.assertContains(detail, 'My preserved reasoning')

    def test_session_detail_cannot_read_another_browser_history(self):
        exercise = CodingExercise.objects.get(slug='double-numbers')
        other = LearningSession.objects.create(
            browser_session_key='another-browser',
            topic=exercise.activity.concept.topic,
            activity=exercise.activity,
            current_state=WorkflowState.FIRST_ATTEMPT,
        )

        response = self.client.get(reverse('progress:coding_session_detail', args=(other.pk,)))

        self.assertEqual(response.status_code, 404)

    def test_planning_evidence_is_shown_only_to_its_browser_session(self):
        exercise_url = reverse('coding_quiz:exercise_detail', args=('double-numbers',))
        self.client.post(exercise_url, {
            'action': 'plan',
            'solution_plan': 'Use a unique per-item transformation plan.',
            'predicted_output': 'unique-output-[2, 6]',
        })
        learning_session = LearningSession.objects.get(
            browser_session_key=self.client.session.session_key,
        )

        detail = self.client.get(
            reverse('progress:coding_session_detail', args=(learning_session.pk,))
        )
        another_browser = Client()
        other_dashboard = another_browser.get(reverse('progress:dashboard'))
        other_detail = another_browser.get(
            reverse('progress:coding_session_detail', args=(learning_session.pk,))
        )

        self.assertContains(detail, 'Use a unique per-item transformation plan.')
        self.assertContains(detail, 'unique-output-[2, 6]')
        self.assertNotContains(other_dashboard, 'unique-output-[2, 6]')
        self.assertEqual(other_detail.status_code, 404)

    def test_session_detail_renders_coach_interactions_hint_usage_and_mastery(self):
        from apps.learning_core.models import CoachLearnerResponse
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercise = CodingExercise.objects.get(slug='double-numbers')
        learning_session = LearningSession.objects.get(
            browser_session_key=browser_key,
            activity=exercise.activity,
        )
        attempt = LearnerAttempt.objects.create(
            learning_session=learning_session,
            activity=exercise.activity,
            answer='def double_numbers(values):\n    return values',
            reasoning='Original approach',
            confidence=3,
            evaluation={'status': 'FAILED', 'message': 'Public test failed'},
        )
        HintUsage.objects.create(
            learner_attempt=attempt,
            level=1,
            content='Think about the loop variable value.',
        )
        interaction = CoachInteraction.objects.create(
            learning_session=learning_session,
            learner_attempt=attempt,
            interaction_type=CoachInteraction.InteractionType.DIAGNOSTIC,
            source=CoachInteraction.Source.CURATED_FALLBACK,
            response={'message': 'Which value changes during iteration?'},
            failure_code='AI_UNAVAILABLE',
        )
        CoachLearnerResponse.objects.create(
            interaction=interaction,
            response='The current loop element changes.',
        )
        ConceptMastery.objects.create(
            learning_session=learning_session,
            concept=exercise.activity.concept,
            status=ConceptMastery.Status.NEEDS_REVIEW,
            reason='Transfer test failed.',
            recommendation='Review loop value binding.',
        )

        response = self.client.get(reverse('progress:coding_session_detail', args=(learning_session.pk,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Coach interactions')
        self.assertContains(response, 'Which value changes during iteration?')
        self.assertContains(response, 'The current loop element changes.')
        self.assertContains(response, 'Fallback code: AI_UNAVAILABLE')
        self.assertContains(response, 'Think about the loop variable value.')
        self.assertContains(response, 'Transfer test failed.')
        self.assertContains(response, 'Review loop value binding.')

    def test_detail_summarizes_coding_evidence_and_uses_fixed_query_count(self):
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercises = CodingExercise.objects.select_related('activity__concept').filter(
            slug__in=('double-numbers', 'square-numbers', 'increment-numbers')
        )
        for exercise in exercises:
            session, _ = LearningSession.objects.get_or_create(
                browser_session_key=browser_key,
                topic=exercise.activity.concept.topic,
                activity=exercise.activity,
            )
            attempt = LearnerAttempt.objects.create(
                learning_session=session,
                activity=exercise.activity,
                answer='def attempt():\n    return []',
                reasoning='A recorded approach.',
                confidence=2,
                revision_number=0,
                evaluation={'status': 'FAILED'},
            )
            LearnerAttempt.objects.create(
                learning_session=session,
                activity=exercise.activity,
                answer='def attempt():\n    return [1]',
                reasoning='A revised approach.',
                confidence=4,
                revision_number=1,
                evaluation={'status': 'PASSED'},
            )
            HintUsage.objects.create(learner_attempt=attempt, level=2, content='A stored hint.')
        double = exercises.get(slug='double-numbers')
        double_session = LearningSession.objects.get(
            browser_session_key=browser_key, activity=double.activity
        )
        MisconceptionRecord.objects.create(
            learning_session=double_session,
            concept=double.activity.concept,
            code='loop-value-misuse',
            evidence='The learner still applies the operation to the whole list.',
            status=MisconceptionRecord.Status.CONFIRMED,
        )
        ConceptMastery.objects.create(
            learning_session=double_session,
            concept=double.activity.concept,
            status=ConceptMastery.Status.NEEDS_REVIEW,
            reason='The Transfer Check did not pass.',
            recommendation='Review one current loop value at a time.',
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse('progress:coding_session_detail', args=(double_session.pk,))
            )

        self.assertEqual(response.status_code, 200)
        # The evidence above spans several related tables; coding.py prefetches
        # them all up front, so the count must not grow with attempts/hints.
        self.assertLessEqual(len(queries), 12)
        self.assertContains(response, '2/5 → 4/5')
        self.assertContains(response, 'Level 2')
        self.assertContains(response, 'loop-value-misuse')
        self.assertContains(response, 'Review one current loop value at a time.')

    def test_detail_labels_teach_back_fields_and_keeps_resolved_misconceptions_out_of_attention(self):
        self.client.get(reverse('coding_quiz:exercise_detail', args=('double-numbers',)))
        browser_key = self.client.session.session_key
        exercise = CodingExercise.objects.select_related('activity__concept').get(slug='double-numbers')
        learning_session = LearningSession.objects.get(
            browser_session_key=browser_key,
            activity=exercise.activity,
        )
        TeachBackAttempt.objects.create(
            learning_session=learning_session,
            response=json.dumps({
                'original_issue': 'I returned values without doubling them.',
                'failure_reason': 'Each current item was unchanged.',
                'correction': 'I double the current item first.',
                'concept': 'A loop works with one current item.',
                'prevention': 'I will trace one item.',
            }),
            evaluation='CLEAR_UNDERSTANDING',
        )
        confirmed = MisconceptionRecord.objects.create(
            learning_session=learning_session,
            concept=exercise.activity.concept,
            code='loop-value-misuse',
            evidence='Initially confirmed.',
            status=MisconceptionRecord.Status.CONFIRMED,
        )
        MisconceptionRecord.objects.create(
            learning_session=learning_session,
            concept=exercise.activity.concept,
            code='loop-value-misuse',
            evidence='Later resolved.',
            status=MisconceptionRecord.Status.RESOLVED,
            supersedes=confirmed,
        )
        TransferAttempt.objects.create(
            learning_session=learning_session,
            activity=exercise.transfer_activity,
            response='def word_lengths(words):\n    return [len(word) for word in words]',
            reasoning='I transform each word.',
            confidence=5,
            passed=True,
            evaluation={'status': 'PASSED'},
        )

        response = self.client.get(reverse('progress:coding_session_detail', args=(learning_session.pk,)))

        self.assertContains(response, 'Why the original approach failed')
        self.assertContains(response, 'Each current item was unchanged.')
        self.assertNotContains(response, 'Current attention:')
        self.assertContains(response, 'Runner status:</strong> PASSED')
