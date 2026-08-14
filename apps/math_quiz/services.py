import datetime
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.ai_engine.client import generate_ai_response, is_ai_configured

from . import ai_prompts, demo_content, mastery
from .mastery import CONFIDENT_THRESHOLD
from .models import (
    Attempt,
    ConceptMastery,
    HintUsage,
    MasteryState,
    Section,
    SectionSession,
    TeachBackAttempt,
    TransferAttempt,
    Unit,
    UnitDiagnosticAnswer,
    UnitDiagnosticSession,
    UnitMaterial,
)
from .state_machine import WorkflowState, hints_allowed, validate_transition

MAX_HINT_LEVEL = demo_content.MAX_HINT_LEVEL
MIN_DIAGNOSTIC_QUESTIONS = 2
MAX_DIAGNOSTIC_QUESTIONS = 5
REVIEW_INTERVAL = datetime.timedelta(hours=24)  # first spaced-recheck gap; queue UI itself is P2


def _ai_mode(unit):
    """Real AI generation is used for every unit except the no-AI demo
    unit, and only while a provider is actually configured. Any AI call
    that fails falls back to the deterministic demo_content generators —
    see each _generate_*/_judge helper below."""
    return not unit.is_demo and is_ai_configured()


def _ai_json(*, system_prompt, user_prompt, response_schema, files=None):
    # Every AI call goes through here, so this one spot is enough to make
    # all AI-generated content (problems, judging, hints, diagnosis,
    # verification, Teach-Back, Transfer, feedback) follow the learner's
    # currently active language — see ai_prompts.LANGUAGE_INSTRUCTIONS.
    language_instruction = ai_prompts.LANGUAGE_INSTRUCTIONS.get(
        translation.get_language(), ai_prompts.LANGUAGE_INSTRUCTIONS['ja'],
    )
    text = generate_ai_response(
        system_prompt=f'{system_prompt}\n{language_instruction}',
        user_prompt=user_prompt, response_schema=response_schema,
        files=files,
    )
    return json.loads(text)


def _unit_material_files(unit):
    """(bytes, mime_type) pairs for every UnitMaterial added to this unit
    after creation (see views.add_unit_material / services.add_unit_materials).
    Doesn't include Unit.file itself — the one existing caller that passes
    `files` explicitly (add_unit, at creation time) already includes it in
    that list, so re-reading it here would attach it twice."""
    result = []
    for material in unit.materials.all():
        material.file.open('rb')
        try:
            content = material.file.read()
        finally:
            material.file.close()
        result.append((content, material.content_type or 'application/octet-stream'))
    return result


@transaction.atomic
def add_unit_materials(*, unit, files):
    """Persists each uploaded file as a UnitMaterial row — no AI call
    here. generate_sections is what actually reads these (via
    _unit_material_files), whenever it happens to run."""
    for uploaded in files:
        UnitMaterial.objects.create(
            unit=unit, file=uploaded, content_type=getattr(uploaded, 'content_type', '') or '',
        )


@transaction.atomic
def generate_sections(unit, name, files=None):
    """AI auto-generation when configured (reading the uploaded files'
    contents, if any — `files` is a list of `(file_bytes, mime_type)`
    pairs, merged with any UnitMaterial already saved for this unit — see
    _unit_material_files, so a course's full accumulated reference
    material is always considered, not just whatever one caller happened
    to pass); a fixed, deterministic section shape otherwise.

    A course must never end up with zero sections — that's a dead end
    with no retry path in the UI. So any problem with the AI call (a
    timeout, a malformed response, a network error, anything) falls
    back to the deterministic demo_content generator, which cannot
    fail. The `except Exception` here is intentionally broad: this is
    the one external-service boundary where "unexpected error type"
    must never escape and leave an empty, orphaned course behind.
    """
    sections_data = None
    if not unit.is_demo and is_ai_configured():
        try:
            all_files = list(files or []) + _unit_material_files(unit)
            data = _ai_json(
                system_prompt=ai_prompts.SECTIONS_SYSTEM_PROMPT,
                user_prompt=(
                    f'単元名: {name}\n\nこの単元を学ぶ上で必要なセクションを、タイトルと内容'
                    '（日本語での説明）の組でJSON形式で答えてください。ファイルが添付されている'
                    '場合は、そのすべての内容を踏まえてセクション構成を決めてください。'
                ),
                response_schema=ai_prompts.SECTIONS_SCHEMA,
                files=all_files,
            )
            candidate = data['sections']
            if isinstance(candidate, list) and candidate and all(
                isinstance(item, dict) and item.get('title') for item in candidate
            ):
                sections_data = candidate
        except Exception:
            sections_data = None

    if not sections_data:
        filename = getattr(unit.file, 'name', None) if unit.file else None
        sections_data = demo_content.build_sections(name, filename=filename)

    for order, section in enumerate(sections_data):
        Section.objects.create(
            unit=unit,
            title=section.get('title', f'セクション{order + 1}'),
            content=section.get('content', ''),
            order=order,
        )


@transaction.atomic
def ensure_sample_unit():
    """A pre-populated, non-deletable course so the platform never looks empty."""
    unit, created = Unit.objects.get_or_create(
        name='一次方程式（サンプル）', defaults={'is_demo': True},
    )
    if created:
        generate_sections(unit, unit.name)
    return unit


def unit_progress(*, unit, browser_session_key):
    """(mastered_sections, total_sections, percent, is_complete) for one course."""
    total = unit.sections.count()
    mastered = 0
    if browser_session_key and total:
        mastered = SectionSession.objects.filter(
            section__unit=unit,
            browser_session_key=browser_session_key,
            current_state=WorkflowState.MASTERED,
        ).count()
    percent = round(mastered / total * 100) if total else 0
    return mastered, total, percent, bool(total) and mastered == total


