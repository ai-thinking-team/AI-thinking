import datetime
import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from apps.ai_engine.exceptions import AIEngineError

from . import demo_content, mastery, services
from .models import (
    ConceptMastery,
    ConfidenceCalibration,
    MasteryState,
    Section,
    SectionSession,
    Unit,
    UnitDiagnosticSession,
)
from .state_machine import WorkflowState


def _fake_generate_ai_response(*, system_prompt, user_prompt, response_schema=None, files=None):
    """Routes to canned JSON based on which prompt/schema is being asked
    for, so AI-path tests never make a real network call."""
    if 'セクションを' in system_prompt and '設計' in system_prompt:
        return json.dumps({'sections': [
            {'title': 'AI生成セクション1', 'content': 'AIが生成した内容1'},
            {'title': 'AI生成セクション2', 'content': 'AIが生成した内容2'},
        ]})
    if '練習問題を1問作成' in system_prompt:
        return json.dumps({'problem': 'AIが生成した問題: 2 + 2 は何ですか？'})
    if '採点してください' in system_prompt:
        is_correct = 'CORRECT_ANSWER' in user_prompt
        return json.dumps({'is_correct': is_correct, 'explanation': 'AIによる採点説明です。'})
    if '誤解を診断する専門家' in system_prompt:
        return json.dumps({'question': 'AIによる診断質問です。', 'possible_misconception': '符号ミス'})
    if '自信度が低いと申告' in system_prompt:
        return json.dumps({'question': 'AIによる確認質問です。'})
    if '理解を確認するための質問に回答しました' in system_prompt:
        understanding = 'CLEAR' if 'CLEAR_VERIFICATION_ANSWER' in user_prompt else 'UNCLEAR'
        return json.dumps({'understanding': understanding})
    if 'まだ誤解が残っていないか' in system_prompt:
        return json.dumps({'question': 'AIによるTargeted Teach-Back質問です。'})
    if 'Teach-Back' in system_prompt and 'CLEAR_UNDERSTANDING' in system_prompt:
        evaluation = 'CLEAR_UNDERSTANDING' if 'CLEAR_TEACH_BACK_ANSWER' in user_prompt else 'PARTIAL_UNDERSTANDING'
        follow_up = '' if evaluation == 'CLEAR_UNDERSTANDING' else 'AIによる追質問です。'
        return json.dumps({
            'evaluation': evaluation, 'feedback': 'AIによるTeach-Backフィードバックです。',
            'follow_up_question': follow_up,
        })
    if 'ヒントを段階的に与える' in system_prompt:
        return json.dumps({'content': 'AIによるヒントです。'})
    if 'Transfer Task' in system_prompt:
        return json.dumps({'problem': 'AIが生成した応用問題です。'})
    if '習熟レベルで完了できません' in system_prompt:
        return json.dumps({'recommendation': 'AIによる復習提案です。'})
    raise AssertionError(f'Unexpected system prompt in test: {system_prompt[:50]}')


def _create_section(name='テスト単元'):
    # is_demo=True keeps these tests on the deterministic demo_content path
    # regardless of whether an AI provider happens to be configured in the
    # environment — the AI path gets its own tests further down, with
    # generate_ai_response mocked so nothing ever hits the network.
    unit = Unit.objects.create(name=name, is_demo=True)
    return Section.objects.create(unit=unit, title='テストセクション', content='内容')


def _create_unit_with_sections(name, count, is_demo=True):
    unit = Unit.objects.create(name=name, is_demo=is_demo)
    sections = [
        Section.objects.create(unit=unit, title=f'セクション{i + 1}', content='内容', order=i)
        for i in range(count)
    ]
    return unit, sections


def _correct_answer(section, *, kind='first'):
    _, value = demo_content.build_problem(section, kind=kind)
    return str(value)


class MathRouteTests(TestCase):
    def test_home_loads(self):
        self.assertEqual(self.client.get(reverse('math_quiz:home')).status_code, 200)

    def test_section_quiz_starts_directly_at_first_attempt(self):
        section = _create_section()
        url = reverse('math_quiz:section_quiz', args=[section.id])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, section.unit.name)
        self.assertContains(response, '最初の解答')


class MathWorkflowServiceTests(TestCase):
    def setUp(self):
        self.section = _create_section()
        self.session, _ = services.get_or_create_section_session(
            section=self.section, browser_session_key='browser-key',
        )
        services.ensure_first_problem(session=self.session)

    def test_first_attempt_cannot_be_submitted_twice(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='移項して計算しました', confidence=5,
        )
        with self.assertRaises(ValidationError):
            services.submit_first_attempt(
                session=self.session, answer=answer, reasoning='もう一度', confidence=5,
            )

    def test_correct_and_confident_answer_skips_straight_to_transfer_task(self):
        answer = _correct_answer(self.section, kind='first')
        attempt = services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='移項して計算しました', confidence=5,
        )
        self.assertTrue(attempt.is_correct)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

    def test_correct_but_unsure_answer_requires_verification_then_teach_back(self):
        answer = _correct_answer(self.section, kind='first')
        attempt = services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='移項して計算しました', confidence=2,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.VERIFICATION)
        self.assertTrue(attempt.verification_question)

        with self.assertRaises(ValidationError):
            services.submit_verification(session=self.session, answer='')

        services.submit_verification(session=self.session, answer='両辺が釣り合ったままだからです。')
        self.session.refresh_from_db()
        # Correct-but-unsure (quadrant B) has an uncertainty signal, so it
        # goes through Teach-Back before Transfer — unlike a confident,
        # correct first try (quadrant A), which skips straight to Transfer.
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)

    def test_incorrect_answer_branches_through_diagnosis_hints_revision_and_teach_back(self):
        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        attempt = services.submit_first_attempt(
            session=self.session, answer=wrong_answer, reasoning='勘です', confidence=2,
        )
        self.assertFalse(attempt.is_correct)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.DIAGNOSIS)
        self.assertTrue(attempt.diagnosis_question)

        services.submit_diagnosis(session=self.session, answer='符号を間違えたと思います。')
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.GUIDED_REVISION)

        first_hint = services.ensure_current_hint(session=self.session)
        self.assertEqual(first_hint.level, 1)

        correct_answer = _correct_answer(self.section, kind='first')
        revised = services.submit_revision(
            session=self.session, answer=correct_answer, reasoning='考え直しました', confidence=4,
        )
        self.assertTrue(revised.is_correct)
        self.session.refresh_from_db()
        # A wrong-first-try recovery (quadrant C/D) has a misconception
        # signal, so it also goes through Teach-Back before Transfer.
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)

    def test_hint_level_escalates_and_forces_incorrect_after_level_five(self):
        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        services.submit_first_attempt(
            session=self.session, answer=wrong_answer, reasoning='勘です', confidence=1,
        )
        services.submit_diagnosis(session=self.session, answer='わかりません')

        for expected_level in range(1, 6):
            hint = services.ensure_current_hint(session=self.session)
            self.assertEqual(hint.level, expected_level)
            services.submit_revision(
                session=self.session, answer=wrong_answer, reasoning='まだ違う考え方です', confidence=2,
            )

        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.NEEDS_REVIEW)
        with self.assertRaises(ValidationError):
            services.submit_revision(
                session=self.session, answer=wrong_answer, reasoning='もう一度', confidence=2,
            )

    def test_full_success_path_reaches_mastered_and_completes_course(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='移項して計算しました', confidence=5,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

        services.ensure_transfer_problem(session=self.session)
        transfer_answer = _correct_answer(self.section, kind='transfer')
        transfer = services.submit_transfer_check(
            session=self.session, answer=transfer_answer, reasoning='移項して計算しました', confidence=5,
        )
        self.assertTrue(transfer.is_correct)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.MASTERED)

        message, recommendation = services.build_outcome_summary(session=self.session)
        self.assertIn('Mastered', message)
        self.assertEqual(recommendation, '')

        mastered, total, percent, complete = services.unit_progress(
            unit=self.section.unit, browser_session_key='browser-key',
        )
        self.assertEqual((mastered, total, percent, complete), (1, 1, 100, True))

    def test_restart_always_resets_the_section_session(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='移項して計算しました', confidence=5,
        )
        services.ensure_transfer_problem(session=self.session)
        services.submit_transfer_check(
            session=self.session,
            answer=_correct_answer(self.section, kind='transfer'),
            reasoning='移項して計算しました',
            confidence=5,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.MASTERED)

        restarted = services.restart_for_review(section=self.section, browser_session_key='browser-key')
        self.assertEqual(restarted.current_state, WorkflowState.FIRST_ATTEMPT)
        self.assertFalse(restarted.attempts.exists())


