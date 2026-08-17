import datetime
import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone, translation

from apps.ai_engine.exceptions import AIEngineError

from . import ai_prompts, demo_content, mastery, services
from .models import (
    ConceptMastery,
    ConfidenceCalibration,
    MasteryState,
    Section,
    SectionSession,
    Unit,
    UnitDiagnosticSession,
    UnitMaterial,
)
from .state_machine import WorkflowState
from .templatetags.math_extras import latexify


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

    def test_sample_unit_is_hidden_from_the_course_list_but_still_exists(self):
        response = self.client.get(reverse('math_quiz:home'))
        self.assertNotContains(response, '一次方程式（サンプル）')
        sample = Unit.objects.get(name='一次方程式（サンプル）')
        self.assertTrue(sample.is_demo)  # still in the DB, untouched

    def test_sample_unit_still_works_if_visited_directly(self):
        sample = services.ensure_sample_unit()
        response = self.client.get(reverse('math_quiz:unit_detail', args=[sample.id]), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_section_quiz_starts_directly_at_first_attempt(self):
        section = _create_section()
        url = reverse('math_quiz:section_quiz', args=[section.id])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, section.unit.name)
        self.assertContains(response, 'First attempt')  # English is now the default language


class MathDontKnowButtonTests(TestCase):
    """The "わからない" button at the FIRST_ATTEMPT stage — see
    views.section_quiz / _handle_action's 'dont_know'/'think_again'
    actions and services.dont_know_hint."""

    def setUp(self):
        self.section = _create_section()
        self.url = reverse('math_quiz:section_quiz', args=[self.section.id])

    def test_dont_know_button_is_shown_on_the_first_attempt_screen(self):
        response = self.client.get(self.url)
        self.assertContains(response, "I don't know")

    def test_clicking_dont_know_shows_a_level_1_hint(self):
        response = self.client.post(self.url, {'action': 'dont_know'}, follow=True)
        self.assertContains(response, 'Hint level 1')
        expected_hint = demo_content.build_hint(section=self.section, level=1, kind='first')
        self.assertContains(response, expected_hint)

    def test_dont_know_never_reveals_the_correct_answer(self):
        correct_answer = _correct_answer(self.section, kind='first')
        response = self.client.post(self.url, {'action': 'dont_know'}, follow=True)
        self.assertNotContains(response, f'x = {correct_answer}')

    def test_dont_know_does_not_end_the_section_or_change_state(self):
        self.client.post(self.url, {'action': 'dont_know'})
        session = SectionSession.objects.get(section=self.section)
        self.assertEqual(session.current_state, WorkflowState.FIRST_ATTEMPT)
        self.assertEqual(session.attempts.count(), 0)  # nothing recorded — no Attempt created

    def test_think_again_returns_to_the_normal_answer_form(self):
        self.client.post(self.url, {'action': 'dont_know'})
        response = self.client.post(self.url, {'action': 'think_again'}, follow=True)
        self.assertContains(response, 'name="answer"')
        self.assertNotContains(response, 'Hint level 1')

    def test_normal_answer_submission_still_works_after_using_dont_know(self):
        self.client.post(self.url, {'action': 'dont_know'})
        self.client.post(self.url, {'action': 'think_again'})
        correct_answer = _correct_answer(self.section, kind='first')
        response = self.client.post(self.url, {
            'action': 'first_attempt', 'answer': correct_answer,
            'reasoning': '移項して計算しました', 'confidence': 5,
        }, follow=True)
        session = SectionSession.objects.get(section=self.section)
        self.assertEqual(session.attempts.count(), 1)
        self.assertTrue(session.attempts.first().is_correct)


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

    def test_revision_stage_never_reveals_the_answer_before_it_is_submitted(self):
        # Regression test for the answer-leak bug: walk through diagnosis
        # and every hint level, and confirm neither the wrong-answer
        # explanation nor any hint (including level 5, the last resort)
        # ever contains the section's correct value before the learner
        # submits it themselves.
        correct_value = _correct_answer(self.section, kind='first')
        wrong_answer = str(int(correct_value) + 1000)
        attempt = services.submit_first_attempt(
            session=self.session, answer=wrong_answer, reasoning='勘です', confidence=2,
        )
        self.assertNotIn(correct_value, attempt.explanation)
        services.submit_diagnosis(session=self.session, answer='わかりません')

        for _expected_level in range(1, 6):
            hint = services.ensure_current_hint(session=self.session)
            self.assertNotIn(correct_value, hint.content)
            revised = services.submit_revision(
                session=self.session, answer=wrong_answer, reasoning='まだ違う考え方です', confidence=2,
            )
            self.assertNotIn(correct_value, revised.explanation)

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
        self.assertContains(response, 'First attempt')  # English is now the default language
        new_session = Section.objects.get(id=self.section.id).sessions.get()
        self.assertNotEqual(old_pk, new_session.pk)

    def test_explicit_reset_action_starts_a_fresh_round_immediately(self):
        # action=reset (posted directly, e.g. from the section menu's "最初
        # からやり直す" button) is a one-click reset — unlike a plain
        # revisit, it doesn't need an intermediate outcome-page view first.
        self.client.get(self.url)
        session = Section.objects.get(id=self.section.id).sessions.get()
        wrong_answer = str(int(_correct_answer(self.section, kind='first')) + 1000)
        self._post(action='first_attempt', answer=wrong_answer, reasoning='勘です', confidence=1)
        self._post(action='diagnosis', answer='わかりません')
        for _ in range(5):
            self._post(action='revision', answer=wrong_answer, reasoning='まだ違います', confidence=2)
        session.refresh_from_db()
        self.assertEqual(session.current_state, WorkflowState.NEEDS_REVIEW)

        response = self._post(action='reset')
        self.assertRedirects(response, self.url)
        new_session = Section.objects.get(id=self.section.id).sessions.get()
        self.assertEqual(new_session.current_state, WorkflowState.FIRST_ATTEMPT)
        self.assertNotEqual(session.pk, new_session.pk)

    def test_revision_page_html_never_contains_the_answer_before_submission(self):
        correct_value = _correct_answer(self.section, kind='first')
        wrong_answer = str(int(correct_value) + 1000)
        self.client.get(self.url)
        self._post(action='first_attempt', answer=wrong_answer, reasoning='勘です', confidence=2)
        self._post(action='diagnosis', answer='わかりません')

        # A short number like "-4" can coincidentally appear inside CSS/JS
        # in an unrelated page, so check the specific answer-reveal phrasing
        # rather than a bare substring match of the number.
        leak_patterns = (f'x = {correct_value}', f'答えは {correct_value}', f'= {correct_value} で合っています')
        for _ in range(5):
            self._post(action='revision', answer=wrong_answer, reasoning='まだ違います', confidence=2)
            # Follow the redirect back to the revision/outcome page and
            # check the rendered HTML itself — not just the service layer —
            # since that's what the learner actually sees pre-submission.
            page = self.client.get(self.url)
            if b'action" value="revision"' not in page.content:
                break
            content = page.content.decode()
            for pattern in leak_patterns:
                self.assertNotIn(pattern, content)