def _next_state_after_evaluation(*, is_correct, confidence):
    if is_correct and confidence >= CONFIDENT_THRESHOLD:
        return WorkflowState.TRANSFER_TASK
    if is_correct:
        return WorkflowState.VERIFICATION
    return WorkflowState.DIAGNOSIS


def get_or_create_section_session(*, section, browser_session_key):
    return SectionSession.objects.get_or_create(
        section=section,
        browser_session_key=browser_session_key,
    )


def reset_section_session(*, section, browser_session_key):
    SectionSession.objects.filter(section=section, browser_session_key=browser_session_key).delete()


@transaction.atomic
def restart_for_review(*, section, browser_session_key):
    """Re-selecting a section always starts completely fresh — nothing
    about the previous round carries over.

    Note this deliberately does NOT touch ConceptMastery: the durable
    learner model (unlike SectionSession) is meant to accumulate evidence
    across resets, not reset with them.

    The outgoing session's own first_problem is captured before it's
    deleted (SectionSession.delete() cascades to its Attempts too, so
    that text would otherwise be unrecoverable) and generation of the new
    round's first_problem is done right here, passing it as an extra
    exclude — this is the one case _used_problems_in_unit can never see
    on its own, since the row it would have read is gone by the time
    anything downstream asks. _next_problem_salt's salt rotation still
    covers everything _used_problems_in_unit can't guarantee beyond this
    immediate case (e.g. a small fallback catalog exhausting its couple
    of variants after several resets)."""
    previous = SectionSession.objects.filter(
        section=section, browser_session_key=browser_session_key,
    ).first()
    previous_problems = set()
    if previous is not None:
        previous_problems = {p for p in (previous.first_problem, previous.transfer_problem) if p}
    reset_section_session(section=section, browser_session_key=browser_session_key)
    restarted = get_or_create_section_session(section=section, browser_session_key=browser_session_key)[0]
    if previous_problems:
        ensure_first_problem(session=restarted, extra_exclude=previous_problems)
    return restarted


def get_concept_mastery(*, section, browser_session_key):
    record, _created = ConceptMastery.objects.get_or_create(
        section=section, browser_session_key=browser_session_key,
    )
    return record


@transaction.atomic
def _update_concept_mastery(*, section, browser_session_key, **signals):
    """Applies one event's worth of evidence to the durable learner model.
    Called as a side effect from the workflow functions below. Accepted
    signal keys (all optional): is_correct, confidence, misconception_type,
    misconception_probability, hint_level, transfer_success, mastery_state.
    """
    get_concept_mastery(section=section, browser_session_key=browser_session_key)
    record = ConceptMastery.objects.select_for_update().get(
        section=section, browser_session_key=browser_session_key,
    )
    now = timezone.now()
    record.last_attempt_at = now
    if record.mastery_state == MasteryState.NOT_STARTED:
        record.mastery_state = MasteryState.IN_PROGRESS

    if 'is_correct' in signals and 'confidence' in signals:
        record.attempt_count += 1
        record.confidence_calibration = mastery.classify_confidence_calibration(
            is_correct=bool(signals['is_correct']), confidence=signals['confidence'],
        )
        # Exponential smoothing so one lucky/unlucky attempt doesn't swing
        # the score wildly — it nudges toward the latest outcome instead.
        target = 100 if signals['is_correct'] else 0
        record.knowledge_score += (target - record.knowledge_score) * 0.5

    if signals.get('misconception_type'):
        record.misconception_type = signals['misconception_type']
    if signals.get('misconception_probability') is not None:
        record.misconception_probability = signals['misconception_probability']

    if 'hint_level' in signals:
        level = signals['hint_level']
        record.hint_count = max(record.hint_count, level)
        record.hint_dependency += (level - record.hint_dependency) * 0.5

    if 'teach_back_score' in signals:
        record.teach_back_score = signals['teach_back_score']

    if 'transfer_success' in signals:
        if signals['transfer_success']:
            record.successful_transfer_count += 1
            record.transfer_score = 100
        else:
            record.failed_transfer_count += 1
            record.transfer_score = 0

    if 'mastery_state' in signals:
        record.mastery_state = signals['mastery_state']
        if signals['mastery_state'] == MasteryState.MASTERED:
            record.last_mastered_at = now
            record.review_due_at = now + REVIEW_INTERVAL

    record.mastery_score = mastery.compute_mastery_score(concept_mastery=record)
    record.save()
    return record


def _used_problems_in_unit(*, unit, browser_session_key):
    """Every problem text already shown to this browser anywhere in this
    unit — across every section and every generation phase (first
    attempt, diagnostic quiz, transfer check) — so a newly generated
    problem never exactly repeats one already used elsewhere in the same
    course. Built entirely from existing SectionSession/
    UnitDiagnosticAnswer data; no new table."""
    pairs = SectionSession.objects.filter(
        section__unit=unit, browser_session_key=browser_session_key,
    ).values_list('first_problem', 'transfer_problem')
    used = {problem for pair in pairs for problem in pair if problem}
    used.update(
        UnitDiagnosticAnswer.objects.filter(
            session__unit=unit, session__browser_session_key=browser_session_key,
        ).values_list('problem', flat=True)
    )
    return used


