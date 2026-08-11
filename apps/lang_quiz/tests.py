from unittest.mock import patch

# pyrefly: ignore [missing-import]
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
# pyrefly: ignore [missing-import]
from django.test import TestCase
# pyrefly: ignore [missing-import]
from django.urls import reverse

from apps.ai_engine.exceptions import AIServiceUnavailable
from apps.lang_quiz.models import (
    LanguageCourseProgress,
    LanguageQuestion,
    LanguageQuizRun,
    MissingLanguageQuestion,
)
from apps.lang_quiz.quiz_engine import remember_missing
from apps.lang_quiz.services import (
    LANGUAGE_GAP_TYPES,
    begin_teach_back,
    begin_transfer_check,
    classify_language_error,
    complete_transfer_check,
    ensure_demo_question,
    get_demo_session,
    record_language_attempt_evaluation,
    request_curated_hint,
    submit_first_attempt,

    submit_revised_attempt,
)
from apps.learning_core.models import Concept, LearnerAttempt, LearningSession, Subject, Topic
from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState


class LanguageRouteTests(TestCase):
    def test_pages_load(self):
        self.assertEqual(self.client.get(reverse('lang_quiz:home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('lang_quiz:exercise')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('lang_quiz:material_setup', args=['myself'])).status_code,
            200,
        )
        started = self.client.get(reverse('lang_quiz:start_quiz', args=['reading']))
        self.assertEqual(self.client.get(started.url).status_code, 200)

    def test_complete_first_attempt_is_stored(self):
        response = self.client.post(reverse('lang_quiz:exercise'), {
            'answer': 'accept',
            'reasoning': 'Fits sentence meaning context.',
            'confidence': 4,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LearnerAttempt.objects.count(), 1)


class TenQuestionLanguageQuizTests(TestCase):
    def _start(self, section):
        response = self.client.get(reverse('lang_quiz:start_quiz', args=[section]))
        self.assertEqual(response.status_code, 302)
        run_id = response.url.rstrip('/').split('/')[-1]
        return LanguageQuizRun.objects.get(id=run_id)

    def test_each_standard_section_starts_with_ten_fresh_questions(self):
        first = self._start('vocabulary')
        second = self._start('reading')
        third = self._start('grammar')
        diagnostic = self._start('diagnostic')
        self.assertEqual(len(first.questions), 10)
        self.assertEqual(len(second.questions), 10)
        self.assertEqual(len(third.questions), 10)
        self.assertEqual(len(diagnostic.questions), 10)
        self.assertNotEqual(first.id, diagnostic.id)

    def test_wrong_answers_raise_hint_to_five_then_save_missing(self):
        run = self._start('grammar')
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        for expected_level in (2, 3, 4, 5):
            self.client.post(url, {'action': 'answer', 'answer': 'definitely wrong'})
            run.refresh_from_db()
            self.assertEqual(run.questions[0]['hint_level'], expected_level)
            self.assertFalse(run.questions[0]['resolved'])

        self.client.post(url, {'action': 'give_up'})
        run.refresh_from_db()
        self.assertTrue(run.questions[0]['resolved'])
        self.assertFalse(run.questions[0]['is_correct'])
        self.assertEqual(MissingLanguageQuestion.objects.count(), 1)

    def test_correct_missing_answer_removes_it(self):
        original = self._start('vocabulary').questions[0]
        session_key = self.client.session.session_key
        remember_missing(session_key, original)
        run = self._start('missing')
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        self.client.post(url, {'action': 'answer', 'answer': run.questions[0]['answer']})
        self.assertEqual(MissingLanguageQuestion.objects.count(), 0)

    def test_uploaded_material_creates_ten_questions_with_instruction(self):
        upload = SimpleUploadedFile(
            'words.csv',
            'xin chao,こんにちは\ncam on,ありがとう'.encode('utf-8'),
            content_type='text/csv',
        )
        response = self.client.post(
            reverse('lang_quiz:start_material_quiz', args=['myself']),
            {'files': upload, 'instruction': 'ベトナム語を日本語で答える問題'},
        )
        self.assertEqual(response.status_code, 302)
        run = LanguageQuizRun.objects.latest('created_at')
        self.assertEqual(run.section, 'myself')
        self.assertEqual(len(run.questions), 10)
        self.assertIn('ベトナム語', run.instruction)

    def test_course_reaches_complete_at_one_hundred_percent(self):
        response = self.client.get(reverse('lang_quiz:start_course', args=['daily-english']))
        self.assertEqual(response.status_code, 302)
        run = LanguageQuizRun.objects.latest('created_at')
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        for index in range(10):
            run.refresh_from_db()
            self.client.post(url, {'action': 'answer', 'answer': run.questions[index]['answer']})
            self.client.post(url, {'action': 'next'})
        progress = LanguageCourseProgress.objects.get(course_slug='daily-english')
        self.assertEqual(progress.score_percent, 100)
        self.assertTrue(progress.completed)


class LanguageWorkflowServiceTests(TestCase):
    def setUp(self):
        self.question = ensure_demo_question()
        self.session, _ = get_demo_session(browser_session_key='lang-key', question=self.question)
        transition_session(self.session, WorkflowState.DIAGNOSTIC_QUIZ)

    def test_incomplete_first_attempt_is_rejected(self):
        with self.assertRaises(ValidationError):
            submit_first_attempt(
                learning_session=self.session,
                question=self.question,
                answer='',
                reasoning='Reasoning provided',
                confidence=3,
            )

    def test_hints_require_guided_revision_and_new_action(self):
        attempt, evaluation = submit_first_attempt(
            learning_session=self.session,
            question=self.question,
            answer='wrong_word',
            reasoning='Vocab guess',
            confidence=2,
        )
        self.assertEqual(self.session.current_state, WorkflowState.GUIDED_REVISION)

        first_hint = request_curated_hint(learning_session=self.session)
        self.assertEqual(first_hint.level, 1)

        with self.assertRaises(PermissionDenied):
            request_curated_hint(learning_session=self.session)

        submit_revised_attempt(
            learning_session=self.session,
            question=self.question,
            answer='another_wrong_word',
            reasoning='Revised guess after hint',
            confidence=3,
        )

        second_hint = request_curated_hint(learning_session=self.session)
        self.assertEqual(second_hint.level, 2)

    def test_teach_back_requires_original_pass(self):
        submit_first_attempt(
            learning_session=self.session,
            question=self.question,
            answer='wrong_word',
            reasoning='Wrong assumption',
            confidence=2,
        )
        with self.assertRaises(PermissionDenied):
            begin_teach_back(learning_session=self.session, original_passed=False)

    def test_transfer_requires_clear_teach_back_and_unassisted_pass_for_mastery(self):
        submit_first_attempt(
            learning_session=self.session,
            question=self.question,
            answer='accept',
            reasoning='Correct vocabulary in context.',
            confidence=5,
        )
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)

        with self.assertRaises(PermissionDenied):
            begin_transfer_check(
                learning_session=self.session,
                teach_back_evaluation='PARTIAL_UNDERSTANDING',
            )

        begin_transfer_check(
            learning_session=self.session,
            teach_back_evaluation='CLEAR_UNDERSTANDING',
        )

        outcome = complete_transfer_check(
            learning_session=self.session,
            original_passed=True,
            teach_back_clear=True,
            transfer_passed=True,
            used_assistance=False,
            misconception_repeated=False,
        )
        self.assertEqual(outcome, WorkflowState.MASTERED)


class LanguageErrorClassificationTests(TestCase):
    def test_gap_types_constant(self):
        self.assertIn('vocabulary_gap', LANGUAGE_GAP_TYPES)
        self.assertIn('grammar_misconception', LANGUAGE_GAP_TYPES)
        self.assertIn('context_misunderstanding', LANGUAGE_GAP_TYPES)

    def test_exact_reference_answer_returns_correct(self):
        result = classify_language_error(
            answer='accept',
            reasoning='Fits text context',
            reference_answer='accept',
        )
        self.assertTrue(result['is_correct'])
        self.assertIsNone(result['gap_type'])

    def test_fallback_vocabulary_gap(self):
        result = classify_language_error(
            answer='cat',
            reasoning='I did not know the word meaning',
            question_type=LanguageQuestion.QuestionType.VOCABULARY,
        )
        self.assertFalse(result['is_correct'])
        self.assertEqual(result['gap_type'], 'vocabulary_gap')

    def test_fallback_grammar_misconception(self):
        result = classify_language_error(
            answer='he go',
            reasoning='I mixed up verb tense and grammar rule',
            question_type=LanguageQuestion.QuestionType.GRAMMAR,
        )
        self.assertFalse(result['is_correct'])
        self.assertEqual(result['gap_type'], 'grammar_misconception')

    def test_fallback_context_misunderstanding(self):
        result = classify_language_error(
            answer='She went home',
            reasoning='Misunderstood the passage context',
            question_type=LanguageQuestion.QuestionType.READING,
        )
        self.assertFalse(result['is_correct'])
        self.assertEqual(result['gap_type'], 'context_misunderstanding')

    @patch('apps.lang_quiz.services.generate_ai_response')
    def test_ai_engine_integration_success(self, mock_ai):
        mock_ai.return_value = {
            'gap_type': 'vocabulary_gap',
            'is_correct': False,
            'confidence': 0.95,
            'explanation': 'Learner confused definition of similar words.',
        }
        result = classify_language_error(
            answer='borrow',
            reasoning='Thought borrow means lend',
            question_type=LanguageQuestion.QuestionType.VOCABULARY,
        )
        self.assertEqual(result['gap_type'], 'vocabulary_gap')
        self.assertFalse(result['is_correct'])

    @patch('apps.lang_quiz.services.generate_ai_response', side_effect=AIServiceUnavailable('AI disabled'))
    def test_ai_engine_unavailable_falls_back(self, mock_ai):
        result = classify_language_error(
            answer='wrong',
            reasoning='vocab problem',
            question_type=LanguageQuestion.QuestionType.VOCABULARY,
        )
        self.assertEqual(result['gap_type'], 'vocabulary_gap')

    def test_record_language_attempt_evaluation(self):
        subject = Subject.objects.create(name='Languages', slug='languages')
        topic = Topic.objects.create(subject=subject, name='English', slug='english')
        session = LearningSession.objects.create(browser_session_key='test-key', topic=topic)
        attempt = LearnerAttempt.objects.create(
            learning_session=session,
            answer='went',
            reasoning='grammar confusion',
            confidence=3,
        )
        evaluation = record_language_attempt_evaluation(
            learner_attempt=attempt,
            question_type=LanguageQuestion.QuestionType.GRAMMAR,
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.evaluation, evaluation)
        self.assertEqual(attempt.evaluation['gap_type'], 'grammar_misconception')