class MathViewFlowTests(TestCase):
    """Walks the flow through the view layer (POST/redirect/GET) instead of
    calling services directly, since the just-completed-vs-restart behavior
    lives in the view, not the service layer."""

    def setUp(self):
        self.section = _create_section()
        self.url = reverse('math_quiz:section_quiz', args=[self.section.id])

    def _post(self, **data):
        return self.client.post(self.url, data, follow=False)

    def test_finishing_shows_outcome_once_before_the_next_visit_restarts(self):
        self.client.get(self.url)
        session = Section.objects.get(id=self.section.id).sessions.get()

        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        self._post(action='first_attempt', answer=wrong_answer, reasoning='勘です', confidence=1)
        self._post(action='diagnosis', answer='わかりません')
        for _ in range(5):
            self._post(action='revision', answer=wrong_answer, reasoning='まだ違います', confidence=2)

        session.refresh_from_db()
        self.assertEqual(session.current_state, WorkflowState.NEEDS_REVIEW)

        # Immediately after finishing, the outcome page shows — not a fresh round.
        response = self.client.get(self.url)
        self.assertContains(response, 'Needs review')

        # The visit after that starts a brand new round.
        old_pk = session.pk
        response = self.client.get(self.url)
        self.assertContains(response, '最初の解答')
        new_session = Section.objects.get(id=self.section.id).sessions.get()
        self.assertNotEqual(old_pk, new_session.pk)


class MathUnitDiagnosticServiceTests(TestCase):
    """The diagnostic quiz now lives at the course level: one problem
    drawn from each section (up to MAX_DIAGNOSTIC_QUESTIONS), its length
    adapting to how consistent the answers are (see
    services._diagnostic_should_stop) instead of a fixed count, taken
    before the section list is shown."""

    def setUp(self):
        self.unit, self.sections = _create_unit_with_sections('診断テスト科目', 3)

    def _answer_current(self, diagnostic, *, correct):
        diagnostic.refresh_from_db()
        item = diagnostic.answers.get(is_correct__isnull=True)
        value = _correct_answer(item.section, kind='diagnostic')
        answer = value if correct else str(int(value) + 1000)
        return services.submit_unit_diagnostic_answer(diagnostic=diagnostic, answer_id=item.id, answer=answer)

    def test_start_creates_only_the_first_question(self):
        diagnostic = services.start_unit_diagnostic(unit=self.unit, browser_session_key='browser-key')
        self.assertEqual(diagnostic.answers.count(), 1)
        self.assertIsNone(diagnostic.completed_at)

    def test_two_consecutive_agreeing_answers_stop_the_quiz_early(self):
        diagnostic = services.start_unit_diagnostic(unit=self.unit, browser_session_key='browser-key')
        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        self.assertIsNone(diagnostic.completed_at)  # 1 answer alone is never enough to stop

        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        # Two agreeing answers (both correct) is a clear enough signal —
        # the quiz stops well under the old fixed count of 3.
        self.assertIsNotNone(diagnostic.completed_at)
        self.assertEqual(diagnostic.answers.count(), 2)

    def test_mixed_answers_continue_past_two_but_never_past_five(self):
        unit, _sections = _create_unit_with_sections('診断長め科目', 6)
        diagnostic = services.start_unit_diagnostic(unit=unit, browser_session_key='browser-key-2')
        # Alternate correct/incorrect so the last-two-agree rule never
        # fires — this must still stop at MAX_DIAGNOSTIC_QUESTIONS (5),
        # never asking a 6th question even though a 6th section exists.
        for i in range(services.MAX_DIAGNOSTIC_QUESTIONS):
            diagnostic.refresh_from_db()
            if diagnostic.completed_at is not None:
                break
            self._answer_current(diagnostic, correct=(i % 2 == 0))
        diagnostic.refresh_from_db()
        self.assertIsNotNone(diagnostic.completed_at)
        self.assertEqual(diagnostic.answers.count(), services.MAX_DIAGNOSTIC_QUESTIONS)

    def test_answers_are_graded_and_session_completes(self):
        diagnostic = services.start_unit_diagnostic(unit=self.unit, browser_session_key='browser-key')
        first_item = diagnostic.answers.get()
        self._answer_current(diagnostic, correct=False)  # wrong
        diagnostic.refresh_from_db()
        self.assertIsNone(diagnostic.completed_at)

        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        self.assertIsNone(diagnostic.completed_at)  # wrong, correct — still mixed, one more question

        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        # correct, correct agree — stops at 3, having started with 1 wrong.
        self.assertIsNotNone(diagnostic.completed_at)

        result = services.build_unit_diagnostic_result(diagnostic=diagnostic)
        self.assertEqual(result['correct_count'], 2)
        self.assertEqual(result['total'], 3)
        self.assertEqual([s.id for s in result['recommended_sections']], [first_item.section_id])

    def test_diagnostic_never_repeats_a_problem_text_within_one_session(self):
        unit, _sections = _create_unit_with_sections('診断重複テスト科目', 5, is_demo=False)
        diagnostic = services.start_unit_diagnostic(unit=unit, browser_session_key='browser-key-3')
        for i in range(services.MAX_DIAGNOSTIC_QUESTIONS):
            diagnostic.refresh_from_db()
            if diagnostic.completed_at is not None:
                break
            self._answer_current(diagnostic, correct=(i % 2 == 0))
        problems = list(diagnostic.answers.values_list('problem', flat=True))
        self.assertEqual(len(problems), len(set(problems)))

    def test_cannot_answer_the_same_question_twice(self):
        diagnostic = services.start_unit_diagnostic(unit=self.unit, browser_session_key='browser-key')
        item = diagnostic.answers.first()
        correct = _correct_answer(item.section, kind='diagnostic')
        services.submit_unit_diagnostic_answer(diagnostic=diagnostic, answer_id=item.id, answer=correct)
        with self.assertRaises(ValidationError):
            services.submit_unit_diagnostic_answer(diagnostic=diagnostic, answer_id=item.id, answer=correct)

    def test_get_or_create_does_not_reset_an_in_progress_session(self):
        first = services.start_unit_diagnostic(unit=self.unit, browser_session_key='browser-key')
        fetched = services.get_or_create_unit_diagnostic(unit=self.unit, browser_session_key='browser-key')
        self.assertEqual(first.pk, fetched.pk)


class MathUnitDiagnosticViewTests(TestCase):
    def setUp(self):
        self.unit, self.sections = _create_unit_with_sections('診断ビュー科目', 3)
        self.detail_url = reverse('math_quiz:unit_detail', args=[self.unit.id])
        self.diag_url = reverse('math_quiz:unit_diagnostic', args=[self.unit.id])

    def test_entering_unit_redirects_to_diagnostic(self):
        response = self.client.get(self.detail_url)
        self.assertRedirects(response, self.diag_url)

    def _complete_diagnostic_with_all_correct(self):
        # The quiz is adaptive (see services._diagnostic_should_stop) —
        # its length isn't known upfront, so answer whatever is currently
        # pending until completed_at is set, rather than looping over a
        # pre-captured (and now stale) list of questions.
        diagnostic = UnitDiagnosticSession.objects.get(unit=self.unit)
        while diagnostic.completed_at is None:
            item = diagnostic.answers.get(is_correct__isnull=True)
            answer = _correct_answer(item.section, kind='diagnostic')
            self.client.post(self.diag_url, {'action': 'answer', 'answer_id': item.id, 'answer': answer})
            diagnostic.refresh_from_db()

    def test_completing_diagnostic_then_continuing_shows_sections(self):
        self.client.get(self.detail_url)  # creates the diagnostic session
        self._complete_diagnostic_with_all_correct()

        response = self.client.get(self.diag_url)
        self.assertContains(response, '診断結果')

        response = self.client.post(self.diag_url, {'action': 'continue'}, follow=True)
        self.assertContains(response, self.sections[0].title)

        # Once completed, revisiting the unit never shows the diagnostic
        # quiz again — completed_at (already-existing data) is the single
        # source of truth, and the session is never reset or recreated.
        old_pk = UnitDiagnosticSession.objects.get(unit=self.unit).pk
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sections[0].title)
        new_pk = UnitDiagnosticSession.objects.get(unit=self.unit).pk
        self.assertEqual(old_pk, new_pk)

    def test_revisiting_a_completed_unit_never_redirects_to_diagnostic_again(self):
        self.client.get(self.detail_url)
        self._complete_diagnostic_with_all_correct()
        self.client.post(self.diag_url, {'action': 'continue'})

        # Multiple later visits (e.g. after navigating away and back) all
        # go straight to the section list — not just the one right after
        # finishing.
        for _ in range(3):
            response = self.client.get(self.detail_url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, self.sections[0].title)