def _generate_problem(*, section, kind, reference_problem=None, exclude=(), start_salt=0):
    """kind is 'first', 'transfer', or 'diagnostic'. AI mode asks for a
    fresh problem (or, for 'transfer', a same-concept variant of
    `reference_problem`); demo mode/failure falls back to the
    deterministic generator — safe because nothing has been judged
    against this problem yet.

    `exclude` is the set of problem texts already used elsewhere in this
    session — the result never exactly matches one of them (AI output
    isn't deterministic, so a plain retry is enough there; the
    deterministic fallback tries a few seeded variants — see
    demo_content.build_unique_problem). `start_salt` only affects that
    deterministic fallback — see _next_problem_salt."""
    exclude = set(exclude)
    # Compared via normalize_problem_text, not raw equality, so an
    # AI-returned problem that only differs from something already used by
    # incidental whitespace still counts as a duplicate — see
    # demo_content.normalize_problem_text.
    normalized_exclude = {demo_content.normalize_problem_text(item) for item in exclude}
    # Telling the AI what's already been used (in the same call it's
    # already making — no extra request) lets it dodge a collision on its
    # own; the exclude check below still catches it deterministically if
    # the AI includes it anyway, so this is a pure improvement, not a
    # dependency.
    exclude_note = ''
    if exclude:
        listed = '\n'.join(f'- {text}' for text in sorted(exclude))
        exclude_note = f'\n既出問題リスト（これらと重複しない新しい問題にすること）:\n{listed}'
    if _ai_mode(section.unit):
        for _attempt in range(2):
            try:
                if kind == 'transfer':
                    data = _ai_json(
                        system_prompt=ai_prompts.TRANSFER_PROBLEM_SYSTEM_PROMPT,
                        user_prompt=(
                            f'セクション: {section.title}\n元の問題: {reference_problem or ""}{exclude_note}'
                        ),
                        response_schema=ai_prompts.TRANSFER_PROBLEM_SCHEMA,
                    )
                else:
                    data = _ai_json(
                        system_prompt=ai_prompts.PROBLEM_SYSTEM_PROMPT,
                        user_prompt=(
                            f'単元: {section.unit.name}\nセクション: {section.title}\n'
                            f'セクションの内容: {section.content}{exclude_note}'
                        ),
                        response_schema=ai_prompts.PROBLEM_SCHEMA,
                    )
                problem = data['problem']
                # A technically successful call doesn't guarantee the problem
                # actually matches the course's subject (AI can hallucinate or
                # degenerate into a generic problem) — looks_like_subject is a
                # cheap sanity net that catches an obvious mismatch before
                # trusting the AI output; see demo_content.looks_like_subject.
                if (
                    isinstance(problem, str) and problem.strip()
                    and demo_content.looks_like_subject(section, problem)
                    and demo_content.normalize_problem_text(problem) not in normalized_exclude
                ):
                    return problem
            except Exception:
                break  # a hard failure won't be fixed by retrying — go straight to the fallback
    return demo_content.build_unique_problem(section, kind=kind, exclude=exclude, start_salt=start_salt)[0]


def _next_problem_salt(*, section, browser_session_key):
    """A deterministic, ever-growing offset used to rotate which
    deterministic problem variant a fresh round starts from (see
    demo_content.build_unique_problem's `start_salt`).

    Re-selecting a completed section always starts a brand-new
    SectionSession (see restart_for_review), and SectionSession.delete()
    cascades to delete every Attempt row with it — so the previous
    round's exact problem text is gone by the time this one is generated,
    and _used_problems_in_unit can no longer exclude it. Without this,
    build_unique_problem would always retry salt=0 first and regenerate
    the byte-identical problem every single time a section is reset.

    ConceptMastery, unlike SectionSession, is deliberately never touched
    by a reset (see restart_for_review's docstring) — its attempt_count
    keeps growing across rounds, so using it here rotates the starting
    salt on every reset without needing any new stored data. 0 for a
    section that has never been attempted (no history to rotate away
    from, and no ConceptMastery row yet)."""
    record = ConceptMastery.objects.filter(
        section=section, browser_session_key=browser_session_key,
    ).first()
    return record.attempt_count if record else 0


def _resolve_fallback(section, *, kind, problem):
    """If `problem` exactly matches one of the small number of
    deterministic fallback variants for (section, kind) — see
    demo_content.build_problem's `salt` — returns
    (salt, expected_value, correct_note, wrong_note) for that variant.
    Returns None if `problem` matches none of them, i.e. it's a genuine
    AI original. Checking every variant (not just salt=0) is what lets
    duplicate-avoidance (demo_content.build_unique_problem) pick a
    different variant at generation time without breaking this
    AI-vs-fallback detection."""
    for salt in range(demo_content.MAX_PROBLEM_DEDUP_ATTEMPTS):
        candidate_problem, candidate_value = demo_content.build_problem(section, kind=kind, salt=salt)
        if candidate_problem == problem:
            correct_note, wrong_note = demo_content.fallback_notes(section, kind=kind, salt=salt)
            return salt, candidate_value, correct_note, wrong_note
    return None


def _judge(*, section, problem, answer, kind, reasoning=''):
    """Returns (is_correct, explanation, reasoning_quality). reasoning_quality
    is evidence about how well the learner's stated explanation supports
    their answer — not a claim of reading their actual thought process
    (see ai_prompts.JUDGE_SYSTEM_PROMPT and mastery.classify_reasoning_quality_heuristic).

    The demo grader's "expected value" is only valid if `problem` is
    actually one of demo_content's deterministic variants for this
    (section, kind) — see _resolve_fallback — which is true in demo mode,
    and also true in AI mode whenever problem generation itself fell back
    to demo_content (e.g. AI was configured but the call failed). Only
    when the problem text matches no known variant (a genuine AI
    original) do we require AI judging — and a failed AI judge call there
    must not silently fall back to demo grading (comparing against a
    completely unrelated equation), so it reports the failure instead."""
    fallback = _resolve_fallback(section, kind=kind, problem=problem)
    if _ai_mode(section.unit) and fallback is None:
        try:
            user_prompt = f'問題: {problem}\n学習者の解答: {answer}'
            if reasoning:
                user_prompt += f'\n学習者の考え方の説明: {reasoning}'
            data = _ai_json(
                system_prompt=ai_prompts.JUDGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=ai_prompts.JUDGE_SCHEMA,
            )
            quality = str(data.get('reasoning_quality', '')).upper()
            return data['is_correct'], data['explanation'], quality
        except Exception as exc:
            return None, f'採点に失敗しました（{exc}）。', ''
    _salt, demo_expected_value, correct_note, wrong_note = fallback or (0, None, None, None)
    is_correct, explanation = demo_content.judge_answer(
        answer=answer, expected_value=demo_expected_value,
        correct_note=correct_note, wrong_note=wrong_note,
    )
    quality = (
        mastery.classify_reasoning_quality_heuristic(reasoning=reasoning, is_correct=bool(is_correct))
        if reasoning else ''
    )
    return is_correct, explanation, quality