class MathUnitDiagnosticServiceTests(TestCase):
    """The diagnostic quiz lives at the course level: one problem drawn
    from every section (up to MAX_DIAGNOSTIC_QUESTIONS), taken before the
    section list is shown. Every candidate section always gets a
    question, regardless of whether earlier answers were right or
    wrong — there's no early-stop shortcut."""

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

    def test_consecutive_agreeing_answers_do_not_stop_the_quiz_early(self):
        diagnostic = services.start_unit_diagnostic(unit=self.unit, browser_session_key='browser-key')
        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        self.assertIsNone(diagnostic.completed_at)

        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        # Two agreeing (both correct) answers used to stop the quiz early —
        # that shortcut is gone, so with 3 candidate sections it must still
        # be waiting on the 3rd question here.
        self.assertIsNone(diagnostic.completed_at)
        self.assertEqual(diagnostic.answers.count(), 3)

        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        # All 3 candidate sections asked (and none left) is what ends it now.
        self.assertIsNotNone(diagnostic.completed_at)
        self.assertEqual(diagnostic.answers.count(), 3)

    def test_diagnostic_always_asks_every_candidate_section_never_past_the_cap(self):
        unit, _sections = _create_unit_with_sections('診断長め科目', 6)
        diagnostic = services.start_unit_diagnostic(unit=unit, browser_session_key='browser-key-2')
        # All-correct used to trigger the early-stop shortcut after just 2
        # questions — it must now run all the way to MAX_DIAGNOSTIC_QUESTIONS
        # (5), never asking a 6th question even though a 6th section exists.
        for _ in range(services.MAX_DIAGNOSTIC_QUESTIONS):
            diagnostic.refresh_from_db()
            self.assertIsNone(diagnostic.completed_at)
            self._answer_current(diagnostic, correct=True)
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
        self.assertIsNone(diagnostic.completed_at)  # 2 of 3 candidate sections answered, one left

        self._answer_current(diagnostic, correct=True)
        diagnostic.refresh_from_db()
        # All 3 candidate sections answered (self.sections has 3) — done.
        self.assertIsNotNone(diagnostic.completed_at)

        result = services.build_unit_diagnostic_result(diagnostic=diagnostic)
        self.assertEqual(result['correct_count'], 2)
        self.assertEqual(result['total'], 3)
        self.assertEqual([s.id for s in result['recommended_sections']], [first_item.section_id])

    def test_diagnostic_never_repeats_a_problem_text_within_one_session(self):
        # is_demo=True (not False): this test exercises the deterministic
        # dedup invariant itself, not AI-vs-demo branching — is_demo=False
        # here would make _ai_mode() depend on whatever AI provider happens
        # to be configured in the environment (a real, unmocked network
        # call), which is what made this test slow/flaky before.
        unit, _sections = _create_unit_with_sections('診断重複テスト科目', 5, is_demo=True)
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
        self.assertContains(response, 'Diagnostic result')  # English is now the default language

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

    def test_progress_shows_first_question_out_of_the_actual_candidate_total(self):
        self.client.get(self.detail_url)  # creates the diagnostic session (3 sections -> total 3)
        response = self.client.get(self.diag_url)
        self.assertContains(response, 'Diagnostic question 1 / 3')
        self.assertEqual(response.context['current'], 1)
        self.assertEqual(response.context['total'], 3)
        self.assertEqual(response.context['progress_percent'], 33)

    def test_progress_advances_after_answering(self):
        self.client.get(self.detail_url)
        diagnostic = UnitDiagnosticSession.objects.get(unit=self.unit)
        item = diagnostic.answers.get(is_correct__isnull=True)
        wrong_answer = str(int(_correct_answer(item.section, kind='diagnostic')) + 1000)
        self.client.post(self.diag_url, {'action': 'answer', 'answer_id': item.id, 'answer': wrong_answer})

        response = self.client.get(self.diag_url)
        self.assertContains(response, 'Diagnostic question 2 / 3')
        self.assertEqual(response.context['progress_percent'], 67)

    def test_progress_reaches_100_percent_on_the_final_question(self):
        self.client.get(self.detail_url)
        diagnostic = UnitDiagnosticSession.objects.get(unit=self.unit)
        # Alternate correct/incorrect so the last-two-agree early stop (see
        # services._diagnostic_should_stop) never fires, forcing the quiz
        # through all 3 candidate sections instead of stopping at 2.
        for i in range(2):
            item = diagnostic.answers.get(is_correct__isnull=True)
            correct_answer = _correct_answer(item.section, kind='diagnostic')
            answer = correct_answer if i % 2 == 0 else str(int(correct_answer) + 1000)
            self.client.post(self.diag_url, {'action': 'answer', 'answer_id': item.id, 'answer': answer})
            diagnostic.refresh_from_db()
        self.assertIsNone(diagnostic.completed_at)  # still mid-quiz, on question 3 of 3

        response = self.client.get(self.diag_url)
        self.assertContains(response, 'Diagnostic question 3 / 3')
        self.assertEqual(response.context['progress_percent'], 100)

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


