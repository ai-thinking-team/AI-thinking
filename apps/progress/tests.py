from django.test import TestCase, override_settings
from django.urls import reverse

from apps.learning_core.models import Concept, LearningSession, MisconceptionRecord, Subject, Topic
from apps.learning_core.state_machine import WorkflowState

from .services import subject_progress_summary


class ProgressRouteTests(TestCase):
    def test_dashboard_loads(self):
        self.assertEqual(self.client.get(reverse('progress:dashboard')).status_code, 200)


class ClassificationTests(TestCase):
    """subject_progress_summary()を通じて、_is_review_item()の判定ロジックを確認する。"""

    def setUp(self):
        self.session_key = 'classification-test-session'
        self.subject = Subject.objects.create(name='Coding', slug='coding')
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
            learning_session=session, concept=self.concept, code='off-by-one', evidence='...', confirmed=True,
        )
        bucket = subject_progress_summary(self.session_key)['coding']
        self.assertEqual((bucket['mastered'], bucket['needs_review'], bucket['in_progress']), (0, 1, 0))

    def test_unconfirmed_misconception_counts_as_in_progress(self):
        session = self._make_session('unconfirmed-topic', WorkflowState.FIRST_ATTEMPT)
        MisconceptionRecord.objects.create(
            learning_session=session, concept=self.concept, code='off-by-one', evidence='...', confirmed=False,
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
        subject = Subject.objects.create(name='Coding', slug='coding')
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


class SessionIsolationTests(TestCase):
    def test_other_browsers_sessions_are_not_shown(self):
        session = self.client.session
        session.save()
        my_key = session.session_key

        subject = Subject.objects.create(name='Coding', slug='coding')
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
        subject = Subject.objects.create(name='Coding', slug='coding')
        concept_topic = Topic.objects.create(subject=subject, name='Concept host', slug='concept-host')
        concept = Concept.objects.create(topic=concept_topic, name='C', slug='c')
        for i in range(5):
            topic = Topic.objects.create(subject=subject, name=f'Topic {i}', slug=f'topic-{i}')
            learning_session = LearningSession.objects.create(
                browser_session_key=session_key, topic=topic, current_state=WorkflowState.FIRST_ATTEMPT,
            )
            MisconceptionRecord.objects.create(
                learning_session=learning_session, concept=concept, code='x', evidence='y', confirmed=True,
            )

    def test_dashboard_grid_query_count_does_not_scale_with_topic_count(self):
        """Guards against the N+1 query pattern in _is_review_item() coming back."""
        with self.assertNumQueries(2):
            self.client.get(reverse('progress:dashboard'))