def _diagnostic_candidate_sections(unit):
    return list(unit.sections.all()[:MAX_DIAGNOSTIC_QUESTIONS])


def _diagnostic_should_stop(results):
    """results: is_correct values (oldest first) for every diagnostic
    question answered so far in this session. Stops as soon as the two
    most recent answers agree — a consistent (rather than mixed) signal
    is treated as diagnostic enough, so the quiz doesn't ask more
    questions than it needs to. Never considered before
    MIN_DIAGNOSTIC_QUESTIONS answers exist; the caller separately caps at
    MAX_DIAGNOSTIC_QUESTIONS regardless of this."""
    if len(results) < MIN_DIAGNOSTIC_QUESTIONS:
        return False
    return results[-1] == results[-2]


def _add_diagnostic_question(*, diagnostic, section, order):
    exclude = _used_problems_in_unit(unit=diagnostic.unit, browser_session_key=diagnostic.browser_session_key)
    problem = _generate_problem(section=section, kind='diagnostic', exclude=exclude)
    UnitDiagnosticAnswer.objects.create(session=diagnostic, section=section, order=order, problem=problem)


@transaction.atomic
def start_unit_diagnostic(*, unit, browser_session_key):
    """Always a fresh quiz: one problem drawn from each of the course's
    sections, to gauge current understanding of the whole subject — its
    length adapts (see MIN_/MAX_DIAGNOSTIC_QUESTIONS and
    _diagnostic_should_stop) instead of always asking a fixed count, and
    only the first question is created here; submit_unit_diagnostic_answer
    decides whether to add another after each answer. Any previous
    attempt (finished or not) for this browser is discarded — the
    diagnostic resets every time the learner (re)enters the course."""
    UnitDiagnosticSession.objects.filter(unit=unit, browser_session_key=browser_session_key).delete()
    diagnostic = UnitDiagnosticSession.objects.create(unit=unit, browser_session_key=browser_session_key)
    sections = _diagnostic_candidate_sections(unit)
    if sections:
        _add_diagnostic_question(diagnostic=diagnostic, section=sections[0], order=0)
    else:
        diagnostic.completed_at = timezone.now()
        diagnostic.save(update_fields=('completed_at',))
    return diagnostic


def get_or_create_unit_diagnostic(*, unit, browser_session_key):
    """Fetches the current diagnostic attempt without resetting it — used
    to resume an in-progress or just-finished quiz. Deciding *when* to
    start a fresh one is the caller's job (see views.unit_detail)."""
    diagnostic = UnitDiagnosticSession.objects.filter(
        unit=unit, browser_session_key=browser_session_key,
    ).first()
    if diagnostic is None:
        diagnostic = start_unit_diagnostic(unit=unit, browser_session_key=browser_session_key)
    return diagnostic


@transaction.atomic
def submit_unit_diagnostic_answer(*, diagnostic, answer_id, answer):
    locked = UnitDiagnosticSession.objects.select_for_update().get(pk=diagnostic.pk)
    if locked.completed_at is not None:
        raise ValidationError(_('この診断クイズはすでに完了しています。'))
    try:
        item = locked.answers.select_for_update().get(pk=answer_id, is_correct__isnull=True)
    except UnitDiagnosticAnswer.DoesNotExist:
        raise ValidationError(_('この問題はすでに回答済みか、存在しません。'))
    answer = answer.strip()
    if not answer:
        raise ValidationError(_('回答を入力してください。'))
    is_correct, explanation, _quality = _judge(
        section=item.section, problem=item.problem, answer=answer, kind='diagnostic',
    )
    item.answer = answer
    item.is_correct = is_correct
    item.explanation = explanation
    item.save(update_fields=('answer', 'is_correct', 'explanation'))

    results = list(
        locked.answers.exclude(is_correct__isnull=True).order_by('order').values_list('is_correct', flat=True)
    )
    sections = _diagnostic_candidate_sections(locked.unit)
    next_order = len(results)
    if next_order < len(sections) and not _diagnostic_should_stop(results):
        _add_diagnostic_question(diagnostic=locked, section=sections[next_order], order=next_order)
    else:
        locked.completed_at = timezone.now()
        locked.save(update_fields=('completed_at',))
    return item


def build_unit_diagnostic_result(*, diagnostic):
    answers = list(diagnostic.answers.select_related('section').order_by('order'))
    total = len(answers)
    correct_count = sum(1 for item in answers if item.is_correct)
    weak_sections = [item.section for item in answers if item.is_correct is False]
    recommended_sections = weak_sections or [item.section for item in answers[-1:]]
    return {
        'answers': answers,
        'total': total,
        'correct_count': correct_count,
        'feedback': demo_content.diagnostic_level_feedback(correct_count, total),
        'recommended_sections': recommended_sections,
    }


@transaction.atomic
def ensure_first_problem(*, session, extra_exclude=()):
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.first_problem:
        session.first_problem = locked.first_problem
        return locked.first_problem
    # Excludes problems already used anywhere else in this unit (other
    # sections' first/transfer/diagnostic problems) so the same text never
    # repeats across sections — see _used_problems_in_unit. `extra_exclude`
    # is for the one thing that query can't see: the immediately preceding
    # round's own problem for THIS section, passed in by restart_for_review
    # right before this call (the row it lived on is already gone by now).
    # start_salt additionally rotates the deterministic fallback's starting
    # variant on top of that, for cases extra_exclude doesn't cover (e.g. a
    # small fallback catalog exhausting its couple of variants after
    # several resets) — see _next_problem_salt.
    exclude = _used_problems_in_unit(unit=locked.section.unit, browser_session_key=locked.browser_session_key)
    exclude |= set(extra_exclude)
    start_salt = _next_problem_salt(section=locked.section, browser_session_key=locked.browser_session_key)
    problem = _generate_problem(
        section=locked.section, kind='first', exclude=exclude, start_salt=start_salt,
    )
    locked.first_problem = problem
    locked.save(update_fields=('first_problem',))
    session.first_problem = problem
    return problem