class MathDiagnosticGenerationFailureTests(TestCase):
    """Regression coverage for a reported bug: when the next diagnostic
    question fails to generate, the learner used to be stranded on a
    screen with a blank problem (or a 500) — progress showed e.g. "4/5"
    but there was no question to answer. Ending the quiz right there,
    using whatever was already answered, is the fix — see
    services._add_diagnostic_question / end_unit_diagnostic_now and
    views.unit_diagnostic's defensive current_item check."""

    def setUp(self):
        self.unit, self.sections = _create_unit_with_sections('生成失敗テスト科目', 5)

    def test_generation_failure_ends_the_quiz_using_answers_so_far(self):
        diagnostic = services.start_unit_diagnostic(unit=self.unit, browser_session_key='fail-key')
        item = diagnostic.answers.get(is_correct__isnull=True)
        answer = _correct_answer(item.section, kind='diagnostic')

        with patch('apps.math_quiz.services._generate_problem', side_effect=RuntimeError('boom')):
            result_item = services.submit_unit_diagnostic_answer(
                diagnostic=diagnostic, answer_id=item.id, answer=answer,
            )

        self.assertTrue(result_item.is_correct)  # the answer that DID succeed is still graded and kept
        diagnostic.refresh_from_db()
        self.assertIsNotNone(diagnostic.completed_at)
        self.assertEqual(diagnostic.answers.count(), 1)  # no phantom/blank next question was created

        result = services.build_unit_diagnostic_result(diagnostic=diagnostic)
        self.assertEqual(result['total'], 1)

    def test_view_shows_the_result_screen_not_a_blank_problem_or_a_500(self):
        detail_url = reverse('math_quiz:unit_detail', args=[self.unit.id])
        diag_url = reverse('math_quiz:unit_diagnostic', args=[self.unit.id])
        self.client.get(detail_url)  # creates the diagnostic + Q1, under the client's own session
        diagnostic = UnitDiagnosticSession.objects.get(unit=self.unit)
        item = diagnostic.answers.get(is_correct__isnull=True)
        answer = _correct_answer(item.section, kind='diagnostic')

        with patch('apps.math_quiz.services._generate_problem', side_effect=RuntimeError('boom')):
            response = self.client.post(
                diag_url, {'action': 'answer', 'answer_id': item.id, 'answer': answer}, follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Diagnostic result')  # English is now the default language
        self.assertNotContains(response, '<div class="equation"></div>')

    def test_view_self_heals_a_stuck_diagnostic_with_no_pending_question(self):
        """Belt-and-suspenders: even if a diagnostic somehow ends up with
        answers but no pending question and no completed_at (the exact
        broken state from the bug report — e.g. left over from before this
        fix), the view must never render the blank-problem screen."""
        detail_url = reverse('math_quiz:unit_detail', args=[self.unit.id])
        diag_url = reverse('math_quiz:unit_diagnostic', args=[self.unit.id])
        self.client.get(detail_url)
        diagnostic = UnitDiagnosticSession.objects.get(unit=self.unit)
        item = diagnostic.answers.get(is_correct__isnull=True)
        item.is_correct = True
        item.answer = '1'
        item.save(update_fields=('is_correct', 'answer'))
        # Stuck: answered, but no follow-up question and not completed.

        response = self.client.get(diag_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Diagnostic result')  # English is now the default language
        diagnostic.refresh_from_db()
        self.assertIsNotNone(diagnostic.completed_at)

    def test_normal_diagnostic_still_completes_all_the_way_through(self):
        # No mocked failure here — confirms the fix didn't change the
        # happy path (still asks every candidate section, still reaches
        # the results screen normally).
        diagnostic = services.start_unit_diagnostic(unit=self.unit, browser_session_key='normal-key')
        while diagnostic.completed_at is None:
            item = diagnostic.answers.get(is_correct__isnull=True)
            answer = _correct_answer(item.section, kind='diagnostic')
            services.submit_unit_diagnostic_answer(diagnostic=diagnostic, answer_id=item.id, answer=answer)
            diagnostic.refresh_from_db()
        self.assertEqual(diagnostic.answers.count(), len(self.sections))


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

    def test_hint_level_5_does_not_reveal_the_final_answer(self):
        # Level 5 is the last-resort hint, but even it must never state the
        # final answer before the learner submits their own revised answer
        # (see ai_prompts.HINT_SYSTEM_PROMPT / demo_content.build_hint).
        _problem, value = demo_content.build_problem(self.word_section, kind='first')
        hint = demo_content.build_hint(section=self.word_section, level=5, kind='first')
        self.assertNotIn(f'x = {value}', hint)
        self.assertNotIn(f'= {value}。', hint)

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


class MathUnitMaterialTests(TestCase):
    """Adding reference material to an already-created Unit — see
    models.UnitMaterial, services.add_unit_materials/_unit_material_files,
    views.add_unit_material. Kept as its own 1-to-many table so Unit.file
    (the single file captured at creation) keeps its original meaning and
    existing data/behavior is untouched."""

    def _upload(self, name, content=b'dummy content', content_type='application/pdf'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, content, content_type=content_type)

    def _url(self, unit):
        return reverse('math_quiz:add_unit_material', args=[unit.id])

    def test_can_add_a_single_material_to_an_existing_unit(self):
        unit = Unit.objects.create(name='資料追加テスト単元1', is_demo=True)
        response = self.client.post(self._url(unit), {'file': self._upload('note.pdf')})
        self.assertRedirects(response, reverse('math_quiz:unit_detail', args=[unit.id]))
        self.assertEqual(unit.materials.count(), 1)
        self.assertTrue(unit.materials.get().file.name.endswith('.pdf'))

    def test_can_add_multiple_materials_at_once(self):
        unit = Unit.objects.create(name='資料追加テスト単元2', is_demo=True)
        response = self.client.post(self._url(unit), {
            'file': [self._upload('a.pdf'), self._upload('b.png', content_type='image/png')],
        })
        self.assertRedirects(response, reverse('math_quiz:unit_detail', args=[unit.id]))
        self.assertEqual(unit.materials.count(), 2)
        self.assertEqual(
            set(unit.materials.values_list('content_type', flat=True)),
            {'application/pdf', 'image/png'},
        )

    def test_existing_material_is_not_deleted_or_overwritten_by_a_later_upload(self):
        unit = Unit.objects.create(name='資料追加テスト単元3', is_demo=True, file=self._upload('original.pdf'))
        self.client.post(self._url(unit), {'file': self._upload('first-addition.pdf')})
        self.client.post(self._url(unit), {'file': self._upload('second-addition.png', content_type='image/png')})

        unit.refresh_from_db()
        self.assertTrue(unit.file.name.endswith('.pdf'))  # untouched original
        self.assertIn('original', unit.file.name)
        self.assertEqual(unit.materials.count(), 2)  # both additions kept, neither replaced the other
        names = set(unit.materials.values_list('file', flat=True))
        self.assertTrue(any('first-addition' in n for n in names))
        self.assertTrue(any('second-addition' in n for n in names))

    def test_adding_material_does_not_call_the_ai(self):
        unit = Unit.objects.create(name='資料追加AI呼び出しテスト単元', is_demo=False)
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        with patch('apps.math_quiz.services.generate_ai_response') as mock_response:
            self.client.post(self._url(unit), {'file': self._upload('note.pdf')})
        mock_response.assert_not_called()

    def test_uploading_no_file_shows_an_error_and_adds_nothing(self):
        unit = Unit.objects.create(name='資料追加空テスト単元', is_demo=True)
        response = self.client.post(self._url(unit), {}, follow=True)
        self.assertEqual(unit.materials.count(), 0)
        self.assertContains(response, 'Please select a file')

    def test_added_materials_are_included_when_sections_are_generated(self):
        """The one AI call generate_sections makes must see both a file
        passed in explicitly (the creation-time path) and anything already
        saved as UnitMaterial — with no extra AI call for either."""
        unit = Unit.objects.create(name='資料反映テスト単元', is_demo=False)
        services.add_unit_materials(unit=unit, files=[self._upload('slides.pdf', content=b'slide bytes')])

        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch('apps.math_quiz.services.generate_ai_response')
        mock_response = response_patcher.start()
        self.addCleanup(response_patcher.stop)
        mock_response.return_value = json.dumps({'sections': [{'title': 'セクション1', 'content': '内容'}]})

        services.generate_sections(unit, unit.name, [(b'creation time bytes', 'application/pdf')])

        self.assertEqual(mock_response.call_count, 1)  # exactly the existing single call, nothing extra
        _args, kwargs = mock_response.call_args
        passed_files = kwargs['files']
        self.assertIn((b'creation time bytes', 'application/pdf'), passed_files)
        self.assertIn((b'slide bytes', 'application/pdf'), passed_files)

    def test_unit_without_any_material_still_generates_sections_normally(self):
        unit = Unit.objects.create(name='資料なしテスト単元', is_demo=True)
        services.generate_sections(unit, unit.name)
        self.assertTrue(unit.sections.exists())

    def test_unit_detail_page_lists_both_existing_and_added_materials(self):
        unit = Unit.objects.create(name='資料一覧表示テスト単元', is_demo=True, file=self._upload('original.pdf'))
        services.generate_sections(unit, unit.name)
        services.add_unit_materials(unit=unit, files=[self._upload('added.pdf')])

        detail_url = reverse('math_quiz:unit_detail', args=[unit.id])
        self.client.get(detail_url)  # first visit creates the course diagnostic session
        key = self.client.session.session_key
        diagnostic = UnitDiagnosticSession.objects.get(unit=unit, browser_session_key=key)
        diagnostic.completed_at = timezone.now()
        diagnostic.save(update_fields=('completed_at',))

        response = self.client.get(detail_url)
        self.assertContains(response, 'original')
        self.assertContains(response, 'added')


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

    def test_diagnostic_problem_generation_uses_the_numeric_only_prompt(self):
        """Diagnostic problems must be answerable with a single number (see
        ai_prompts.DIAGNOSTIC_PROBLEM_SYSTEM_PROMPT) — a distinct prompt
        from the one used for a section's regular first_problem, which
        allows richer answers."""
        section = Section.objects.create(unit=self.unit, title='セクションD', content='内容')
        services._generate_problem(section=section, kind='diagnostic')
        used_prompt = self.mock_response.call_args.kwargs['system_prompt']
        self.assertIn(ai_prompts.DIAGNOSTIC_PROBLEM_SYSTEM_PROMPT, used_prompt)
        self.assertIn('数値', used_prompt)

    def test_first_problem_generation_uses_the_general_prompt_not_the_diagnostic_one(self):
        section = Section.objects.create(unit=self.unit, title='セクションD2', content='内容')
        services._generate_problem(section=section, kind='first')
        used_prompt = self.mock_response.call_args.kwargs['system_prompt']
        self.assertIn(ai_prompts.PROBLEM_SYSTEM_PROMPT, used_prompt)
        self.assertNotIn(ai_prompts.DIAGNOSTIC_PROBLEM_SYSTEM_PROMPT, used_prompt)

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

    def test_catalog_keys_match_curated_subjects_and_have_at_least_three_problems_each(self):
        # 3 (not 2): a 2-entry pool is exhausted by the diagnostic quiz
        # alone once it asks about 2 different sections, leaving nothing
        # left for any section's own first_problem — see
        # MathDiagnosticSectionDedupTests for the regression this covers.
        for name in demo_content.AI_FALLBACK_PROBLEMS:
            self.assertIn(name, demo_content.UNIT_SECTION_PROFILES)
        for name, catalog in demo_content.AI_FALLBACK_PROBLEMS.items():
            self.assertGreaterEqual(len(catalog['keywords']), 1, name)
            self.assertGreaterEqual(len(catalog['problems']), 3, name)

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
        # The wrong-answer explanation must never reveal the correct value
        # itself — only after a correct submission is it shown (above).
        self.assertNotIn(str(answer), explanation)

    def test_generic_fallback_hint_level_5_does_not_reveal_the_answer(self):
        unit = Unit.objects.create(name='群論', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        entry = demo_content._ai_fallback_entry(section, kind='first')
        for level in range(1, 6):
            hint = demo_content.build_hint(section=section, level=level, kind='first')
            self.assertNotIn(str(entry['answer']), hint)

    def test_generic_fallback_hints_are_grounded_in_the_problems_own_method_hint(self):
        """Levels 3-5 should say something concrete about *this* problem
        (reusing the same safe wrong_note already used for wrong-answer
        feedback), not just generic, subject-agnostic phrasing."""
        unit = Unit.objects.create(name='群論', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        entry = demo_content._ai_fallback_entry(section, kind='first')
        for level in (3, 4, 5):
            hint = demo_content.build_hint(section=section, level=level, kind='first')
            self.assertIn(entry['wrong_note'], hint)

    def test_differential_equation_wrong_note_does_not_coincidentally_reveal_the_answer(self):
        """Regression check for a narrow edge case found while grounding
        hints in wrong_note: for a couple of catalog entries, wrong_note
        used to restate a given problem value (e.g. an initial condition
        y(0)=5) that happens to numerically equal that problem's derived
        answer — safe as a one-off wrong-answer explanation, but would
        have leaked through every hint level once reused there. Checked
        against wrong_note itself (not the full hint, whose own fixed
        wrapping text can coincidentally contain a stray digit — e.g.
        "1つずつ" for an answer of 1 — unrelated to any real leak)."""
        unit = Unit.objects.create(name='微分方程式', is_demo=True)
        section = Section.objects.create(unit=unit, title='一階微分方程式', content='内容')
        for salt in range(5):
            entry = demo_content._ai_fallback_entry(section, kind='first', salt=salt)
            self.assertNotIn(str(entry['answer']), entry['wrong_note'])

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


class MathFallbackSectionTopicMatchTests(TestCase):
    """Regression coverage for a reported bug: a section titled
    '自然数と整数の性質' (natural numbers/integers) inside a '数と式'-named
    course showed a '(x-6)^2 を展開したときの定数項を求めなさい' problem —
    that catalog entry belongs to '数と式''s narrow 展開/因数分解/有理化
    scope, not to this section's actual topic. See
    demo_content._section_matches_catalog."""

    def test_off_topic_section_in_a_catalog_matched_course_does_not_get_that_catalogs_problem(self):
        unit = Unit.objects.create(name='数と式', is_demo=True)
        section = Section.objects.create(
            unit=unit, title='自然数と整数の性質',
            content='自然数の定義、加減乗除の基本的性質、整数の符号と絶対値について学び、'
                    '数の大小関係や約数・倍数の概念を理解する。',
        )
        catalog_problems = {e['problem'] for e in demo_content.AI_FALLBACK_PROBLEMS['数と式']['problems']}
        for salt in range(demo_content.MAX_PROBLEM_DEDUP_ATTEMPTS):
            problem, _value = demo_content.build_problem(section, kind='first', salt=salt)
            self.assertNotIn(problem, catalog_problems)
        # Falls through to the generic, subject-agnostic equation instead —
        # safe (not confidently wrong), even though less tailored.
        problem, _value = demo_content.build_problem(section, kind='first')
        self.assertRegex(problem, r'^-?\d+x [+-] \d+ = -?\d+$')

    def test_on_topic_section_in_the_same_course_still_gets_the_catalog_problem(self):
        # Same '数と式' course, but this section's own topic (matching the
        # curated UNIT_SECTION_PROFILES title/content for '数と式') really
        # is what the catalog was written for — the fix must not make the
        # catalog unreachable altogether within a multi-topic course.
        unit = Unit.objects.create(name='数と式', is_demo=True)
        section = Section.objects.create(
            unit=unit, title='展開と因数分解', content='多項式の展開と因数分解の公式を確認します。',
        )
        problem, answer = demo_content.build_problem(section, kind='first')
        catalog = demo_content.AI_FALLBACK_PROBLEMS['数と式']['problems']
        matching = [e for e in catalog if e['problem'] == problem]
        self.assertEqual(len(matching), 1)
        self.assertEqual(answer, matching[0]['answer'])

    def test_ai_generation_prompt_forbids_off_topic_problems(self):
        self.assertIn('別分野の問題を生成しないこと', ai_prompts.PROBLEM_SYSTEM_PROMPT)
        self.assertIn('別分野の問題を生成しないこと', ai_prompts.DIAGNOSTIC_PROBLEM_SYSTEM_PROMPT)

    def test_generic_placeholder_content_still_falls_back_to_the_course_catalog(self):
        # Regression guard: sections with no real topic-specific content of
        # their own (as in most of this test suite's setup) must keep
        # using the unit-level catalog match exactly as before — there's
        # no section-level signal to second-guess it with.
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        problem, _value = demo_content.build_problem(section, kind='first')
        catalog_problems = {e['problem'] for e in demo_content.AI_FALLBACK_PROBLEMS['群論']['problems']}
        self.assertIn(problem, catalog_problems)


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


class MathDiagnosticSectionDedupTests(TestCase):
    """Regression coverage for a reported critical bug: the course
    diagnostic quiz and a section's own first_problem/transfer_problem
    showed the exact same fallback-catalog text (e.g. both showing
    "dy/dx = 2x の一般解...のCの値を求めなさい。" for 微分方程式). Root
    cause was twofold — see demo_content._ai_fallback_entry and
    AI_FALLBACK_PROBLEMS: (1) each salt re-ran an independent rng.choice
    instead of cycling, so two different (section, kind) seeds could
    coincidentally land on the same one of only 2 catalog entries even
    though services._used_problems_in_unit already excludes known text;
    (2) with only 2 entries, a 2-question diagnostic alone could exhaust
    the entire catalog before any section was even visited, leaving
    nothing non-excluded for any section's first_problem to find. Fixed
    by making _ai_fallback_entry cycle deterministically through the
    catalog (so the exclude-driven search actually explores every entry)
    and growing each catalog to 3 entries."""

    def _complete_diagnostic(self, unit, browser_session_key):
        """Answers every diagnostic question (correctly, though it no
        longer affects how many questions get asked — every candidate
        section always gets one). _correct_answer alone assumes salt=0,
        but duplicate avoidance can legitimately pick a different salt for
        a given (section, kind) — so the expected value is resolved
        against whichever salt actually produced this question's problem
        text."""
        diagnostic = services.start_unit_diagnostic(unit=unit, browser_session_key=browser_session_key)
        seen = []
        while True:
            diagnostic.refresh_from_db()
            if diagnostic.completed_at is not None:
                break
            item = diagnostic.answers.get(is_correct__isnull=True)
            seen.append(item.problem)
            value = next(
                v for p, v in (
                    demo_content.build_problem(item.section, kind='diagnostic', salt=s) for s in range(4)
                ) if p == item.problem
            )
            services.submit_unit_diagnostic_answer(diagnostic=diagnostic, answer_id=item.id, answer=str(value))
        return diagnostic, seen

    def test_diagnostic_problems_never_reused_as_a_sections_first_problem(self):
        # 2 sections (not 3+): the diagnostic no longer stops early — it
        # now always asks one question per candidate section — so with a
        # 5-entry-per-subject catalog, 2 sections keeps total demand
        # (2 diagnostic + 2 first_problem = 4) comfortably inside capacity.
        # See test_diagnostic_and_every_sections_first_problem_are_all_mutually_distinct.
        unit = Unit.objects.create(name='群論', is_demo=True)
        sections = [
            Section.objects.create(unit=unit, title=f'セクション{i + 1}', content='内容', order=i)
            for i in range(2)
        ]
        _diagnostic, diagnostic_problems = self._complete_diagnostic(unit, 'diag-first-browser')

        for section in sections:
            session, _ = services.get_or_create_section_session(
                section=section, browser_session_key='diag-first-browser',
            )
            first_problem = services.ensure_first_problem(session=session)
            self.assertNotIn(
                first_problem, diagnostic_problems,
                f'{section.title} first_problem duplicated a diagnostic problem',
            )

    def test_diagnostic_problems_never_reused_as_a_sections_transfer_problem(self):
        # 2 sections — see test_diagnostic_problems_never_reused_as_a_sections_first_problem.
        unit = Unit.objects.create(name='群論', is_demo=True)
        sections = [
            Section.objects.create(unit=unit, title=f'セクション{i + 1}', content='内容', order=i)
            for i in range(2)
        ]
        _diagnostic, diagnostic_problems = self._complete_diagnostic(unit, 'diag-transfer-browser')

        section = sections[0]
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='diag-transfer-browser',
        )
        services.ensure_first_problem(session=session)
        transfer_problem = services.ensure_transfer_problem(session=session)
        self.assertNotIn(transfer_problem, diagnostic_problems)

    def test_diagnostic_and_every_sections_first_problem_are_all_mutually_distinct(self):
        """The full reported scenario end-to-end: diagnostic quiz, then
        visit every section — every problem shown anywhere in the course
        must be unique (diagnostic included). Uses 2 sections (not 3+): a
        hand-authored catalog (4 entries per subject) can comfortably
        guarantee this for the common case, but isn't a truly unbounded
        pool — see test_exhausted_candidate_pool_falls_back_safely_* for
        the explicitly-permitted graceful-repeat behavior once a course
        legitimately needs more distinct problems than the catalog has."""
        unit = Unit.objects.create(name='微分方程式', is_demo=True)
        sections = [
            Section.objects.create(unit=unit, title=f'セクション{i + 1}', content='内容', order=i)
            for i in range(2)
        ]
        _diagnostic, diagnostic_problems = self._complete_diagnostic(unit, 'diag-all-browser')

        all_problems = list(diagnostic_problems)
        for section in sections:
            session, _ = services.get_or_create_section_session(
                section=section, browser_session_key='diag-all-browser',
            )
            all_problems.append(services.ensure_first_problem(session=session))

        self.assertEqual(
            len(all_problems), len(set(all_problems)),
            f'duplicate problem(s) found across diagnostic + sections: {all_problems}',
        )

    def test_section_retry_still_avoids_diagnostic_problems_too(self):
        # Reaches NEEDS_REVIEW via 5 wrong revisions rather than a
        # successful Transfer Check, so this only needs the catalog to
        # cover diagnostic(2, one per section — the diagnostic no longer
        # stops early) + this section's first_problem(1) + the retried
        # round's new first_problem(1) = 4 distinct texts — within what a
        # 5-entry catalog can reliably provide, unlike also requiring a
        # 5th (a Transfer Check problem) on top of that.
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        Section.objects.create(unit=unit, title='セクションB', content='内容')
        _diagnostic, diagnostic_problems = self._complete_diagnostic(unit, 'diag-retry-browser')

        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='diag-retry-browser',
        )
        first_problem = services.ensure_first_problem(session=session)
        self.assertNotIn(first_problem, diagnostic_problems)
        wrong_answer = 'これは間違った解答です'
        services.submit_first_attempt(
            session=session, answer=wrong_answer, reasoning='わかりません', confidence=2,
        )
        services.submit_diagnosis(session=session, answer='わかりません')
        for _ in range(5):
            services.ensure_current_hint(session=session)
            services.submit_revision(
                session=session, answer=wrong_answer, reasoning='まだ違います', confidence=2,
            )
        session.refresh_from_db()
        self.assertEqual(session.current_state, WorkflowState.NEEDS_REVIEW)

        restarted = services.restart_for_review(section=section, browser_session_key='diag-retry-browser')
        self.assertNotIn(restarted.first_problem, diagnostic_problems)

    def test_ai_failure_fallback_avoids_a_diagnostic_problem(self):
        unit = Unit.objects.create(name='群論', is_demo=True)
        sections = [
            Section.objects.create(unit=unit, title=f'セクション{i + 1}', content='内容', order=i)
            for i in range(3)
        ]
        _diagnostic, diagnostic_problems = self._complete_diagnostic(unit, 'diag-ai-fail-browser')
        unit.is_demo = False
        unit.save(update_fields=('is_demo',))

        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch(
            'apps.math_quiz.services.generate_ai_response', side_effect=AIEngineError('down'),
        )
        self.addCleanup(response_patcher.stop)
        response_patcher.start()

        session, _ = services.get_or_create_section_session(
            section=sections[0], browser_session_key='diag-ai-fail-browser',
        )
        first_problem = services.ensure_first_problem(session=session)
        self.assertNotIn(first_problem, diagnostic_problems)

    def test_exhausted_candidate_pool_falls_back_safely_without_hanging_or_erroring(self):
        """Force genuine pool exhaustion (every catalog entry already
        excluded) and confirm build_unique_problem still returns promptly
        — an honest repeat, not an infinite loop or exception."""
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        all_entries = {
            demo_content.build_problem(section, kind='first', salt=s)[0] for s in range(4)
        }
        problem, value = demo_content.build_unique_problem(section, kind='first', exclude=all_entries)
        self.assertIn(problem, all_entries)  # honest repeat, not a crash
        self.assertIsNotNone(value)

    def test_exhausted_pool_at_the_service_layer_still_returns_promptly(self):
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        all_entries = {
            demo_content.build_problem(section, kind='first', salt=s)[0] for s in range(4)
        }
        problem = services._generate_problem(section=section, kind='first', exclude=all_entries)
        self.assertIn(problem, all_entries)

    def test_dedup_treats_whitespace_only_differences_as_the_same_problem(self):
        section = _create_section(name='正規化重複テスト単元')
        problem0, _value0 = demo_content.build_problem(section, kind='first', salt=0)
        padded = f'  {problem0}\n\n'  # same problem, incidental extra whitespace
        unique_problem, _value = demo_content.build_unique_problem(
            section, kind='first', exclude={padded},
        )
        self.assertNotEqual(unique_problem, problem0)


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


class MathCrossSectionDedupTests(TestCase):
    """Cross-section duplicate avoidance within a single course (unit): the
    same problem text must never be shown twice across different sections'
    first attempt, diagnostic quiz, and Transfer Check — see
    services._used_problems_in_unit, which every problem-generation call
    site (ensure_first_problem / _add_diagnostic_question /
    ensure_transfer_problem) now excludes against, instead of only
    checking within their own section/session as before."""

    def test_used_problems_in_unit_collects_first_transfer_and_diagnostic_problems(self):
        unit, sections = _create_unit_with_sections('横断重複収集テスト単元', 2)
        section_a, _section_b = sections
        session_a, _ = services.get_or_create_section_session(
            section=section_a, browser_session_key='collect-browser',
        )
        first_a = services.ensure_first_problem(session=session_a)
        session_a.first_problem = first_a
        transfer_a = services.ensure_transfer_problem(session=session_a)
        diagnostic = services.start_unit_diagnostic(unit=unit, browser_session_key='collect-browser')
        diagnostic_problem = diagnostic.answers.get().problem

        used = services._used_problems_in_unit(unit=unit, browser_session_key='collect-browser')
        self.assertIn(first_a, used)
        self.assertIn(transfer_a, used)
        self.assertIn(diagnostic_problem, used)

    def test_ensure_first_problem_excludes_problems_already_used_by_another_section(self):
        unit, sections = _create_unit_with_sections('セクション間重複防止テスト単元', 2)
        section_a, section_b = sections
        session_a, _ = services.get_or_create_section_session(
            section=section_a, browser_session_key='exclude-browser',
        )
        problem_a = services.ensure_first_problem(session=session_a)

        session_b, _ = services.get_or_create_section_session(
            section=section_b, browser_session_key='exclude-browser',
        )
        with patch(
            'apps.math_quiz.services._generate_problem', wraps=services._generate_problem,
        ) as spy:
            services.ensure_first_problem(session=session_b)
        _args, kwargs = spy.call_args
        self.assertIn(problem_a, kwargs['exclude'])

    def test_ensure_transfer_problem_excludes_problems_used_by_another_section(self):
        unit, sections = _create_unit_with_sections('発展問題重複防止テスト単元', 2)
        section_a, section_b = sections
        session_a, _ = services.get_or_create_section_session(
            section=section_a, browser_session_key='transfer-exclude-browser',
        )
        problem_a = services.ensure_first_problem(session=session_a)

        session_b, _ = services.get_or_create_section_session(
            section=section_b, browser_session_key='transfer-exclude-browser',
        )
        services.ensure_first_problem(session=session_b)
        with patch(
            'apps.math_quiz.services._generate_problem', wraps=services._generate_problem,
        ) as spy:
            services.ensure_transfer_problem(session=session_b)
        _args, kwargs = spy.call_args
        self.assertIn(problem_a, kwargs['exclude'])

    def test_diagnostic_quiz_excludes_problems_already_used_by_a_section_session(self):
        unit, sections = _create_unit_with_sections('診断横断重複防止テスト単元', 2)
        section_a, _section_b = sections
        session_a, _ = services.get_or_create_section_session(
            section=section_a, browser_session_key='diag-exclude-browser',
        )
        problem_a = services.ensure_first_problem(session=session_a)

        with patch(
            'apps.math_quiz.services._generate_problem', wraps=services._generate_problem,
        ) as spy:
            services.start_unit_diagnostic(unit=unit, browser_session_key='diag-exclude-browser')
        _args, kwargs = spy.call_args
        self.assertIn(problem_a, kwargs['exclude'])

    def test_cross_section_dedup_excludes_fallback_problems_from_ai_mode_generation(self):
        """AI-generated problems are checked against the same exclude set
        as the deterministic fallback — a subject-catalog problem already
        used by another section must be rejected even when AI (mis)returns
        it verbatim, and the eventual fallback pick must also honor the
        same exclude set."""
        unit = Unit.objects.create(name='群論', is_demo=False)
        section_a = Section.objects.create(unit=unit, title='セクションA', content='内容')
        section_b = Section.objects.create(unit=unit, title='セクションB', content='内容')
        session_a, _ = services.get_or_create_section_session(
            section=section_a, browser_session_key='cross-dedup-browser',
        )
        problem_a = services.ensure_first_problem(session=session_a)

        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch('apps.math_quiz.services.generate_ai_response')
        mock_response = response_patcher.start()
        self.addCleanup(response_patcher.stop)
        mock_response.return_value = json.dumps({'problem': problem_a})

        session_b, _ = services.get_or_create_section_session(
            section=section_b, browser_session_key='cross-dedup-browser',
        )
        build_patcher = patch(
            'apps.math_quiz.services.demo_content.build_unique_problem',
            wraps=demo_content.build_unique_problem,
        )
        mock_build = build_patcher.start()
        self.addCleanup(build_patcher.stop)

        services.ensure_first_problem(session=session_b)
        self.assertEqual(mock_response.call_count, 2)  # AI retried once, both matched exclude
        _args, kwargs = mock_build.call_args
        self.assertIn(problem_a, kwargs['exclude'])

    def test_no_extra_ai_call_is_made_purely_for_duplicate_checking(self):
        unit, sections = _create_unit_with_sections('AI呼び出し回数テスト単元', 2, is_demo=True)
        section_a, section_b = sections
        session_a, _ = services.get_or_create_section_session(
            section=section_a, browser_session_key='no-extra-ai-browser',
        )
        services.ensure_first_problem(session=session_a)
        session_b, _ = services.get_or_create_section_session(
            section=section_b, browser_session_key='no-extra-ai-browser',
        )
        with patch('apps.math_quiz.services.generate_ai_response') as mock_response:
            services.ensure_first_problem(session=session_b)
        mock_response.assert_not_called()  # is_demo unit: dedup is pure code, no AI involved at all

    def test_ai_problem_prompt_includes_the_existing_problem_list_without_extra_calls(self):
        """The exclude set is also handed to the AI inside its one existing
        call (not a second call) — a proactive nudge on top of the
        deterministic post-hoc exclude check, still zero extra requests."""
        unit = Unit.objects.create(name='群論AIプロンプトテスト単元', is_demo=False)
        section_a = Section.objects.create(unit=unit, title='セクションA', content='内容')
        section_b = Section.objects.create(unit=unit, title='セクションB', content='内容')
        session_a, _ = services.get_or_create_section_session(
            section=section_a, browser_session_key='prompt-browser',
        )
        problem_a = services.ensure_first_problem(session=session_a)

        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch('apps.math_quiz.services.generate_ai_response')
        mock_response = response_patcher.start()
        self.addCleanup(response_patcher.stop)
        mock_response.return_value = json.dumps({'problem': '新しい問題文'})

        session_b, _ = services.get_or_create_section_session(
            section=section_b, browser_session_key='prompt-browser',
        )
        services.ensure_first_problem(session=session_b)
        self.assertEqual(mock_response.call_count, 1)  # accepted first try, no retry needed
        _args, kwargs = mock_response.call_args
        self.assertIn(problem_a, kwargs['user_prompt'])
        self.assertIn('既出問題リスト', kwargs['user_prompt'])


class MathSameSectionResetDedupTests(TestCase):
    """Re-selecting a completed section always starts a brand-new
    SectionSession (see views._browser_section_session /
    services.restart_for_review), and SectionSession.delete() cascades to
    delete every Attempt with it — so the previous round's exact problem
    text is gone by the time a new one is generated, and the unit-wide
    exclude set (_used_problems_in_unit) can no longer see it. Without
    services._next_problem_salt, this made a section regenerate the exact
    same problem on every single reset (build_unique_problem always
    retrying salt=0 first with nothing to exclude it)."""

    def _complete_confidently(self, section, *, browser_session_key):
        """Fastest path to a finished (Mastered) round: confident+correct
        first attempt skips straight to Transfer, and a confident+correct
        Transfer Check reaches Mastered — see
        state_machine.ALLOWED_TRANSITIONS."""
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key=browser_session_key,
        )
        services.ensure_first_problem(session=session)
        answer = _correct_answer(section, kind='first')
        services.submit_first_attempt(
            session=session, answer=answer, reasoning='移項して計算しました', confidence=5,
        )
        services.ensure_transfer_problem(session=session)
        transfer_answer = _correct_answer(section, kind='transfer')
        services.submit_transfer_check(
            session=session, answer=transfer_answer, reasoning='計算しました', confidence=5,
        )
        session.refresh_from_db()
        self.assertEqual(session.current_state, WorkflowState.MASTERED)
        return session

    def test_same_section_shows_a_different_problem_after_a_reset(self):
        section = _create_section(name='リセット後重複防止テスト単元')
        session = self._complete_confidently(section, browser_session_key='reset-dedup-browser')
        first_round_problem = session.first_problem

        restarted = services.restart_for_review(section=section, browser_session_key='reset-dedup-browser')
        second_round_problem = services.ensure_first_problem(session=restarted)
        self.assertNotEqual(second_round_problem, first_round_problem)

    def test_same_section_catalog_fallback_never_repeats_the_immediately_preceding_first_problem(self):
        """restart_for_review now captures the outgoing round's own
        first_problem (and transfer_problem, if any) before it's deleted
        and passes it forward as an explicit exclude — a hard guarantee
        for the immediately-next round, not just the salt rotation's
        probabilistic variety. Regression coverage specifically for the
        2-entry fallback catalog case, where two different salts can
        otherwise land on the same one of only two possible texts."""
        unit = Unit.objects.create(name='群論', is_demo=True)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='catalog-immediate-browser',
        )
        first_round_problem = services.ensure_first_problem(session=session)
        answer = _correct_answer(section, kind='first')
        # Confident+correct skips straight to Transfer — reset right after,
        # so only first_problem (not transfer_problem) was actually used
        # this round, leaving the catalog's other entry available.
        services.submit_first_attempt(
            session=session, answer=answer, reasoning='わかりました', confidence=5,
        )

        restarted = services.restart_for_review(section=section, browser_session_key='catalog-immediate-browser')
        self.assertNotEqual(restarted.first_problem, first_round_problem)

    def test_ensure_first_problem_passes_a_nonzero_start_salt_after_a_completed_round(self):
        """Verifies the rotation mechanism directly (rather than the
        probabilistic final text) — this stays deterministic even for a
        subject with only a 2-entry fallback catalog, where the final
        chosen text isn't guaranteed to differ every single time.

        restart_for_review now generates the new round's first_problem
        eagerly (see its docstring), so that's where the call happens —
        by the time a caller's own ensure_first_problem runs afterward,
        first_problem is already set and it's a no-op."""
        section = _create_section(name='スタート塩テスト単元')
        self._complete_confidently(section, browser_session_key='start-salt-browser')

        with patch(
            'apps.math_quiz.services._generate_problem', wraps=services._generate_problem,
        ) as spy:
            services.restart_for_review(section=section, browser_session_key='start-salt-browser')
        _args, kwargs = spy.call_args
        self.assertNotEqual(kwargs['start_salt'], 0)

    def test_grading_still_works_correctly_for_a_rotated_salt_after_reset(self):
        """Critical safety check: whatever salt gets rotated to after a
        reset must stay within the range services._resolve_fallback /
        demo_content.build_hint search (0..MAX_PROBLEM_DEDUP_ATTEMPTS-1) —
        otherwise a real fallback problem would look like a genuine AI
        original and grading would break (see build_unique_problem's
        `start_salt %= MAX_PROBLEM_DEDUP_ATTEMPTS`)."""
        section = _create_section(name='ローテーション後採点テスト単元')
        self._complete_confidently(section, browser_session_key='rotate-grade-browser')

        restarted = services.restart_for_review(section=section, browser_session_key='rotate-grade-browser')
        new_problem = services.ensure_first_problem(session=restarted)
        expected_value = next(
            value
            for salt in range(demo_content.MAX_PROBLEM_DEDUP_ATTEMPTS)
            for problem, value in [demo_content.build_problem(section, kind='first', salt=salt)]
            if problem == new_problem
        )
        is_correct, explanation, _quality = services._judge(
            section=section, problem=new_problem, answer=str(expected_value), kind='first',
        )
        self.assertTrue(is_correct)
        self.assertNotIn('採点に失敗しました', explanation)

    def test_resetting_one_section_does_not_affect_another_sections_problem(self):
        unit, sections = _create_unit_with_sections('リセット影響範囲テスト単元', 2)
        section_a, section_b = sections
        session_b, _ = services.get_or_create_section_session(
            section=section_b, browser_session_key='scope-browser',
        )
        problem_b_before = services.ensure_first_problem(session=session_b)

        self._complete_confidently(section_a, browser_session_key='scope-browser')
        services.restart_for_review(section=section_a, browser_session_key='scope-browser')

        session_b.refresh_from_db()
        self.assertEqual(session_b.first_problem, problem_b_before)

    def test_no_extra_ai_call_when_regenerating_after_a_reset(self):
        section = _create_section(name='リセット後AI呼び出しテスト単元')
        self._complete_confidently(section, browser_session_key='reset-no-ai-browser')
        # restart_for_review now generates the new round's first_problem
        # eagerly (see its docstring), so that's what must stay AI-free
        # for an is_demo unit — wrap it rather than the now-redundant
        # follow-up ensure_first_problem call.
        with patch('apps.math_quiz.services.generate_ai_response') as mock_response:
            services.restart_for_review(section=section, browser_session_key='reset-no-ai-browser')
        mock_response.assert_not_called()

    def test_fallback_problem_after_reset_still_matches_the_subject(self):
        unit = Unit.objects.create(name='フーリエ変換', is_demo=True)
        section = Section.objects.create(unit=unit, title='基本の計算', content='内容')
        self._complete_confidently(section, browser_session_key='reset-subject-browser')

        restarted = services.restart_for_review(section=section, browser_session_key='reset-subject-browser')
        new_problem = services.ensure_first_problem(session=restarted)
        # Membership in the subject's own catalog is the precise check;
        # looks_like_subject is a much cruder AI-sanity heuristic that
        # isn't guaranteed to recognize every one of a catalog's own
        # problems (e.g. one entry's text doesn't literally contain any of
        # its catalog's keyword list) — not what's being tested here.
        catalog_problems = {entry['problem'] for entry in demo_content.AI_FALLBACK_PROBLEMS['フーリエ変換']['problems']}
        self.assertIn(new_problem, catalog_problems)

    def test_ai_mode_falls_back_with_a_rotated_salt_when_ai_fails_after_reset(self):
        """A genuine AI-original problem can't be checked against a
        deleted prior round by text at all (there's nothing deterministic
        to compare), so the meaningful guarantee in AI mode is: when the
        AI call itself fails and generation drops to the deterministic
        fallback, that fallback must still be rotated — not always retry
        salt=0 and risk reproducing the exact fallback problem shown
        before the reset."""
        unit = Unit.objects.create(name='群論', is_demo=False)
        section = Section.objects.create(unit=unit, title='セクションA', content='内容')
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='ai-fail-rotate-browser',
        )

        not_configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=False)
        not_configured_patcher.start()
        services.ensure_first_problem(session=session)
        not_configured_patcher.stop()
        services._update_concept_mastery(
            section=section, browser_session_key='ai-fail-rotate-browser', is_correct=True, confidence=5,
        )
        services.reset_section_session(section=section, browser_session_key='ai-fail-rotate-browser')
        restarted, _ = services.get_or_create_section_session(
            section=section, browser_session_key='ai-fail-rotate-browser',
        )

        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch(
            'apps.math_quiz.services.generate_ai_response', side_effect=Exception('AI down'),
        )
        self.addCleanup(response_patcher.stop)
        response_patcher.start()

        build_patcher = patch(
            'apps.math_quiz.services.demo_content.build_unique_problem',
            wraps=demo_content.build_unique_problem,
        )
        mock_build = build_patcher.start()
        self.addCleanup(build_patcher.stop)

        services.ensure_first_problem(session=restarted)
        _args, kwargs = mock_build.call_args
        self.assertNotEqual(kwargs['start_salt'], 0)


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
        self.assertContains(response, 'Solve this without AI hints')


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