class MathSectionProfileTests(TestCase):
    def test_known_subject_gets_its_curated_textbook_order(self):
        sections = demo_content.build_sections('一次方程式')
        self.assertEqual(
            [s['title'] for s in sections],
            ['基本形を確認する', '文章題に挑戦する', '発展問題に挑戦する'],
        )

    def test_another_known_subject_has_a_different_progression(self):
        sections = demo_content.build_sections('フーリエ変換')
        self.assertEqual(
            [s['title'] for s in sections],
            ['基本の計算', '熱方程式への応用', '波動方程式への応用'],
        )

    def test_unknown_subject_falls_back_to_the_generic_template(self):
        sections = demo_content.build_sections('聞いたことのない科目')
        self.assertEqual(
            [s['title'] for s in sections],
            ['定義・公式を確認する', '例題に取り組む', '発展問題に挑戦する'],
        )

    def test_curriculum_covers_all_four_school_levels(self):
        # One representative unit per school level — spot-checks that the
        # curated catalogue actually spans 小学校〜大学, not just high
        # school math.
        for unit_name in ('分数の計算', '連立方程式', '三角関数', '線形代数学'):
            self.assertIn(unit_name, demo_content.UNIT_SECTION_PROFILES)

    def test_every_curated_profile_has_well_formed_sections(self):
        for unit_name, template in demo_content.UNIT_SECTION_PROFILES.items():
            with self.subTest(unit=unit_name):
                self.assertGreaterEqual(len(template), 2)
                for title, content in template:
                    self.assertTrue(title.strip())
                    self.assertTrue(content.strip())

    def test_curated_catalogue_stays_at_least_this_broad(self):
        # Regression floor, not an exact count — catches an accidental
        # mass-deletion of entries. (A duplicate dict key would silently
        # drop content without raising anything; this can't detect that
        # directly, but a shrinking count is the visible symptom.)
        self.assertGreaterEqual(len(demo_content.UNIT_SECTION_PROFILES), 40)


class MathWordProblemTests(TestCase):
    def setUp(self):
        self.unit, self.sections = _create_unit_with_sections('一次方程式', 3)
        # matches the curated profile's section titles
        for section, title in zip(self.sections, ['基本形を確認する', '文章題に挑戦する', '発展問題に挑戦する']):
            section.title = title
            section.save(update_fields=('title',))
        self.word_section = self.sections[1]
        self.plain_section = self.sections[0]

    def test_word_problem_section_is_phrased_as_a_story_not_a_bare_equation(self):
        problem, value = demo_content.build_problem(self.word_section, kind='first')
        self.assertIn('ノート', problem)
        self.assertIsInstance(value, int)
        self.assertGreater(value, 0)  # word problems use positive, human-friendly numbers

    def test_plain_section_still_gets_a_bare_equation(self):
        problem, _ = demo_content.build_problem(self.plain_section, kind='first')
        self.assertIn('x', problem)
        self.assertIn('=', problem)
        self.assertNotIn('ノート', problem)

    def test_hint_numbers_agree_with_the_word_problem(self):
        problem, value = demo_content.build_problem(self.word_section, kind='first')
        hint = demo_content.build_hint(section=self.word_section, level=5, kind='first')
        self.assertIn(str(value), hint)

    def test_word_problem_is_graded_like_any_other_numeric_answer(self):
        session, _ = services.get_or_create_section_session(
            section=self.word_section, browser_session_key='browser-key',
        )
        services.ensure_first_problem(session=session)
        _, value = demo_content.build_problem(self.word_section, kind='first')
        attempt = services.submit_first_attempt(
            session=session, answer=f'x = {value}', reasoning='式を立てて解きました', confidence=5,
        )
        self.assertTrue(attempt.is_correct)


class MathMistakesTests(TestCase):
    """Drives everything through the test client (rather than calling
    services with a hardcoded browser key directly) so the session key
    used to look up mistakes matches the one the views actually see."""

    def setUp(self):
        self.section = _create_section(name='復習テスト単元')
        self.url = reverse('math_quiz:section_quiz', args=[self.section.id])

    def _post(self, **data):
        return self.client.post(self.url, data, follow=False)

    def _fail_to_needs_review(self):
        self.client.get(self.url)  # establishes the test client's session
        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        self._post(action='first_attempt', answer=wrong_answer, reasoning='勘です', confidence=1)
        self._post(action='diagnosis', answer='わかりません')
        for _ in range(5):
            self._post(action='revision', answer=wrong_answer, reasoning='まだ違います', confidence=2)

    def test_no_mistakes_before_anything_fails(self):
        self.client.get(self.url)
        key = self.client.session.session_key
        self.assertEqual(services.list_mistakes(browser_session_key=key), [])

    def test_a_needs_review_section_appears_with_its_last_wrong_problem(self):
        self._fail_to_needs_review()
        key = self.client.session.session_key
        mistakes = services.list_mistakes(browser_session_key=key)
        self.assertEqual(len(mistakes), 1)
        self.assertEqual(mistakes[0]['section'], self.section)
        self.assertEqual(mistakes[0]['unit'], self.section.unit)
        self.assertTrue(mistakes[0]['problem'])

    def test_mistakes_page_lists_it_and_home_shows_the_count_badge(self):
        self._fail_to_needs_review()

        response = self.client.get(reverse('math_quiz:mistakes'))
        self.assertContains(response, self.section.title)

        home_response = self.client.get(reverse('math_quiz:home'))
        self.assertContains(home_response, '間違えた問題')

    def test_mistakes_page_shows_misconception_and_reasons_from_the_learner_model(self):
        self._fail_to_needs_review()
        key = self.client.session.session_key
        mistakes = services.list_mistakes(browser_session_key=key)
        self.assertEqual(len(mistakes), 1)
        self.assertTrue(mistakes[0]['misconception_type'])
        self.assertTrue(mistakes[0]['reasons'])

        response = self.client.get(reverse('math_quiz:mistakes'))
        self.assertContains(response, '推定される誤解')
        self.assertContains(response, mistakes[0]['reasons'][0])

    def test_resolving_via_mistakes_page_button_starts_a_fresh_round_immediately(self):
        self._fail_to_needs_review()
        # The mistakes page's "解きなおす" button posts action=reset directly,
        # so — unlike a plain revisit — one click is enough to get a fresh problem.
        response = self.client.post(self.url, {'action': 'reset'}, follow=True)
        self.assertContains(response, '最初の解答')
        key = self.client.session.session_key
        self.assertEqual(services.list_mistakes(browser_session_key=key), [])