@transaction.atomic
def submit_first_attempt(*, session, answer, reasoning, confidence):
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.current_state != WorkflowState.FIRST_ATTEMPT:
        raise ValidationError(_('最初の解答はこのステップでは提出できません。'))
    if not answer.strip() or not reasoning.strip():
        raise ValidationError(_('解答と考え方の説明の両方を入力してください。'))
    if confidence not in range(1, 6):
        raise ValidationError(_('自信度を選択してください。'))
    if locked.attempts.filter(revision_number=0).exists():
        raise ValidationError(_('最初の解答はすでに提出済みです。'))

    problem = locked.first_problem or ensure_first_problem(session=locked)
    is_correct, explanation, reasoning_quality = _judge(
        section=locked.section, problem=problem, answer=answer, kind='first', reasoning=reasoning,
    )

    attempt = Attempt.objects.create(
        session=locked,
        section=locked.section,
        problem=problem,
        answer=answer,
        reasoning=reasoning,
        confidence=confidence,
        is_correct=is_correct,
        explanation=explanation,
        reasoning_quality=reasoning_quality,
    )

    target = _next_state_after_evaluation(is_correct=bool(is_correct), confidence=confidence)
    if target == WorkflowState.DIAGNOSIS:
        question, misconception, probability = _diagnosis_question(
            section=locked.section, attempt=attempt, confidence=confidence,
        )
        attempt.diagnosis_question = question
        attempt.suspected_misconception = misconception
        attempt.misconception_probability = probability
    elif target == WorkflowState.VERIFICATION:
        attempt.verification_question = _verification_question(section=locked.section, attempt=attempt)
    attempt.save()

    _update_concept_mastery(
        section=locked.section, browser_session_key=locked.browser_session_key,
        is_correct=is_correct, confidence=confidence,
        misconception_type=attempt.suspected_misconception,
        misconception_probability=attempt.misconception_probability if target == WorkflowState.DIAGNOSIS else None,
    )

    validate_transition(locked.current_state, target)
    locked.current_state = target
    locked.save(update_fields=('current_state', 'updated_at'))
    session.current_state = locked.current_state
    return attempt


def _diagnosis_question(*, section, attempt, confidence=None):
    """Returns (question, possible_misconception, misconception_probability).
    A confident wrong answer (quadrant C) gets a more pointed question
    aimed at the likely error; an unsure wrong answer (quadrant D) gets a
    softer, exploratory one — see ai_prompts.DIAGNOSIS_SYSTEM_PROMPT."""
    if _ai_mode(section.unit):
        try:
            user_prompt = (
                f'問題: {attempt.problem}\n学習者の解答: {attempt.answer}\n'
                f'学習者の考え方: {attempt.reasoning}'
            )
            if confidence is not None:
                user_prompt += f'\n学習者の自信度(1-5): {confidence}'
            data = _ai_json(
                system_prompt=ai_prompts.DIAGNOSIS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=ai_prompts.DIAGNOSIS_SCHEMA,
            )
            return (
                data['question'], data['possible_misconception'],
                float(data.get('misconception_probability', 0.5)),
            )
        except Exception:
            pass
    question, misconception = demo_content.diagnosis_question(section, confidence=confidence)
    probability = mastery.estimate_misconception_probability_heuristic(confidence=confidence or 0)
    return question, misconception, probability


def _verification_question(*, section, attempt):
    if _ai_mode(section.unit):
        try:
            data = _ai_json(
                system_prompt=ai_prompts.VERIFICATION_SYSTEM_PROMPT,
                user_prompt=(
                    f'問題: {attempt.problem}\n学習者の解答: {attempt.answer}\n'
                    f'学習者の考え方: {attempt.reasoning}'
                ),
                response_schema=ai_prompts.VERIFICATION_SCHEMA,
            )
            return data['question']
        except Exception:
            pass
    return demo_content.verification_question(section)


def _evaluate_verification_answer(*, section, question, answer, reasoning_quality):
    """Returns (understanding, reason_tag). 'CLEAR' skips Teach-Back
    entirely (adaptive Level 0); 'UNCLEAR' routes to a Short Teach-Back.
    AI is only consulted for the genuinely ambiguous case — see
    mastery.heuristic_verification_signal — and a failed/unavailable AI
    call always falls back to 'UNCLEAR', never an optimistic 'CLEAR'."""
    signal = mastery.heuristic_verification_signal(
        answer=answer, first_attempt_reasoning_quality=reasoning_quality,
    )
    if signal != 'AMBIGUOUS':
        return signal, f'verification_heuristic_{signal.lower()}'
    if _ai_mode(section.unit):
        try:
            data = _ai_json(
                system_prompt=ai_prompts.VERIFICATION_JUDGE_SYSTEM_PROMPT,
                user_prompt=f'確認質問: {question}\n学習者の回答: {answer}',
                response_schema=ai_prompts.VERIFICATION_JUDGE_SCHEMA,
            )
            understanding = str(data.get('understanding', '')).upper()
            if understanding in ('CLEAR', 'UNCLEAR'):
                return understanding, 'verification_ai_ambiguous'
        except Exception:
            pass
    return 'UNCLEAR', 'verification_ambiguous_no_ai'