class MathTeachBackSubjectMatchTests(TestCase):
    """Teach-Back must always be grounded in the actual problem shown for
    the current section, never a generic or wrong-subject question —
    regression coverage for a reported bug where a differential-equations
    section showed a linear-equation ("6x - 1 = 47 の両辺から...")
    Teach-Back question. See demo_content.teach_back_question /
    evaluate_teach_back_answer and services._generate_teach_back_question."""

    def _reach_targeted_teach_back(self, section, *, browser_session_key):
        """Confident-but-wrong first attempt -> high misconception
        probability -> after a correct revision, decide_teach_back_level
        picks TARGETED (see mastery.decide_teach_back_level), which is the
        only Teach-Back level that calls _generate_teach_back_question."""
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key=browser_session_key,
        )
        problem = services.ensure_first_problem(session=session)
        wrong_answer = str(int(_correct_answer(section, kind='first')) + 1000)
        services.submit_first_attempt(
            session=session, answer=wrong_answer, reasoning='絶対これだと思います', confidence=5,
        )
        services.submit_diagnosis(session=session, answer='公式を間違えたと思います。')
        services.ensure_current_hint(session=session)
        correct_answer = _correct_answer(section, kind='first')
        services.submit_revision(
            session=session, answer=correct_answer, reasoning='考え直しました', confidence=4,
        )
        session.refresh_from_db()
        self.assertEqual(session.current_state, WorkflowState.TEACH_BACK)
        self.assertEqual(session.teach_back_level, 'TARGETED')
        return session, problem

    def test_teach_back_question_for_differential_equations_matches_the_actual_problem(self):
        unit = Unit.objects.create(name='微分方程式', is_demo=True)
        section = Section.objects.create(unit=unit, title='二階線形微分方程式', content='内容')
        session, problem = self._reach_targeted_teach_back(section, browser_session_key='diffeq-browser')

        current = services.current_teach_back(session=session)
        self.assertIn(problem, current.question)
        self.assertNotIn('移項', current.question)
        self.assertNotIn('両辺', current.question)
        self.assertNotIn('6x', current.question)

    def test_teach_back_question_for_fourier_transform_matches_the_actual_problem(self):
        unit = Unit.objects.create(name='フーリエ変換', is_demo=True)
        section = Section.objects.create(unit=unit, title='基本の計算', content='内容')
        session, problem = self._reach_targeted_teach_back(section, browser_session_key='fourier-browser')

        current = services.current_teach_back(session=session)
        self.assertIn(problem, current.question)
        self.assertNotIn('移項', current.question)
        self.assertNotIn('両辺', current.question)

    def test_teach_back_question_for_plain_linear_equation_still_matches_the_actual_problem(self):
        """Non-catalog subjects (e.g. the existing demo linear-equation
        content) must also quote the actual problem shown, not a
        re-derived equation that could disagree with it once duplicate-
        avoidance (build_unique_problem) is in play."""
        section = _create_section(name='一次方程式Teach-Back照合テスト単元')
        session, problem = self._reach_targeted_teach_back(section, browser_session_key='linear-browser')

        current = services.current_teach_back(session=session)
        self.assertIn(problem, current.question)

    def test_evaluate_teach_back_answer_uses_catalog_keywords_for_a_matching_subject(self):
        unit = Unit.objects.create(name='フーリエ変換', is_demo=True)
        section = Section.objects.create(unit=unit, title='基本の計算', content='内容')
        evaluation, _feedback, _follow_up = demo_content.evaluate_teach_back_answer(
            section, '周波数成分をもとに変換の意味を考えて計算しました',
        )
        self.assertEqual(evaluation, 'CLEAR_UNDERSTANDING')

    def test_evaluate_teach_back_answer_partial_feedback_does_not_mention_unrelated_subject_terms(self):
        unit = Unit.objects.create(name='フーリエ変換', is_demo=True)
        section = Section.objects.create(unit=unit, title='基本の計算', content='内容')
        _evaluation, feedback, _follow_up = demo_content.evaluate_teach_back_answer(
            section, 'なんとなく計算しただけです',
        )
        self.assertNotIn('移項', feedback)
        self.assertNotIn('両辺', feedback)

    def test_targeted_teach_back_question_uses_exactly_one_ai_call_with_full_context(self):
        """No extra AI call is added purely to keep Teach-Back on-subject —
        the existing single Targeted-question call is just given richer
        context (subject, section, actual problem) in its prompt."""
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch(
            'apps.math_quiz.services.generate_ai_response', side_effect=_fake_generate_ai_response,
        )
        mock_response = response_patcher.start()
        self.addCleanup(response_patcher.stop)

        unit = Unit.objects.create(name='微分方程式AIテスト単元', is_demo=False)
        section = Section.objects.create(unit=unit, title='二階線形微分方程式', content='内容')
        session, _ = services.get_or_create_section_session(
            section=section, browser_session_key='diffeq-ai-browser',
        )
        services.ensure_first_problem(session=session)
        services.submit_first_attempt(
            session=session, answer='WRONG_ANSWER', reasoning='絶対これだと思います', confidence=2,
        )
        services.submit_diagnosis(session=session, answer='わかりません')
        # Escalate to hint level 4 via three wrong revisions — this reaches
        # TARGETED through decide_teach_back_level's hint_level_used >= 4
        # branch, which (unlike the misconception-probability branch)
        # doesn't depend on optional fields the mocked AI response omits.
        for _ in range(3):
            services.ensure_current_hint(session=session)
            services.submit_revision(
                session=session, answer='WRONG_ANSWER', reasoning='まだ違う考え方です', confidence=2,
            )
        hint = services.ensure_current_hint(session=session)
        self.assertEqual(hint.level, 4)
        mock_response.reset_mock()
        services.submit_revision(
            session=session, answer='CORRECT_ANSWER', reasoning='考え直しました', confidence=4,
        )
        session.refresh_from_db()
        self.assertEqual(session.teach_back_level, 'TARGETED')

        teach_back_calls = [
            call for call in mock_response.call_args_list
            if 'まだ誤解が残っていないか' in call.kwargs['system_prompt']
        ]
        self.assertEqual(len(teach_back_calls), 1)
        user_prompt = teach_back_calls[0].kwargs['user_prompt']
        self.assertIn('微分方程式AIテスト単元', user_prompt)
        self.assertIn('二階線形微分方程式', user_prompt)
        self.assertIn(session.first_problem, user_prompt)


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
        self.assertEqual((label, tone), ('Time for a recheck', 'warning'))

    def test_overconfident_in_progress_shows_calibration_pill(self):
        record = ConceptMastery(confidence_calibration=ConfidenceCalibration.OVERCONFIDENT)
        label, tone = mastery.classify_section_status(
            section_state=WorkflowState.GUIDED_REVISION, concept_mastery=record,
        )
        self.assertEqual((label, tone), ('May be overconfident', 'muted'))

    def test_underconfident_in_progress_shows_calibration_pill(self):
        record = ConceptMastery(confidence_calibration=ConfidenceCalibration.UNDERCONFIDENT)
        label, tone = mastery.classify_section_status(
            section_state=WorkflowState.FIRST_ATTEMPT, concept_mastery=record,
        )
        self.assertEqual((label, tone), ('May be underconfident', 'muted'))

    def test_not_started_shows_not_started_pill(self):
        label, tone = mastery.classify_section_status(section_state=None, concept_mastery=None)
        self.assertEqual((label, tone), ('Not started', 'muted'))

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
        self.assertContains(response, 'May be overconfident')