class MathAddUnitViewTests(TestCase):
    """add_unit accepts any number of reference files — every file's bytes
    reach generate_sections for analysis, but only the first is kept as
    the course's downloadable reference file (Unit.file stays a single
    FileField; see views.add_unit)."""

    def setUp(self):
        self.url = reverse('math_quiz:add_unit')

    def _upload(self, name, content=b'dummy content', content_type='application/pdf'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, content, content_type=content_type)

    def test_single_file_upload_still_works(self):
        response = self.client.post(self.url, {
            'name': '単一ファイル科目', 'file': self._upload('a.pdf'),
        })
        unit = Unit.objects.get(name='単一ファイル科目')
        self.assertRedirects(response, reverse('math_quiz:unit_detail', args=[unit.id]), fetch_redirect_response=False)
        self.assertTrue(unit.file.name.split('/')[-1].startswith('a') and unit.file.name.endswith('.pdf'))
        self.assertTrue(unit.sections.exists())

    def test_multiple_files_all_reach_generate_sections(self):
        captured = {}

        def fake_generate_sections(unit, name, files=None):
            captured['files'] = files or []
            Section.objects.create(unit=unit, title='セクション1', content='内容', order=0)

        with patch('apps.math_quiz.views.services.generate_sections', side_effect=fake_generate_sections):
            response = self.client.post(self.url, {
                'name': '複数ファイル科目',
                'file': [self._upload('a.pdf'), self._upload('b.png', content_type='image/png')],
            })

        unit = Unit.objects.get(name='複数ファイル科目')
        self.assertRedirects(response, reverse('math_quiz:unit_detail', args=[unit.id]), fetch_redirect_response=False)
        # Both files' contents were handed to section generation...
        self.assertEqual(len(captured['files']), 2)
        self.assertEqual({mime for _bytes, mime in captured['files']}, {'application/pdf', 'image/png'})
        # ...but only the first is kept as the course's reference file.
        self.assertTrue(unit.file.name.split('/')[-1].startswith('a') and unit.file.name.endswith('.pdf'))

    def test_no_file_upload_still_works(self):
        response = self.client.post(self.url, {'name': 'ファイルなし科目'})
        unit = Unit.objects.get(name='ファイルなし科目')
        self.assertRedirects(response, reverse('math_quiz:unit_detail', args=[unit.id]), fetch_redirect_response=False)
        self.assertFalse(unit.file)


class MathAIGenerationTests(TestCase):
    """AI generation is only reachable for non-demo units, and only while
    a provider is configured — both are mocked here so nothing ever hits
    the network, matching the pattern used before this app had a
    deterministic demo_content fallback to lean on."""

    def setUp(self):
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.mock_configured = configured_patcher.start()
        self.addCleanup(configured_patcher.stop)

        response_patcher = patch(
            'apps.math_quiz.services.generate_ai_response', side_effect=_fake_generate_ai_response,
        )
        self.mock_response = response_patcher.start()
        self.addCleanup(response_patcher.stop)

        self.unit = Unit.objects.create(name='AIテスト単元', is_demo=False)

    def test_generate_sections_uses_ai_when_configured(self):
        services.generate_sections(self.unit, self.unit.name)
        titles = list(self.unit.sections.order_by('order').values_list('title', flat=True))
        self.assertEqual(titles, ['AI生成セクション1', 'AI生成セクション2'])

    def test_generate_sections_falls_back_to_demo_content_on_ai_failure(self):
        self.mock_response.side_effect = AIEngineError('boom')
        services.generate_sections(self.unit, self.unit.name)
        titles = list(self.unit.sections.order_by('order').values_list('title', flat=True))
        self.assertEqual(titles, [title for title, _ in demo_content.DEFAULT_SECTION_TEMPLATE])

    def test_generate_sections_never_leaves_zero_sections_on_an_unexpected_error_type(self):
        """Regression test: a course was found in production with zero
        sections because an exception type outside (AIEngineError,
        JSONDecodeError, KeyError) — e.g. a raw TimeoutError — escaped
        the narrow except clause, leaving the Unit row (already
        committed by the view) orphaned with no sections and no retry
        path. The AI-attempt catch is now a deliberately broad
        `except Exception` so this can't happen again."""
        self.mock_response.side_effect = TimeoutError('read timed out')
        services.generate_sections(self.unit, self.unit.name)
        self.assertGreater(self.unit.sections.count(), 0)

    def test_generate_sections_falls_back_when_ai_returns_an_empty_or_malformed_list(self):
        """A "successful" AI call that returns no usable sections (an
        empty list, or a list of strings instead of {title, content}
        objects) must also fall back — the response not raising doesn't
        mean it's usable."""
        self.mock_response.side_effect = None
        self.mock_response.return_value = json.dumps({'sections': []})
        services.generate_sections(self.unit, self.unit.name)
        titles = list(self.unit.sections.order_by('order').values_list('title', flat=True))
        self.assertEqual(titles, [title for title, _ in demo_content.DEFAULT_SECTION_TEMPLATE])

    def test_demo_unit_never_calls_ai_even_when_configured(self):
        demo_unit = Unit.objects.create(name='デモのまま単元', is_demo=True)
        services.generate_sections(demo_unit, demo_unit.name)
        self.mock_response.assert_not_called()

    def test_first_problem_and_judge_use_ai(self):
        section = Section.objects.create(unit=self.unit, title='セクションA', content='内容')
        session, _ = services.get_or_create_section_session(section=section, browser_session_key='ai-browser')
        problem = services.ensure_first_problem(session=session)
        self.assertIn('AIが生成した問題', problem)

        attempt = services.submit_first_attempt(
            session=session, answer='CORRECT_ANSWER', reasoning='AIに解かせました', confidence=5,
        )
        self.assertTrue(attempt.is_correct)
        self.assertEqual(attempt.explanation, 'AIによる採点説明です。')

    def test_first_problem_falls_back_when_ai_returns_an_empty_problem(self):
        section = Section.objects.create(unit=self.unit, title='セクションE', content='内容')
        session, _ = services.get_or_create_section_session(section=section, browser_session_key='ai-browser-5')
        self.mock_response.side_effect = None
        self.mock_response.return_value = json.dumps({'problem': '  '})
        problem = services.ensure_first_problem(session=session)
        demo_problem, _ = demo_content.build_problem(section, kind='first')
        self.assertEqual(problem, demo_problem)

    def test_wrong_answer_gets_ai_generated_diagnosis_then_ai_hint(self):
        section = Section.objects.create(unit=self.unit, title='セクションC', content='内容')
        session, _ = services.get_or_create_section_session(section=section, browser_session_key='ai-browser-3')
        services.ensure_first_problem(session=session)

        attempt = services.submit_first_attempt(
            session=session, answer='wrong answer', reasoning='勘です', confidence=2,
        )
        self.assertFalse(attempt.is_correct)
        self.assertEqual(attempt.diagnosis_question, 'AIによる診断質問です。')

        services.submit_diagnosis(session=session, answer='わかりません')
        hint = services.ensure_current_hint(session=session)
        self.assertEqual(hint.content, 'AIによるヒントです。')

    def test_judge_failure_reports_error_without_falling_back_to_demo_grading(self):
        section = Section.objects.create(unit=self.unit, title='セクションB', content='内容')
        session, _ = services.get_or_create_section_session(section=section, browser_session_key='ai-browser-2')
        services.ensure_first_problem(session=session)

        def raise_on_judge(*, system_prompt, user_prompt, response_schema=None, files=None):
            if '採点してください' in system_prompt:
                raise AIEngineError('judge unavailable')
            return _fake_generate_ai_response(
                system_prompt=system_prompt, user_prompt=user_prompt, response_schema=response_schema,
            )

        self.mock_response.side_effect = raise_on_judge
        attempt = services.submit_first_attempt(
            session=session, answer='CORRECT_ANSWER', reasoning='解きました', confidence=5,
        )
        # A failed AI judge call must never silently fall back to demo
        # grading (that would compare against a completely unrelated
        # equation) — it reports the failure instead.
        self.assertIsNone(attempt.is_correct)
        self.assertIn('採点に失敗しました', attempt.explanation)

    def test_when_ai_generation_itself_falls_back_to_demo_judging_also_uses_demo(self):
        """If AI is configured but every call fails, problem generation
        silently falls back to demo_content — and judging/hints must
        recognize that and use demo grading too, instead of retrying a
        doomed AI call and reporting a hard failure for what is actually
        a perfectly gradable demo equation."""
        section = Section.objects.create(unit=self.unit, title='セクションD', content='内容')
        self.mock_response.side_effect = AIEngineError('provider unavailable')

        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='ai-browser-4',
        )
        problem = services.ensure_first_problem(session=session)
        demo_problem, demo_value = demo_content.build_problem(section, kind='first')
        self.assertEqual(problem, demo_problem)

        attempt = services.submit_first_attempt(
            session=session, answer=str(demo_value), reasoning='計算しました', confidence=5,
        )
        self.assertTrue(attempt.is_correct)
        self.assertNotIn('採点に失敗しました', attempt.explanation)


