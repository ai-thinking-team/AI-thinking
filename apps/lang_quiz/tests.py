from unittest.mock import patch

# pyrefly: ignore [missing-import]
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
# pyrefly: ignore [missing-import]
from django.test import TestCase
# pyrefly: ignore [missing-import]
from django.urls import reverse
from django.utils.html import escape

from apps.ai_engine.exceptions import AIServiceUnavailable
from apps.lang_quiz.models import (
    LanguageCourseProgress,
    LanguageQuestion,
    LanguageQuizRun,
    MissingLanguageQuestion,
)
from apps.lang_quiz.quiz_engine import (
    _decode_upload,
    _parse_exact_pdf_quiz,
    remember_missing,
)
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
    EXACT_PDF_TEXT = '''
Chinese Vocabulary Fill-in Quiz
01. 我每天早上七点（ ）。
日本語：私は毎朝7時に（ ）。
A. 起床
B. 睡觉
C. 下班
D. 洗澡
E. 回家
02. 今天很冷，出门要穿（ ）。
日本語：今日は寒いので（ ）を着ます。
A. 帽子
B. 外套
C. 鞋子
D. 裙子
E. 手表
解答一覧
01. A 起床
02. B 外套
'''

    def _start(self, section):
        response = self.client.get(reverse('lang_quiz:start_quiz', args=[section]))
        self.assertEqual(response.status_code, 302)
        run_id = response.url.rstrip('/').split('/')[-1]
        return LanguageQuizRun.objects.get(id=run_id)

    def test_damaged_pdf_is_not_reported_as_scanned(self):
        upload = SimpleUploadedFile(
            'damaged.pdf', b'not a pdf', content_type='application/pdf',
        )

        with self.assertRaisesRegex(ValueError, 'could not be read'):
            _decode_upload(upload)

    def test_pdf_without_text_is_reported_as_scanned(self):
        from io import BytesIO
        from pypdf import PdfWriter

        stream = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(stream)
        upload = SimpleUploadedFile(
            'image-only.pdf', stream.getvalue(), content_type='application/pdf',
        )

        with self.assertRaisesRegex(ValueError, 'scanned image'):
            _decode_upload(upload)

    def test_exact_pdf_parser_preserves_prompts_choice_order_and_answers(self):
        questions = _parse_exact_pdf_quiz(
            self.EXACT_PDF_TEXT,
            section='vocabulary',
            source_name='quiz.pdf',
        )

        self.assertEqual(len(questions), 2)
        self.assertEqual(
            questions[0]['prompt'],
            '01. 我每天早上七点（ ）。\n日本語：私は毎朝7時に（ ）。',
        )
        self.assertEqual(
            questions[0]['choices'],
            ['A. 起床', 'B. 睡觉', 'C. 下班', 'D. 洗澡', 'E. 回家'],
        )
        self.assertEqual(questions[0]['answer'], 'A. 起床')
        self.assertEqual(questions[1]['answer'], 'B. 外套')

    @patch('apps.lang_quiz.views.import_pdf_questions_exact')
    def test_exact_pdf_mode_creates_run_without_ai_generation(self, mock_import):
        mock_import.return_value = (
            _parse_exact_pdf_quiz(self.EXACT_PDF_TEXT, source_name='quiz.pdf'),
            'quiz.pdf',
        )
        upload = SimpleUploadedFile('quiz.pdf', b'%PDF-test', content_type='application/pdf')

        response = self.client.post(
            reverse('lang_quiz:start_material_quiz', args=['vocabulary']),
            {
                'import_mode': 'exact_pdf',
                'files': upload,
                'instruction': '',
                'answer_mode': 'typing',
            },
        )

        self.assertEqual(response.status_code, 302)
        run = LanguageQuizRun.objects.latest('created_at')
        self.assertEqual(run.mode, 'upload_exact')
        self.assertEqual(run.instruction, 'PDFの問題をそのまま出題')
        self.assertEqual(len(run.questions), 2)
        self.assertEqual(run.questions[0]['choices'][0], 'A. 起床')
        mock_import.assert_called_once()

    def test_material_setup_shows_both_import_modes(self):
        response = self.client.get(
            reverse('lang_quiz:material_setup', args=['vocabulary'])
        )
        self.assertContains(response, 'AIで新しい問題を作る')
        self.assertContains(response, 'PDFの問題をそのまま出題する')

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

    def test_diagnostic_does_not_show_dont_know_button(self):
        run = self._start('diagnostic')
        response = self.client.get(reverse('lang_quiz:quiz_run', args=[run.id]))
        self.assertNotContains(response, 'わからない（不正解として次へ）')
        self.assertNotContains(response, 'name="action" value="dont_know"')

    def test_wrong_answers_raise_hint_to_five_then_save_missing(self):
        run = self._start('grammar')
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        self.assertEqual(run.questions[0]['hint_level'], 0)
        self.assertNotContains(self.client.get(url), 'SMART HINT')
        for expected_level in (1, 2, 3, 4, 5):
            self.client.post(url, {'action': 'answer', 'answer': 'definitely wrong'})
            run.refresh_from_db()
            self.assertEqual(run.questions[0]['hint_level'], expected_level)
            self.assertFalse(run.questions[0]['resolved'])
            self.assertEqual(MissingLanguageQuestion.objects.count(), 1)

        self.client.post(url, {'action': 'give_up'})
        run.refresh_from_db()
        self.assertTrue(run.questions[0]['resolved'])
        self.assertFalse(run.questions[0]['is_correct'])
        self.assertEqual(run.current_index, 1)
        self.assertEqual(MissingLanguageQuestion.objects.count(), 1)

    @patch('apps.lang_quiz.quiz_engine.generate_ai_response', side_effect=AIServiceUnavailable('offline'))
    def test_each_learning_section_shows_hint_levels_one_through_five(self, _mock_ai):
        for section in ('vocabulary', 'reading', 'grammar', 'myself'):
            with self.subTest(section=section):
                if section == 'myself':
                    session = self.client.session
                    session.save()
                    question = {
                        'key': 'myself-hint-test',
                        'prompt': 'Type the missing word: Learning is _____.',
                        'answer': 'valuable',
                        'explanation': 'The material uses the word valuable.',
                        'next_step': 'Write a new sentence with valuable.',
                        'hints': [
                            'Think about a positive adjective.',
                            'It describes something worth having.',
                            'The word has eight letters.',
                            'It starts with v and ends with e.',
                            'The answer is valuable.',
                        ],
                        'section': 'myself',
                        'choices': [],
                        'answer_mode': 'typing',
                        'difficulty': 'intermediate',
                        'attempt_count': 0,
                        'hint_level': 0,
                        'resolved': False,
                        'is_correct': None,
                        'last_feedback': '',
                    }
                    run = LanguageQuizRun.objects.create(
                        browser_session_key=session.session_key,
                        section='myself',
                        mode='upload',
                        questions=[question],
                    )
                else:
                    run = self._start(section)

                url = reverse('lang_quiz:quiz_run', args=[run.id])
                self.assertNotContains(self.client.get(url), 'SMART HINT')
                for expected_level in range(1, 6):
                    current = run.questions[0]
                    wrong_answer = next(
                        (
                            choice for choice in current.get('choices', [])
                            if choice.casefold() != current['answer'].casefold()
                        ),
                        'definitely wrong',
                    )
                    response = self.client.post(
                        url,
                        {'action': 'answer', 'answer': wrong_answer},
                        follow=True,
                    )
                    run.refresh_from_db()
                    self.assertEqual(run.questions[0]['hint_level'], expected_level)
                    self.assertContains(response, f'LEVEL {expected_level} / 5')

    @patch('apps.lang_quiz.quiz_engine.generate_ai_response', side_effect=AIServiceUnavailable('offline'))
    def test_vocabulary_supports_five_choice_and_typing_modes(self, _mock_ai):
        choice_response = self.client.get(
            reverse('lang_quiz:start_vocabulary', args=['multiple_choice'])
        )
        choice_run = LanguageQuizRun.objects.get(
            id=choice_response.url.rstrip('/').split('/')[-1]
        )
        self.assertEqual(choice_run.mode, 'multiple_choice')
        self.assertTrue(all(len(question['choices']) == 5 for question in choice_run.questions))
        self.assertTrue(all(question['answer'] in question['choices'] for question in choice_run.questions))

        typing_response = self.client.get(
            reverse('lang_quiz:start_vocabulary', args=['typing'])
        )
        typing_run = LanguageQuizRun.objects.get(
            id=typing_response.url.rstrip('/').split('/')[-1]
        )
        self.assertEqual(typing_run.mode, 'typing')
        self.assertTrue(all(question['choices'] == [] for question in typing_run.questions))
        self.assertContains(self.client.get(typing_response.url), 'placeholder="Type your answer"')

    def test_answer_after_hint_counts_as_incorrect(self):
        run = self._start('grammar')
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        self.client.post(url, {'action': 'answer', 'answer': 'wrong'})
        run.refresh_from_db()
        self.client.post(url, {'action': 'answer', 'answer': run.questions[0]['answer']})
        run.refresh_from_db()
        self.assertTrue(run.questions[0]['resolved'])
        self.assertFalse(run.questions[0]['is_correct'])
        self.assertEqual(run.correct_count, 0)
        self.assertEqual(MissingLanguageQuestion.objects.count(), 1)

    def test_diagnostic_wrong_answer_advances_without_immediate_feedback(self):
        run = self._start('diagnostic')
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        self.assertNotContains(self.client.get(url), 'SMART HINT')
        question = run.questions[0]
        wrong_answer = next(
            (choice for choice in question.get('choices', []) if choice != question['answer']),
            'wrong',
        )
        self.client.post(url, {'action': 'answer', 'answer': wrong_answer})
        run.refresh_from_db()
        self.assertEqual(run.questions[0]['hint_level'], 0)
        self.assertTrue(run.questions[0]['resolved'])
        self.assertFalse(run.questions[0]['is_correct'])
        self.assertEqual(run.questions[0]['submitted_answer'], wrong_answer)
        self.assertEqual(run.current_index, 1)
        self.assertEqual(run.correct_count, 0)
        self.assertEqual(MissingLanguageQuestion.objects.count(), 1)
        next_page = self.client.get(url)
        self.assertNotContains(next_page, 'SMART HINT')
        self.assertNotContains(next_page, run.questions[0]['explanation'])

    def test_diagnostic_shows_all_answers_and_explanations_after_last_question(self):
        run = self._start('diagnostic')
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        expected_prompts = [question['prompt'] for question in run.questions]
        expected_explanations = [question['explanation'] for question in run.questions]

        for _index in range(len(run.questions)):
            run.refresh_from_db()
            question = run.questions[run.current_index]
            response = self.client.post(
                url,
                {'action': 'answer', 'answer': question['answer']},
                follow=True,
            )
            if not run.current_index == len(run.questions) - 1:
                self.assertNotContains(response, question['explanation'])

        run.refresh_from_db()
        self.assertTrue(run.finished)
        self.assertEqual(run.correct_count, len(run.questions))
        self.assertContains(response, '診断テスト結果一覧')
        for prompt, explanation in zip(expected_prompts, expected_explanations):
            self.assertContains(response, escape(prompt))
            self.assertContains(response, escape(explanation))
        self.assertContains(response, 'CORRECT', count=len(run.questions))

    @patch('apps.lang_quiz.quiz_engine.generate_ai_response', side_effect=AIServiceUnavailable('offline'))
    def test_latest_diagnostic_sets_each_section_difficulty(self, _mock_ai):
        session = self.client.session
        session.save()
        LanguageQuizRun.objects.create(
            browser_session_key=session.session_key,
            section='diagnostic',
            mode='random',
            finished=True,
            questions=[
                {'section': 'vocabulary', 'is_correct': False},
                {'section': 'vocabulary', 'is_correct': False},
                {'section': 'vocabulary', 'is_correct': False},
                {'section': 'reading', 'is_correct': True},
                {'section': 'reading', 'is_correct': True},
                {'section': 'reading', 'is_correct': False},
                {'section': 'grammar', 'is_correct': True},
                {'section': 'grammar', 'is_correct': True},
                {'section': 'grammar', 'is_correct': True},
            ],
        )
        expected = {
            'vocabulary': 'beginner',
            'reading': 'intermediate',
            'grammar': 'advanced',
        }
        for section, difficulty in expected.items():
            with self.subTest(section=section):
                run = self._start(section)
                self.assertTrue(all(
                    question['difficulty'] == difficulty for question in run.questions
                ))

    @patch('apps.lang_quiz.quiz_engine.generate_ai_response')
    def test_vocabulary_course_is_ai_generated_at_diagnostic_difficulty(self, mock_ai):
        mock_ai.return_value = [
            {
                'prompt': f'Advanced academic context question {index}',
                'answer': f'term{index}',
                'skill_focus': 'Academic vocabulary',
                'explanation': 'The term fits the academic context.',
                'next_step': 'Use the term in a formal paragraph.',
                'hints': [f'Hint {level}' for level in range(1, 6)],
                'choices': [f'term{index}', 'option-a', 'option-b', 'option-c', 'option-d'],
            }
            for index in range(10)
        ]
        session = self.client.session
        session.save()
        LanguageQuizRun.objects.create(
            browser_session_key=session.session_key,
            section='diagnostic',
            mode='random',
            finished=True,
            questions=[
                {'section': 'vocabulary', 'is_correct': True},
                {'section': 'vocabulary', 'is_correct': True},
                {'section': 'vocabulary', 'is_correct': True},
            ],
        )

        response = self.client.get(reverse(
            'lang_quiz:start_course', args=['academic-words'],
        ))
        self.assertEqual(response.status_code, 302)
        run = LanguageQuizRun.objects.latest('created_at')
        self.assertTrue(all(question['difficulty'] == 'advanced' for question in run.questions))
        prompt = mock_ai.call_args.kwargs['user_prompt']
        self.assertIn('Difficulty: advanced', prompt)
        self.assertIn('CEFR C1-C2', prompt)
        self.assertIn('Academic Word Builder', prompt)

    def test_correct_missing_answer_removes_it(self):
        original = self._start('vocabulary').questions[0]
        session_key = self.client.session.session_key
        remember_missing(session_key, original)
        stored = MissingLanguageQuestion.objects.get()
        self.assertEqual(stored.choices, original['choices'])
        run = self._start('missing')
        self.assertEqual(run.questions[0]['choices'], original['choices'])
        url = reverse('lang_quiz:quiz_run', args=[run.id])
        self.client.post(url, {'action': 'answer', 'answer': run.questions[0]['answer']})
        self.assertEqual(MissingLanguageQuestion.objects.count(), 0)

    def test_typing_question_is_saved_to_missing_with_empty_choices(self):
        run = self._start('grammar')
        remember_missing(self.client.session.session_key, run.questions[0])
        stored = MissingLanguageQuestion.objects.get()
        self.assertEqual(stored.choices, [])

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