class MathI18nTests(TestCase):
    """Minimal ja/en language switch — see config/settings.py
    (LocaleMiddleware, LANGUAGES, LOCALE_PATHS) and config/urls.py
    (django.conf.urls.i18n's set_language view). Translation itself is
    Django's own gettext/gettext_lazy machinery; these tests only check
    the switch works end-to-end, not the completeness of the wordlist."""

    def test_english_is_the_default_language(self):
        # LANGUAGE_CODE = 'en' (see config/settings.py) — a fresh visitor
        # with no saved language preference and no Accept-Language header
        # (as here — the test client sends none) gets English by default.
        response = self.client.get(reverse('math_quiz:home'))
        self.assertContains(response, 'Math')

    def test_japanese_can_still_be_selected(self):
        # The switch mechanism itself must still work even though its UI
        # is hidden — see test_language_switcher_ui_is_hidden_from_users.
        self.client.post(reverse('set_language'), {'language': 'ja', 'next': reverse('math_quiz:home')})
        response = self.client.get(reverse('math_quiz:home'))
        self.assertContains(response, '数学')

    def test_a_browsers_japanese_accept_language_does_not_override_the_english_default(self):
        # Regression: LocaleMiddleware checks Accept-Language before
        # falling back to LANGUAGE_CODE, so a browser with Japanese OS/
        # browser settings got Japanese regardless of LANGUAGE_CODE='en'
        # for any visitor who'd never explicitly chosen a language — see
        # config.middleware.IgnoreBrowserLanguageMiddleware.
        client = Client(HTTP_ACCEPT_LANGUAGE='ja,ja-JP;q=0.9,en;q=0.8')
        response = client.get(reverse('math_quiz:home'))
        self.assertContains(response, 'Math')
        self.assertNotContains(response, '数学')

    def test_an_explicit_past_choice_still_wins_over_the_english_default(self):
        # The middleware above must only skip Accept-Language when there's
        # no saved choice yet — an explicit past selection (the
        # django_language cookie) always wins, browser language or not.
        client = Client(HTTP_ACCEPT_LANGUAGE='ja,ja-JP;q=0.9,en;q=0.8')
        client.post(reverse('set_language'), {'language': 'ja', 'next': reverse('math_quiz:home')})
        response = client.get(reverse('math_quiz:home'))
        self.assertContains(response, '数学')

    def test_language_switcher_ui_is_hidden_from_users(self):
        # 'lang-switch' alone isn't a safe marker — the CSS rule for it
        # still lives in _style.html regardless of whether the widget
        # renders, so check for the widget's own actual markup instead.
        response = self.client.get(reverse('math_quiz:home'))
        self.assertNotContains(response, 'name="language" value="ja"')
        self.assertNotContains(response, 'name="language" value="en"')

    def test_english_can_be_selected(self):
        self.client.post(reverse('set_language'), {'language': 'en', 'next': reverse('math_quiz:home')})
        response = self.client.get(reverse('math_quiz:home'))
        self.assertContains(response, 'Math')

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

    def test_generate_sections_does_not_force_japanese_regardless_of_selected_language(self):
        """Regression: the user_prompt used to hardcode "（日本語での説明）"
        directly next to the generation request — a much more specific,
        nearby instruction than the generic "Answer in English." appended
        to the system_prompt, so the model reliably followed the hardcoded
        Japanese one instead even with English selected. See
        services.generate_sections."""
        configured_patcher = patch('apps.math_quiz.services.is_ai_configured', return_value=True)
        self.addCleanup(configured_patcher.stop)
        configured_patcher.start()
        response_patcher = patch('apps.math_quiz.services.generate_ai_response')
        self.addCleanup(response_patcher.stop)
        mock_response = response_patcher.start()
        mock_response.return_value = json.dumps({'sections': [{'title': 'What Is Probability?', 'content': '...'}]})

        unit = Unit.objects.create(name='English Language Test Unit', is_demo=False)
        with translation.override('en'):
            services.generate_sections(unit, unit.name)
        user_prompt = mock_response.call_args.kwargs['user_prompt']
        self.assertNotIn('日本語', user_prompt)
        self.assertIn('Answer in English.', mock_response.call_args.kwargs['system_prompt'])