class MathAIFallbackCatalogTests(TestCase):
    """AI_FALLBACK_PROBLEMS: subject-matched fallback content used when AI
    generation fails or produces something off-topic — see
    demo_content.build_problem / looks_like_subject. Regression coverage
    for the reported bug where a Fourier-transform course showed an
    unrelated linear equation ("6x + 1 = -47")."""

    def test_catalog_keys_match_curated_subjects_and_have_two_problems_each(self):
        for name in demo_content.AI_FALLBACK_PROBLEMS:
            self.assertIn(name, demo_content.UNIT_SECTION_PROFILES)
        for name, catalog in demo_content.AI_FALLBACK_PROBLEMS.items():
            self.assertGreaterEqual(len(catalog['keywords']), 1, name)
            self.assertEqual(len(catalog['problems']), 2, name)

    def test_every_answer_is_extractable_from_its_own_stringified_form(self):
        for name, catalog in demo_content.AI_FALLBACK_PROBLEMS.items():
            for entry in catalog['problems']:
                numbers = demo_content._extract_numbers(str(entry['answer']))
                self.assertIn(entry['answer'], numbers, f'{name}: {entry["problem"]}')

    def test_build_problem_uses_catalog_for_a_matching_subject(self):
        unit = Unit.objects.create(name='フーリエ変換', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        problem, answer = demo_content.build_problem(section, kind='first')
        catalog = demo_content.AI_FALLBACK_PROBLEMS['フーリエ変換']['problems']
        matching = [e for e in catalog if e['problem'] == problem]
        self.assertEqual(len(matching), 1)
        self.assertEqual(answer, matching[0]['answer'])

    def test_build_problem_falls_back_to_linear_equation_for_unrecognized_subject(self):
        unit = Unit.objects.create(name='存在しない科目XYZ', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        problem, _ = demo_content.build_problem(section, kind='first')
        self.assertRegex(problem, r'^-?\d+x [+-] \d+ = -?\d+$')

    def test_demo_unit_names_never_collide_with_the_catalog(self):
        self.assertNotIn('一次方程式（サンプル）', demo_content.AI_FALLBACK_PROBLEMS)
        self.assertNotIn('デモ単元（AI不要）', demo_content.AI_FALLBACK_PROBLEMS)

    def test_judge_answer_uses_subject_specific_notes(self):
        unit = Unit.objects.create(name='群論', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        _, answer = demo_content.build_problem(section, kind='first')
        correct_note, wrong_note = demo_content.fallback_notes(section, kind='first')
        self.assertTrue(correct_note)
        self.assertTrue(wrong_note)

        is_correct, explanation = demo_content.judge_answer(
            answer=str(answer), expected_value=answer,
            correct_note=correct_note, wrong_note=wrong_note,
        )
        self.assertTrue(is_correct)
        self.assertIn(correct_note, explanation)

        wrong_answer = str(answer + 1000)
        is_correct, explanation = demo_content.judge_answer(
            answer=wrong_answer, expected_value=answer,
            correct_note=correct_note, wrong_note=wrong_note,
        )
        self.assertFalse(is_correct)
        self.assertIn(wrong_note, explanation)

    def test_diagnosis_verification_hint_avoid_equation_specific_wording_when_fallback_active(self):
        unit = Unit.objects.create(name='群論', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        question, _misconception = demo_content.diagnosis_question(section, confidence=2)
        self.assertNotIn('移項', question)
        verification = demo_content.verification_question(section)
        self.assertNotIn('両辺', verification)
        for level in range(1, 6):
            hint = demo_content.build_hint(section=section, level=level, kind='first')
            self.assertNotIn('移項', hint)


class MathAIFallbackGenerationTests(TestCase):
    """services._generate_problem falling back to the subject-matched
    catalog — both when the AI call fails outright, and when it succeeds
    but returns something unrelated to the course (see
    demo_content.looks_like_subject). Same non-demo + mocked AI pattern as
    MathAIGenerationTests."""

    def setUp(self):
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.mock_configured = configured_patcher.start()
        self.addCleanup(configured_patcher.stop)
        response_patcher = patch('apps.math_quiz.services.generate_ai_response')
        self.mock_response = response_patcher.start()
        self.addCleanup(response_patcher.stop)

        self.unit = Unit.objects.create(name='フーリエ変換', is_demo=False)
        self.section = Section.objects.create(unit=self.unit, title='変数分離法', content='内容')

    def _catalog_problem_texts(self):
        return [e['problem'] for e in demo_content.AI_FALLBACK_PROBLEMS['フーリエ変換']['problems']]

    def test_ai_failure_falls_back_to_subject_matched_problem(self):
        self.mock_response.side_effect = AIEngineError('rate limited')
        problem = services._generate_problem(section=self.section, kind='first')
        self.assertIn(problem, self._catalog_problem_texts())

    def test_ai_success_but_off_topic_falls_back_to_subject_matched_problem(self):
        # This is the exact reported bug reproduced directly: AI call
        # "succeeds" but hands back an unrelated linear equation.
        self.mock_response.return_value = json.dumps({'problem': '6x + 1 = -47'})
        problem = services._generate_problem(section=self.section, kind='first')
        self.assertIn(problem, self._catalog_problem_texts())

    def test_ai_success_with_on_topic_content_is_used_as_is(self):
        on_topic = 'フーリエ変換を用いてこの信号の周波数成分を求めなさい。'
        self.mock_response.return_value = json.dumps({'problem': on_topic})
        problem = services._generate_problem(section=self.section, kind='first')
        self.assertEqual(problem, on_topic)


class MathProblemDedupTests(TestCase):
    """Exact-text duplicate avoidance across problem-generation call sites
    — see demo_content.build_unique_problem / build_problem's `salt` and
    services._generate_problem's `exclude`. Regression coverage for the
    AI fallback catalog's small 2-entry-per-subject pool making a
    first/transfer or diagnostic collision likely without this."""

    def test_build_unique_problem_finds_a_different_fallback_catalog_entry(self):
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        problem0, _value0 = demo_content.build_problem(section, kind='first', salt=0)
        unique_problem, _value = demo_content.build_unique_problem(
            section, kind='first', exclude={problem0},
        )
        self.assertNotEqual(unique_problem, problem0)

    def test_build_unique_problem_finds_a_different_linear_equation(self):
        section = _create_section(name='一次方程式重複テスト単元')
        problem0, _value0 = demo_content.build_problem(section, kind='first', salt=0)
        unique_problem, _value = demo_content.build_unique_problem(
            section, kind='first', exclude={problem0},
        )
        self.assertNotEqual(unique_problem, problem0)

    def test_first_and_transfer_never_collide_within_one_session(self):
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='dedup-browser',
        )
        first_problem = services.ensure_first_problem(session=session)
        session.first_problem = first_problem
        transfer_problem = services.ensure_transfer_problem(session=session)
        self.assertNotEqual(first_problem, transfer_problem)

    def test_generate_problem_ai_mode_rejects_a_repeated_ai_output(self):
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch('apps.math_quiz.services.generate_ai_response')
        self.addCleanup(response_patcher.stop)
        mock_response = response_patcher.start()

        unit = Unit.objects.create(name='群論', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        excluded = 'すでに出題済みの問題文'
        mock_response.return_value = json.dumps({'problem': excluded})

        problem = services._generate_problem(section=section, kind='first', exclude={excluded})
        self.assertNotEqual(problem, excluded)
        self.assertEqual(mock_response.call_count, 2)  # retried once, still matched exclude, fell through

    def test_resolve_fallback_grades_correctly_for_a_non_zero_salt_variant(self):
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        problem0, _ = demo_content.build_problem(section, kind='first', salt=0)
        target_salt = next(
            s for s in range(1, demo_content.MAX_PROBLEM_DEDUP_ATTEMPTS)
            if demo_content.build_problem(section, kind='first', salt=s)[0] != problem0
        )
        problem, value = demo_content.build_problem(section, kind='first', salt=target_salt)
        is_correct, explanation, _quality = services._judge(
            section=section, problem=problem, answer=str(value), kind='first',
        )
        self.assertTrue(is_correct)
        self.assertNotIn('採点に失敗しました', explanation)


class MathConceptMasteryTests(TestCase):
    """ConceptMastery is the durable learner model — unlike SectionSession,
    it is never deleted by reset_section_session, and accumulates evidence
    (confidence calibration, hint dependency, misconception estimates,
    transfer results) across attempt cycles."""

    def setUp(self):
        self.section = _create_section(name='学習者モデルテスト単元')
        self.session, _ = services.get_or_create_section_session(
            section=self.section, browser_session_key='mastery-browser',
        )
        services.ensure_first_problem(session=self.session)

    def _mastery(self, *, browser_session_key='mastery-browser', section=None):
        return services.get_concept_mastery(
            section=section or self.section, browser_session_key=browser_session_key,
        )

    def test_correct_high_confidence_is_well_calibrated_and_skips_to_transfer(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='計算しました', confidence=5,
        )
        record = self._mastery()
        self.assertEqual(record.confidence_calibration, ConfidenceCalibration.WELL_CALIBRATED)
        self.assertEqual(record.attempt_count, 1)
        self.assertEqual(record.mastery_state, MasteryState.IN_PROGRESS)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

    def test_correct_low_confidence_is_underconfident(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='たぶんこうだと思います', confidence=1,
        )
        self.assertEqual(self._mastery().confidence_calibration, ConfidenceCalibration.UNDERCONFIDENT)

    def test_incorrect_high_confidence_is_overconfident(self):
        wrong = str(int(_correct_answer(self.section, kind='first')) + 1000)
        services.submit_first_attempt(
            session=self.session, answer=wrong, reasoning='絶対にこうです', confidence=5,
        )
        self.assertEqual(self._mastery().confidence_calibration, ConfidenceCalibration.OVERCONFIDENT)

    def test_confidence_quadrant_changes_diagnosis_question_and_misconception_probability(self):
        """Wrong+confident (quadrant C) should look more like a genuine
        misconception than wrong+unsure (quadrant D): a higher estimated
        probability and a different diagnostic question."""
        wrong = str(int(_correct_answer(self.section, kind='first')) + 1000)
        high_conf_attempt = services.submit_first_attempt(
            session=self.session, answer=wrong, reasoning='絶対にこうです', confidence=5,
        )

        section2 = _create_section(name='学習者モデルテスト単元2')
        session2, _ = services.get_or_create_section_session(
            section=section2, browser_session_key='mastery-browser-2',
        )
        services.ensure_first_problem(session=session2)
        wrong2 = str(int(_correct_answer(section2, kind='first')) + 1000)
        low_conf_attempt = services.submit_first_attempt(
            session=session2, answer=wrong2, reasoning='わかりません', confidence=1,
        )

        self.assertGreater(high_conf_attempt.misconception_probability, low_conf_attempt.misconception_probability)
        self.assertNotEqual(high_conf_attempt.diagnosis_question, low_conf_attempt.diagnosis_question)

    def test_hint_progression_updates_hint_count_and_forces_needs_review_at_level_five(self):
        wrong = str(int(_correct_answer(self.section, kind='first')) + 1000)
        services.submit_first_attempt(session=self.session, answer=wrong, reasoning='勘です', confidence=2)
        services.submit_diagnosis(session=self.session, answer='わかりません')

        for expected_level in range(1, 6):
            hint = services.ensure_current_hint(session=self.session)
            self.assertEqual(hint.level, expected_level)
            services.submit_revision(
                session=self.session, answer=wrong, reasoning='まだ違う考え方です', confidence=2,
            )
            record = self._mastery()
            self.assertEqual(record.hint_count, expected_level)

        record = self._mastery()
        self.assertEqual(record.mastery_state, MasteryState.NEEDS_REVIEW)

    def test_successful_revision_raises_knowledge_score(self):
        wrong = str(int(_correct_answer(self.section, kind='first')) + 1000)
        services.submit_first_attempt(session=self.session, answer=wrong, reasoning='勘です', confidence=2)
        services.submit_diagnosis(session=self.session, answer='わかりません')
        before = self._mastery().knowledge_score

        correct = _correct_answer(self.section, kind='first')
        services.submit_revision(
            session=self.session, answer=correct, reasoning='考え直しました', confidence=4,
        )
        after = self._mastery()
        self.assertGreater(after.knowledge_score, before)
        self.assertEqual(after.confidence_calibration, ConfidenceCalibration.WELL_CALIBRATED)

    def test_transfer_success_sets_mastered_state_and_review_due_at(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(session=self.session, answer=answer, reasoning='計算しました', confidence=5)
        services.ensure_transfer_problem(session=self.session)
        transfer_answer = _correct_answer(self.section, kind='transfer')
        services.submit_transfer_check(
            session=self.session, answer=transfer_answer, reasoning='計算しました', confidence=5,
        )
        record = self._mastery()
        self.assertEqual(record.mastery_state, MasteryState.MASTERED)
        self.assertEqual(record.successful_transfer_count, 1)
        self.assertIsNotNone(record.last_mastered_at)
        self.assertIsNotNone(record.review_due_at)
        self.assertGreater(record.mastery_score, 0)

    def test_transfer_failure_sets_needs_review_state(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(session=self.session, answer=answer, reasoning='計算しました', confidence=5)
        services.ensure_transfer_problem(session=self.session)
        wrong_transfer = str(int(_correct_answer(self.section, kind='transfer')) + 1000)
        services.submit_transfer_check(
            session=self.session, answer=wrong_transfer, reasoning='計算しました', confidence=5,
        )
        record = self._mastery()
        self.assertEqual(record.mastery_state, MasteryState.NEEDS_REVIEW)
        self.assertEqual(record.failed_transfer_count, 1)

    def test_concept_mastery_survives_reset_unlike_section_session(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(session=self.session, answer=answer, reasoning='計算しました', confidence=5)
        before = self._mastery()
        self.assertEqual(before.attempt_count, 1)

        services.reset_section_session(section=self.section, browser_session_key='mastery-browser')
        self.assertFalse(SectionSession.objects.filter(section=self.section).exists())

        after = self._mastery()
        self.assertEqual(after.pk, before.pk)
        self.assertEqual(after.attempt_count, 1)

    def test_get_concept_mastery_is_safe_when_no_record_exists_yet(self):
        # Simulates pre-existing SectionSession/Attempt data from before
        # ConceptMastery existed — get_or_create must not error.
        other_section = _create_section(name='既存データ互換テスト単元')
        record = services.get_concept_mastery(section=other_section, browser_session_key='legacy-browser')
        self.assertEqual(record.mastery_state, MasteryState.NOT_STARTED)
        self.assertEqual(record.attempt_count, 0)


CLEAR_TEACH_BACK_RESPONSE = (
    '両辺から同じ数を引いて移項し、符号に気をつけながらxだけの形に整理して計算しました。'
)
PARTIAL_TEACH_BACK_RESPONSE = 'よくわかりません。'


class MathTeachBackTests(TestCase):
    """Adaptive Teach-Back: Level 0 (skipped), Level 1 (Short), Level 2
    (Targeted) — see mastery.decide_teach_back_level /
    mastery.heuristic_verification_signal. A confident, correct first try
    (quadrant A) still skips it entirely, as before P1's reactivation."""

    def setUp(self):
        self.section = _create_section(name='Teach-Backテスト単元')
        self.session, _ = services.get_or_create_section_session(
            section=self.section, browser_session_key='teachback-browser',
        )
        services.ensure_first_problem(session=self.session)

    def _reach_teach_back_via_verification(self):
        """A short, generic Verification answer is confidently 'unclear'
        via the heuristic (no AI needed) — see
        mastery.heuristic_verification_signal — so this always lands on
        Level 1 (Short) Teach-Back."""
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='移項して計算しました', confidence=2,
        )
        services.submit_verification(session=self.session, answer='わかりません')
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)
        self.assertEqual(self.session.teach_back_level, 'SHORT')

    def test_confident_correct_first_try_skips_teach_back_entirely(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer, reasoning='移項して計算しました', confidence=5,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

    def test_verification_with_clear_understanding_skips_teach_back(self):
        answer = _correct_answer(self.section, kind='first')
        services.submit_first_attempt(
            session=self.session, answer=answer,
            reasoning='両辺から同じ数を引いて移項し、符号に注意しながらxだけの形に整理して計算しました',
            confidence=2,
        )
        services.submit_verification(
            session=self.session,
            answer='両辺に同じ操作をしても方程式のつり合いは変わらないからです、移項の考え方と同じです',
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)
        self.assertEqual(self.session.teach_back_level, '')

    def test_clear_teach_back_answer_advances_to_transfer_and_updates_mastery(self):
        self._reach_teach_back_via_verification()
        teach_back = services.submit_teach_back(session=self.session, answer=CLEAR_TEACH_BACK_RESPONSE)
        self.assertEqual(teach_back.evaluation, 'CLEAR_UNDERSTANDING')
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)
        record = services.get_concept_mastery(section=self.section, browser_session_key='teachback-browser')
        self.assertEqual(record.teach_back_score, 100)

    def test_partial_teach_back_answer_gets_one_follow_up_round(self):
        self._reach_teach_back_via_verification()
        teach_back = services.submit_teach_back(session=self.session, answer=PARTIAL_TEACH_BACK_RESPONSE)
        self.assertEqual(teach_back.evaluation, 'PARTIAL_UNDERSTANDING')
        self.assertTrue(teach_back.follow_up_question)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)
        record = services.get_concept_mastery(section=self.section, browser_session_key='teachback-browser')
        self.assertEqual(record.teach_back_score, 50)

        current = services.current_teach_back(session=self.session)
        self.assertEqual(current.round_number, 1)
        self.assertEqual(current.question, teach_back.follow_up_question)

        retry = services.submit_teach_back(session=self.session, answer=CLEAR_TEACH_BACK_RESPONSE)
        self.assertEqual(retry.evaluation, 'CLEAR_UNDERSTANDING')
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

    def test_teach_back_force_advances_after_max_rounds_without_claiming_understanding(self):
        self._reach_teach_back_via_verification()
        services.submit_teach_back(session=self.session, answer=PARTIAL_TEACH_BACK_RESPONSE)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)

        final = services.submit_teach_back(session=self.session, answer=PARTIAL_TEACH_BACK_RESPONSE)
        self.assertEqual(final.evaluation, 'PARTIAL_UNDERSTANDING')
        self.session.refresh_from_db()
        # mastery.MAX_TEACH_BACK_ROUNDS caps rounds at 2 (0 and 1) — the
        # learner must move on to Transfer rather than loop forever, but
        # this must NOT be recorded as understanding.
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)
        record = services.get_concept_mastery(section=self.section, browser_session_key='teachback-browser')
        self.assertEqual(record.teach_back_score, 50)

    def test_round_cap_then_failed_transfer_still_goes_to_needs_review(self):
        """Forced advancement past an unresolved Teach-Back must never be
        mistaken for mastery — Transfer Check is still required, and
        failing it still routes to Needs Review, never Mastered."""
        self._reach_teach_back_via_verification()
        services.submit_teach_back(session=self.session, answer=PARTIAL_TEACH_BACK_RESPONSE)
        services.submit_teach_back(session=self.session, answer=PARTIAL_TEACH_BACK_RESPONSE)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

        services.ensure_transfer_problem(session=self.session)
        wrong_transfer = str(int(_correct_answer(self.section, kind='transfer')) + 1000)
        transfer = services.submit_transfer_check(
            session=self.session, answer=wrong_transfer, reasoning='わかりません', confidence=2,
        )
        self.assertFalse(transfer.is_correct)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.NEEDS_REVIEW)

    def test_teach_back_requires_a_non_empty_answer(self):
        self._reach_teach_back_via_verification()
        with self.assertRaises(ValidationError):
            services.submit_teach_back(session=self.session, answer='   ')

    def test_teach_back_cannot_be_submitted_outside_teach_back_stage(self):
        with self.assertRaises(ValidationError):
            services.submit_teach_back(session=self.session, answer=CLEAR_TEACH_BACK_RESPONSE)

    def test_full_path_through_teach_back_reaches_mastered(self):
        self._reach_teach_back_via_verification()
        services.submit_teach_back(session=self.session, answer=CLEAR_TEACH_BACK_RESPONSE)
        services.ensure_transfer_problem(session=self.session)
        transfer_answer = _correct_answer(self.section, kind='transfer')
        transfer = services.submit_transfer_check(
            session=self.session, answer=transfer_answer, reasoning='計算しました', confidence=5,
        )
        self.assertTrue(transfer.is_correct)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.MASTERED)

    def test_revision_success_with_low_hint_and_strong_reasoning_skips_teach_back(self):
        """Requirement C: a minor, quickly self-corrected slip shouldn't
        need Teach-Back at all."""
        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        services.submit_first_attempt(
            session=self.session, answer=wrong_answer, reasoning='勘です', confidence=2,
        )
        services.submit_diagnosis(session=self.session, answer='符号を間違えたと思います。')
        services.ensure_current_hint(session=self.session)

        correct_answer = _correct_answer(self.section, kind='first')
        services.submit_revision(
            session=self.session, answer=correct_answer,
            reasoning='今度は符号に気をつけて両辺を同じように処理し、正しく移項して計算しました',
            confidence=4,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)
        self.assertEqual(self.session.teach_back_level, '')
        self.assertEqual(self.session.teach_back_level_reason, 'revision_low_risk')

    def test_revision_success_with_high_hint_level_gets_targeted_teach_back(self):
        """Requirement E: heavy hint dependence (level 4+) warrants a
        Targeted check even though misconception probability was low."""
        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        services.submit_first_attempt(
            session=self.session, answer=wrong_answer, reasoning='勘です', confidence=2,
        )
        services.submit_diagnosis(session=self.session, answer='わかりません')
        for _ in range(3):
            services.ensure_current_hint(session=self.session)
            services.submit_revision(
                session=self.session, answer=wrong_answer, reasoning='まだ違う考え方です', confidence=2,
            )
        hint = services.ensure_current_hint(session=self.session)
        self.assertEqual(hint.level, 4)

        correct_answer = _correct_answer(self.section, kind='first')
        services.submit_revision(
            session=self.session, answer=correct_answer, reasoning='ヒントを見てやっと分かりました', confidence=3,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)
        self.assertEqual(self.session.teach_back_level, 'TARGETED')
        self.assertEqual(self.session.teach_back_level_reason, 'revision_high_hint')
        current = services.current_teach_back(session=self.session)
        self.assertTrue(current.question)
        self.assertNotEqual(current.question, demo_content.SHORT_TEACH_BACK_PROMPT)

    def test_revision_success_with_high_misconception_probability_gets_targeted_teach_back(self):
        """Requirement D: a confident-but-wrong first attempt (quadrant C)
        signals a likely real misconception, so even a quick recovery
        still gets a Targeted check."""
        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        services.submit_first_attempt(
            session=self.session, answer=wrong_answer, reasoning='絶対これだと思います', confidence=5,
        )
        services.submit_diagnosis(session=self.session, answer='符号を間違えたと思います。')
        services.ensure_current_hint(session=self.session)

        correct_answer = _correct_answer(self.section, kind='first')
        services.submit_revision(
            session=self.session, answer=correct_answer, reasoning='考え直しました', confidence=4,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)
        self.assertEqual(self.session.teach_back_level, 'TARGETED')
        self.assertEqual(self.session.teach_back_level_reason, 'revision_high_misconception')

    def test_teach_back_action_works_through_the_view(self):
        client_section = _create_section(name='Teach-Back画面テスト単元')
        url = reverse('math_quiz:section_quiz', args=[client_section.id])
        self.client.get(url)

        answer = _correct_answer(client_section, kind='first')
        self.client.post(url, {
            'action': 'first_attempt', 'answer': answer, 'reasoning': '移項して計算しました', 'confidence': 2,
        })
        self.client.post(url, {'action': 'verification', 'answer': 'わかりません'})
        response = self.client.get(url)
        self.assertContains(response, 'Teach-Back')

        response = self.client.post(
            url, {'action': 'teach_back', 'answer': CLEAR_TEACH_BACK_RESPONSE}, follow=True,
        )
        self.assertContains(response, 'AIのヒントなしで解いてください')