@transaction.atomic
def submit_verification(*, session, answer):
    """Correct-but-unsure (quadrant B). The verification answer is judged
    (see _evaluate_verification_answer) to decide whether Teach-Back is
    actually needed — clear understanding skips straight to Transfer
    (adaptive Level 0); anything else gets one Short Teach-Back round."""
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.current_state != WorkflowState.VERIFICATION:
        raise ValidationError(_('確認質問はこのステップでは利用できません。'))
    answer = answer.strip()
    if not answer:
        raise ValidationError(_('確認質問に回答してから進んでください。'))
    latest_attempt = locked.attempts.order_by('-revision_number', '-created_at').first()
    understanding, reason = _evaluate_verification_answer(
        section=locked.section,
        question=latest_attempt.verification_question if latest_attempt else '',
        answer=answer,
        reasoning_quality=latest_attempt.reasoning_quality if latest_attempt else '',
    )
    if latest_attempt is not None:
        latest_attempt.verification_answer = answer
        latest_attempt.verification_understanding = understanding
        latest_attempt.save(update_fields=('verification_answer', 'verification_understanding'))

    if understanding == 'CLEAR':
        target, level = WorkflowState.TRANSFER_TASK, ''
    else:
        target, level = WorkflowState.TEACH_BACK, 'SHORT'
    validate_transition(locked.current_state, target)
    locked.current_state = target
    locked.teach_back_level = level
    locked.teach_back_level_reason = reason
    locked.save(update_fields=('current_state', 'teach_back_level', 'teach_back_level_reason', 'updated_at'))
    session.current_state = locked.current_state
    if level:
        _start_teach_back(session=locked, level=level)
    return latest_attempt


@transaction.atomic
def submit_diagnosis(*, session, answer):
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.current_state != WorkflowState.DIAGNOSIS:
        raise ValidationError(_('診断質問はこのステップでは利用できません。'))
    answer = answer.strip()
    if not answer:
        raise ValidationError(_('診断質問に回答してから進んでください。'))
    validate_transition(locked.current_state, WorkflowState.GUIDED_REVISION)
    locked.current_state = WorkflowState.GUIDED_REVISION
    locked.save(update_fields=('current_state', 'updated_at'))
    session.current_state = locked.current_state
    return answer


def _wrong_revision_count(session):
    return session.attempts.filter(revision_number__gte=1, is_correct=False).count()


def current_hint_level(*, session):
    """Hint level is never chosen by the learner — it tracks how many wrong
    revisions they've submitted, starting at 1 and capping at 5."""
    return min(_wrong_revision_count(session) + 1, MAX_HINT_LEVEL)


def _generate_hint(*, section, level, attempt):
    # Same reasoning as _judge: only require AI when the problem being
    # hinted at is a genuine AI original, not a demo_content fallback.
    fallback = _resolve_fallback(section, kind='first', problem=attempt.problem)
    if _ai_mode(section.unit) and fallback is None:
        try:
            data = _ai_json(
                system_prompt=ai_prompts.HINT_SYSTEM_PROMPT,
                user_prompt=(
                    f'ヒントレベル: {level}（このレベルの内容のみ。レベル{level + 1}以上に'
                    f'相当する情報は含めないこと）\n問題: {attempt.problem}\n'
                    f'学習者の現在の解答: {attempt.answer}\n学習者の考え方: {attempt.reasoning}'
                ),
                response_schema=ai_prompts.HINT_SCHEMA,
            )
            return data['content']
        except Exception as exc:
            return f'ヒントの自動生成に失敗しました（{exc}）。'
    # `salt` must match whichever variant was actually shown as the
    # problem so hints (and level 5's answer reveal) stay consistent with
    # it — see demo_content.build_hint.
    salt = fallback[0] if fallback else 0
    return demo_content.build_hint(section=section, level=level, kind='first', salt=salt)


@transaction.atomic
def ensure_current_hint(*, session):
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if not hints_allowed(locked.current_state):
        return None
    latest_attempt = locked.attempts.order_by('-created_at').first()
    if latest_attempt is None:
        return None
    level = current_hint_level(session=locked)
    existing = HintUsage.objects.filter(attempt=latest_attempt, level=level).first()
    if existing:
        return existing
    content = _generate_hint(section=locked.section, level=level, attempt=latest_attempt)
    hint = HintUsage.objects.create(attempt=latest_attempt, level=level, content=content)
    _update_concept_mastery(
        section=locked.section, browser_session_key=locked.browser_session_key, hint_level=level,
    )
    return hint


@transaction.atomic
def submit_revision(*, session, answer, reasoning, confidence):
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.current_state != WorkflowState.GUIDED_REVISION:
        raise ValidationError(_('修正の提出はこのステップでは利用できません。'))
    if not answer.strip() or not reasoning.strip():
        raise ValidationError(_('解答と考え方の説明の両方を入力してください。'))
    if confidence not in range(1, 6):
        raise ValidationError(_('自信度を選択してください。'))

    level_shown = current_hint_level(session=locked)
    latest_number = locked.attempts.order_by('-revision_number').values_list(
        'revision_number', flat=True
    ).first()
    problem = locked.first_problem
    is_correct, explanation, reasoning_quality = _judge(
        section=locked.section, problem=problem, answer=answer, kind='first', reasoning=reasoning,
    )
    attempt = Attempt.objects.create(
        session=locked,
        section=locked.section,
        problem=problem,
        answer=answer,
        reasoning=reasoning,
        confidence=confidence,
        revision_number=(latest_number or 0) + 1,
        is_correct=is_correct,
        explanation=explanation,
        reasoning_quality=reasoning_quality,
    )
    if is_correct:
        first_attempt = locked.attempts.filter(revision_number=0).first()
        misconception_probability = first_attempt.misconception_probability if first_attempt else 0.0
        level, reason = mastery.decide_teach_back_level(
            hint_level_used=level_shown,
            misconception_probability=misconception_probability,
            reasoning_quality=reasoning_quality,
        )
        target = WorkflowState.TRANSFER_TASK if level == 'NONE' else WorkflowState.TEACH_BACK
        validate_transition(locked.current_state, target)
        locked.current_state = target
        locked.teach_back_level = '' if level == 'NONE' else level
        locked.teach_back_level_reason = reason
        locked.save(update_fields=('current_state', 'teach_back_level', 'teach_back_level_reason', 'updated_at'))
        session.current_state = locked.current_state
        if level != 'NONE':
            _start_teach_back(session=locked, level=level)
    elif level_shown >= MAX_HINT_LEVEL:
        # Level 5 (the full worked solution) was already shown and the
        # learner is still wrong — this attempt cycle is final.
        attempt.explanation = (
            f'{explanation} レベル5のヒント（完全な解答）を確認した上でも正解に至らなかったため、'
            'この問題は不正解として記録します。'
        )
        attempt.save(update_fields=('explanation',))
        validate_transition(locked.current_state, WorkflowState.NEEDS_REVIEW)
        locked.current_state = WorkflowState.NEEDS_REVIEW
        locked.save(update_fields=('current_state', 'updated_at'))
        session.current_state = locked.current_state
        _update_concept_mastery(
            section=locked.section, browser_session_key=locked.browser_session_key,
            mastery_state=MasteryState.NEEDS_REVIEW,
        )

    _update_concept_mastery(
        section=locked.section, browser_session_key=locked.browser_session_key,
        is_correct=is_correct, confidence=confidence,
    )
    return attempt