class MathLatexifyFilterTests(TestCase):
    """Regression coverage for a reported bug: AI-generated problem text
    mixes Japanese prose with raw, undelimited LaTeX (e.g. "\\frac{...}"),
    which was displayed as literal text instead of being rendered as math
    — see templatetags.math_extras.latexify."""

    def test_wraps_a_fraction(self):
        out = latexify(r"関数 f(x)=\frac{x^2\,e^{x}}{1+x^3} の x=1 における導関数 f'(1) を求めなさい。")
        self.assertIn(r'\(f(x)=\frac{x^2\,e^{x}}{1+x^3}\)', out)

    def test_does_not_double_wrap_a_run_the_ai_already_delimited(self):
        # Regression: the AI sometimes already wraps its own LaTeX in \( \)
        # — re-wrapping that produced "\(\(\frac{...}\)\)", which KaTeX
        # can't parse (its inner \( is just literal text in math mode),
        # and rendered as raw red error text instead of a formula.
        out = latexify(r'比例式 \(\frac{7}{x}=\frac{21}{6}\) が成り立つとき、x の値を求めなさい。')
        self.assertIn(r'\(\frac{7}{x}=\frac{21}{6}\)', out)
        self.assertNotIn(r'\(\(', out)
        self.assertNotIn(r'\)\)', out)

    def test_leaves_an_already_bracket_delimited_run_alone(self):
        out = latexify(r'\[\frac{1}{2}\] を計算しなさい。')
        self.assertIn(r'\[\frac{1}{2}\]', out)
        self.assertNotIn(r'\(\[', out)

    def test_leaves_an_already_dollar_delimited_run_alone(self):
        out = latexify(r'$$\frac{1}{2}$$ を計算しなさい。')
        self.assertIn(r'$$\frac{1}{2}$$', out)
        self.assertNotIn(r'\($$', out)

    def test_wraps_a_superscript(self):
        self.assertIn(r'\(x^2\)', latexify('x^2 を計算しなさい。'))

    def test_wraps_a_subscript(self):
        self.assertIn(r'\(x_1\)', latexify('x_1 の値を求めなさい。'))

    def test_wraps_e_to_the_x(self):
        self.assertIn(r'\(e^{x}\)', latexify('e^{x} を微分しなさい。'))

    def test_plain_linear_equation_is_left_completely_unchanged(self):
        # No actual LaTeX commands here — must render exactly as it does
        # today (plain monospace text), not get wrapped/re-styled.
        self.assertEqual(latexify('6x - 7 = -31'), '6x - 7 = -31')

    def test_plain_japanese_only_text_is_untouched(self):
        text = 'この単元の内容を確認しましょう。'
        self.assertEqual(latexify(text), text)

    def test_multiple_math_runs_in_one_japanese_sentence(self):
        out = latexify(r'x^2 を計算し、次に \frac{1}{2} を求めなさい。')
        self.assertIn(r'\(x^2\)', out)
        self.assertIn(r'\(\frac{1}{2}\)', out)

    def test_html_is_escaped_not_left_executable(self):
        out = latexify('<script>alert(1)</script>')
        self.assertNotIn('<script>', out)
        self.assertIn('&lt;script&gt;', out)

    def test_none_is_rendered_as_empty_string(self):
        self.assertEqual(latexify(None), '')