class MathAdaptiveTeachBackAIModeTests(TestCase):
    """Confirms AI is only consulted for genuinely ambiguous Verification/
    Teach-Back judgments — see mastery.heuristic_verification_signal /
    heuristic_teach_back_signal. Same non-demo + mocked AI pattern as
    MathAIGenerationTests."""

    def setUp(self):
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.mock_configured = configured_patcher.start()
        self.addCleanup(configured_patcher.stop)

        response_patcher = patch(
            'apps.math_quiz.services.generate_ai_response', side_effect=_fake_generate_ai_response,
        )
        self.mock_response = response_patcher.start()
        self.addCleanup(response_patcher.stop)

        self.unit = Unit.objects.create(name='Adaptive Teach-Back AIテスト単元', is_demo=False)
        self.section = Section.objects.create(unit=self.unit, title='セクションA', content='内容')
        self.session, _ = services.get_or_create_section_session(
            section=self.section, browser_session_key='adaptive-ai-browser',
        )
        services.ensure_first_problem(session=self.session)
        services.submit_first_attempt(
            session=self.session, answer='CORRECT_ANSWER', reasoning='解きました', confidence=2,
        )
        self.mock_response.reset_mock()

    def test_confidently_short_verification_answer_skips_ai_call(self):
        services.submit_verification(session=self.session, answer='わかりません')
        self.mock_response.assert_not_called()
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TEACH_BACK)

    def test_ambiguous_verification_answer_consults_ai(self):
        services.submit_verification(
            session=self.session,
            answer='CLEAR_VERIFICATION_ANSWER それなりに長い説明ですが特定のキーワードは含みません',
        )
        self.mock_response.assert_called_once()
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_state, WorkflowState.TRANSFER_TASK)

    def test_confidently_short_teach_back_answer_skips_ai_call(self):
        services.submit_verification(session=self.session, answer='わかりません')
        self.mock_response.reset_mock()
        services.submit_teach_back(session=self.session, answer='短い')
        self.mock_response.assert_not_called()

    def test_ambiguous_teach_back_answer_consults_ai(self):
        services.submit_verification(session=self.session, answer='わかりません')
        self.mock_response.reset_mock()
        teach_back = services.submit_teach_back(
            session=self.session, answer='CLEAR_TEACH_BACK_ANSWER それなりに長い説明です',
        )
        self.mock_response.assert_called_once()
        self.assertEqual(teach_back.evaluation, 'CLEAR_UNDERSTANDING')