def _generate_teach_back_question(*, session):
    """Level 2 (Targeted) initial question — grounded in the actual
    problem shown to the learner (never re-derived or borrowed from
    another subject) and the diagnosed misconception (if any), not a
    generic restatement (see
    ai_prompts.TEACH_BACK_TARGETED_QUESTION_SYSTEM_PROMPT)."""
    section = session.section
    first_attempt = session.attempts.filter(revision_number=0).first()
    misconception = first_attempt.suspected_misconception if first_attempt else ''
    problem = first_attempt.problem if first_attempt else ''
    if _ai_mode(section.unit):
        try:
            user_prompt = (
                f'科目/単元: {section.unit.name}\nセクション: {section.title}\n問題: {problem}'
            )
            if first_attempt is not None and not first_attempt.is_correct:
                user_prompt += f'\n学習者の最初の誤答: {first_attempt.answer}'
            user_prompt += f'\n推定される誤解: {misconception}'
            data = _ai_json(
                system_prompt=ai_prompts.TEACH_BACK_TARGETED_QUESTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=ai_prompts.TEACH_BACK_TARGETED_QUESTION_SCHEMA,
            )
            question = data['question']
            if isinstance(question, str) and question.strip():
                return question
        except Exception:
            pass
    return demo_content.teach_back_question(section, problem=problem, misconception=misconception)


def _start_teach_back(*, session, level):
    """Creates the round-0 pending TeachBackAttempt for a newly-entered
    Teach-Back stage — SHORT uses a fixed prompt (no AI call), TARGETED
    generates one grounded question once, up front (not on every render)."""
    question = (
        _generate_teach_back_question(session=session) if level == 'TARGETED'
        else demo_content.SHORT_TEACH_BACK_PROMPT
    )
    TeachBackAttempt.objects.create(session=session, question=question, response='', round_number=0)


def current_teach_back(*, session):
    """The Teach-Back round currently awaiting an answer, if any (the most
    recent one with no evaluation yet)."""
    return session.teach_backs.filter(evaluation='').order_by('-round_number', '-created_at').first()


def _evaluate_teach_back_answer(*, session, question, answer):
    """Returns (evaluation, feedback, follow_up_question). A confidently
    too-thin answer is judged without an AI call (see
    mastery.heuristic_teach_back_signal); anything else is judged grounded
    in the actual problem/misconception (see
    ai_prompts.TEACH_BACK_JUDGE_SYSTEM_PROMPT — this is what makes the
    evaluation more than a plausibility/keyword check). A failed/unavailable
    AI call falls back to the same demo heuristic used when AI isn't
    configured — never an optimistic CLEAR_UNDERSTANDING invented from
    nothing."""
    section = session.section
    if mastery.heuristic_teach_back_signal(answer=answer) == 'PARTIAL':
        return demo_content.evaluate_teach_back_answer(section, answer)
    if _ai_mode(section.unit):
        first_attempt = session.attempts.filter(revision_number=0).first()
        try:
            user_prompt = (
                f'科目/単元: {section.unit.name}\nセクション: {section.title}\n'
                f'質問: {question}\n学習者の回答: {answer}'
            )
            if first_attempt is not None:
                user_prompt += f'\n実際の問題: {first_attempt.problem}'
                if not first_attempt.is_correct:
                    user_prompt += f'\n学習者の最初の誤答: {first_attempt.answer}'
                if first_attempt.suspected_misconception:
                    user_prompt += f'\n推定される誤解: {first_attempt.suspected_misconception}'
            data = _ai_json(
                system_prompt=ai_prompts.TEACH_BACK_JUDGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=ai_prompts.TEACH_BACK_JUDGE_SCHEMA,
            )
            evaluation = str(data.get('evaluation', '')).upper()
            if evaluation in ('CLEAR_UNDERSTANDING', 'PARTIAL_UNDERSTANDING'):
                return evaluation, data.get('feedback', ''), data.get('follow_up_question', '')
        except Exception:
            pass
    return demo_content.evaluate_teach_back_answer(section, answer)