class MathSectionStatusTests(TestCase):
    """classify_section_status is what unit_detail.html's per-section pills
    are built from — richer than the raw workflow state where the learner
    model has something to say, but still only one label at a time."""

    def test_mastered_without_due_review_shows_mastered_pill(self):
        label, tone = mastery.classify_section_status(
            section_state=WorkflowState.MASTERED, concept_mastery=None,
        )
        self.assertEqual((label, tone), ('Mastered', 'success'))

    def test_mastered_with_review_due_in_the_past_shows_recheck_pill(self):
        section = _create_section(name='再確認テスト単元')
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='review-browser',
        )
        services.ensure_first_problem(session=session)
        answer = _correct_answer(section, kind='first')
        services.submit_first_attempt(session=session, answer=answer, reasoning='計算しました', confidence=5)
        services.ensure_transfer_problem(session=session)
        transfer_answer = _correct_answer(section, kind='transfer')
        services.submit_transfer_check(
            session=session, answer=transfer_answer, reasoning='計算しました', confidence=5,
        )

        record = services.get_concept_mastery(section=section, browser_session_key='review-browser')
        self.assertIsNotNone(record.review_due_at)  # set automatically on reaching Mastered
        record.review_due_at = timezone.now() - datetime.timedelta(hours=1)
        record.save(update_fields=('review_due_at',))

        label, tone = mastery.classify_section_status(
            section_state=WorkflowState.MASTERED, concept_mastery=record,
        )
        self.assertEqual((label, tone), ('再確認の時期です', 'warning'))

    def test_overconfident_in_progress_shows_calibration_pill(self):
        record = ConceptMastery(confidence_calibration=ConfidenceCalibration.OVERCONFIDENT)
        label, tone = mastery.classify_section_status(
            section_state=WorkflowState.GUIDED_REVISION, concept_mastery=record,
        )
        self.assertEqual((label, tone), ('自信過剰かもしれません', 'muted'))

    def test_underconfident_in_progress_shows_calibration_pill(self):
        record = ConceptMastery(confidence_calibration=ConfidenceCalibration.UNDERCONFIDENT)
        label, tone = mastery.classify_section_status(
            section_state=WorkflowState.FIRST_ATTEMPT, concept_mastery=record,
        )
        self.assertEqual((label, tone), ('自信不足かもしれません', 'muted'))

    def test_not_started_shows_not_started_pill(self):
        label, tone = mastery.classify_section_status(section_state=None, concept_mastery=None)
        self.assertEqual((label, tone), ('未着手', 'muted'))

    def test_unit_detail_view_renders_status_pills(self):
        unit, sections = _create_unit_with_sections('セクション状態テスト科目', 1)
        section = sections[0]
        quiz_url = reverse('math_quiz:section_quiz', args=[section.id])
        detail_url = reverse('math_quiz:unit_detail', args=[unit.id])
        diag_url = reverse('math_quiz:unit_diagnostic', args=[unit.id])

        # unit_detail redirects to the course diagnostic until it's done.
        self.client.get(detail_url)
        diagnostic = UnitDiagnosticSession.objects.get(unit=unit)
        item = diagnostic.answers.first()
        correct = _correct_answer(item.section, kind='diagnostic')
        self.client.post(diag_url, {'action': 'answer', 'answer_id': item.id, 'answer': correct})
        self.client.post(diag_url, {'action': 'continue'})

        # Wrong + confident => overconfident calibration, still in progress.
        wrong = str(int(_correct_answer(section, kind='first')) + 1000)
        self.client.post(quiz_url, {
            'action': 'first_attempt', 'answer': wrong, 'reasoning': '勘です', 'confidence': 5,
        })

        response = self.client.get(detail_url)
        self.assertContains(response, '自信過剰かもしれません')


class MathI18nTests(TestCase):
    """Minimal ja/en language switch — see config/settings.py
    (LocaleMiddleware, LANGUAGES, LOCALE_PATHS) and config/urls.py
    (django.conf.urls.i18n's set_language view). Translation itself is
    Django's own gettext/gettext_lazy machinery; these tests only check
    the switch works end-to-end, not the completeness of the wordlist."""

    def test_japanese_is_the_default_language(self):
        response = self.client.get(reverse('math_quiz:home'))
        self.assertContains(response, '数学')

    def test_english_can_be_selected(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': reverse('math_quiz:home')})
        response = self.client.get(reverse('math_quiz:home'))
        self.assertContains(response, 'Math')
        self.assertNotContains(response, '数学')

    def test_switching_back_to_japanese_works(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': reverse('math_quiz:home')})
        self.client.post(reverse('set_language'), {'language': 'ja', 'next': reverse('math_quiz:home')})
        response = self.client.get(reverse('math_quiz:home'))
        self.assertContains(response, '数学')
        self.assertNotContains(response, 'Choose a subject')

    def test_a_representative_page_renders_translated_english_ui(self):
        section = _create_section(name='英語UIテスト単元')
        self.client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        response = self.client.get(reverse('math_quiz:section_quiz', args=[section.id]))
        self.assertContains(response, 'Answer')  # 解答
        self.assertContains(response, 'Confidence')  # 自信度
        self.assertNotContains(response, '解答')

    def test_ai_generation_receives_the_selected_language(self):
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch('apps.math_quiz.services.generate_ai_response')
        self.addCleanup(response_patcher.stop)
        mock_response = response_patcher.start()
        mock_response.return_value = json.dumps({'problem': 'What is 2 + 2?'})

        unit = Unit.objects.create(name='英語AIテスト単元', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')

        with translation.override('en'):
            services._generate_problem(section=section, kind='first')
        self.assertIn('Answer in English.', mock_response.call_args.kwargs['system_prompt'])

        mock_response.reset_mock()
        with translation.override('ja'):
            services._generate_problem(section=section, kind='first')
        self.assertIn('日本語で答えてください。', mock_response.call_args.kwargs['system_prompt'])