@transaction.atomic
def submit_teach_back(*, session, answer):
    """Teach-Back only runs on paths with an uncertainty or misconception
    signal (see state_machine.ALLOWED_TRANSITIONS) — a confident, correct
    first try skips straight to Transfer, and even Verification/Guided
    Revision successes skip it entirely when the evidence already shows
    clear understanding (adaptive Level 0 — see submit_verification /
    submit_revision). A single short answer per round, evaluated grounded
    in the actual problem (see _evaluate_teach_back_answer), capped at
    mastery.MAX_TEACH_BACK_ROUNDS rounds so an unclear answer can never
    loop forever.

    Reaching the round cap without CLEAR_UNDERSTANDING still moves on to
    Transfer Check (Teach-Back must never become a dead end), but this is
    NOT treated as understanding: the evaluation stays
    PARTIAL_UNDERSTANDING, teach_back_score stays at the partial value, and
    Mastered is only ever granted by a subsequent successful Transfer
    Check, never by Teach-Back alone."""
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.current_state != WorkflowState.TEACH_BACK:
        raise ValidationError(_('Teach-Backはこのステップでは利用できません。'))
    answer = answer.strip()
    if not answer:
        raise ValidationError(_('Teach-Backの回答を入力してください。'))
    pending = current_teach_back(session=locked)
    if pending is None:
        raise ValidationError(_('Teach-Backの質問が見つかりません。'))

    evaluation, feedback, follow_up_question = _evaluate_teach_back_answer(
        session=locked, question=pending.question, answer=answer,
    )
    pending.response = answer
    pending.evaluation = evaluation
    pending.feedback = feedback
    pending.follow_up_question = follow_up_question
    pending.save(update_fields=('response', 'evaluation', 'feedback', 'follow_up_question'))

    round_cap_reached = pending.round_number >= mastery.MAX_TEACH_BACK_ROUNDS - 1
    if evaluation == 'CLEAR_UNDERSTANDING' or round_cap_reached:
        validate_transition(locked.current_state, WorkflowState.TRANSFER_TASK)
        locked.current_state = WorkflowState.TRANSFER_TASK
        locked.save(update_fields=('current_state', 'updated_at'))
        session.current_state = locked.current_state
    else:
        TeachBackAttempt.objects.create(
            session=locked, question=follow_up_question, response='',
            round_number=pending.round_number + 1,
        )
    _update_concept_mastery(
        section=locked.section, browser_session_key=locked.browser_session_key,
        teach_back_score=100 if evaluation == 'CLEAR_UNDERSTANDING' else 50,
    )
    return pending


@transaction.atomic
def ensure_transfer_problem(*, session):
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.transfer_problem:
        session.transfer_problem = locked.transfer_problem
        return locked.transfer_problem
    # Unit-wide exclude (see _used_problems_in_unit) already includes this
    # section's own first_problem, plus every other section's problems.
    #
    # start_salt is derived from whichever salt actually produced
    # first_problem (via _resolve_fallback), NOT from _next_problem_salt /
    # ConceptMastery.attempt_count directly — attempt_count already grew
    # by the time Transfer is reached (submit_first_attempt/submit_revision
    # judge at least one attempt first), so re-reading it here would give a
    # start_salt that disagrees with the one ensure_first_problem used at
    # the start of this same round. Reusing first_problem's own salt keeps
    # both still rotating together across resets of this section, without
    # that drift. None (a genuine AI-original first_problem) falls back to 0.
    exclude = _used_problems_in_unit(unit=locked.section.unit, browser_session_key=locked.browser_session_key)
    resolved_first = (
        _resolve_fallback(locked.section, kind='first', problem=locked.first_problem)
        if locked.first_problem else None
    )
    start_salt = resolved_first[0] if resolved_first else 0
    problem = _generate_problem(
        section=locked.section, kind='transfer', reference_problem=locked.first_problem,
        exclude=exclude, start_salt=start_salt,
    )
    locked.transfer_problem = problem
    locked.save(update_fields=('transfer_problem',))
    session.transfer_problem = problem
    return problem


@transaction.atomic
def submit_transfer_check(*, session, answer, reasoning, confidence):
    locked = SectionSession.objects.select_for_update().get(pk=session.pk)
    if locked.current_state != WorkflowState.TRANSFER_TASK:
        raise ValidationError(_('Transfer Checkはこのステップでは利用できません。'))
    if locked.transfer_attempts.exists():
        raise ValidationError(_('Transfer Checkはすでに提出済みです。'))
    if not answer.strip() or not reasoning.strip():
        raise ValidationError(_('解答と考え方の説明の両方を入力してください。'))
    if confidence not in range(1, 6):
        raise ValidationError(_('自信度を選択してください。'))

    problem = locked.transfer_problem or ensure_transfer_problem(session=locked)
    is_correct, explanation, _quality = _judge(
        section=locked.section, problem=problem, answer=answer, kind='transfer', reasoning=reasoning,
    )
    transfer = TransferAttempt.objects.create(
        session=locked,
        problem=problem,
        answer=answer,
        reasoning=reasoning,
        confidence=confidence,
        is_correct=is_correct,
        explanation=explanation,
    )
    target = WorkflowState.MASTERED if is_correct else WorkflowState.NEEDS_REVIEW
    validate_transition(locked.current_state, target)
    locked.current_state = target
    locked.save(update_fields=('current_state', 'updated_at'))
    session.current_state = locked.current_state
    _update_concept_mastery(
        section=locked.section, browser_session_key=locked.browser_session_key,
        transfer_success=bool(is_correct),
        mastery_state=MasteryState.MASTERED if is_correct else MasteryState.NEEDS_REVIEW,
    )
    return transfer


def _review_recommendation(*, session):
    section = session.section
    if _ai_mode(section.unit):
        latest_attempt = session.attempts.order_by('-revision_number', '-created_at').first()
        hint_count = HintUsage.objects.filter(attempt__session=session).count()
        try:
            data = _ai_json(
                system_prompt=ai_prompts.REVIEW_RECOMMENDATION_SYSTEM_PROMPT,
                user_prompt=(
                    f'推定される誤解: {latest_attempt.suspected_misconception if latest_attempt else "記録なし"}\n'
                    f'使用したヒント数: {hint_count}'
                ),
                response_schema=ai_prompts.REVIEW_RECOMMENDATION_SCHEMA,
            )
            return data['recommendation']
        except Exception:
            pass
    return demo_content.review_recommendation(section)


def build_outcome_summary(*, session):
    if session.current_state == WorkflowState.MASTERED:
        return 'Mastered: この単元の内容を習得したと判定されました。', ''
    return 'Needs review: もう一度復習が必要です。', _review_recommendation(session=session)
