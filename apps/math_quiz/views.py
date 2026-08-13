from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from . import demo_content, mastery, services
from .models import ConceptMastery, HintUsage, Section, SectionSession, Unit
from .state_machine import WorkflowState

# gettext_lazy (not gettext) here: these are module-level constants
# evaluated once at import time, before any request (and its active
# language) exists — lazy translation defers the actual lookup until the
# label is rendered, so it still follows each request's language.
DIAGNOSIS_BRANCH_STAGES = (
    ('first', _lazy('最初の解答')),
    ('diagnosis', _lazy('診断')),
    ('revision', _lazy('修正')),
    ('teach_back', 'Teach-Back'),
    ('transfer', 'Transfer Check'),
    ('completed', _lazy('完了')),
)

VERIFICATION_BRANCH_STAGES = (
    ('first', _lazy('最初の解答')),
    ('verification', _lazy('確認')),
    ('teach_back', 'Teach-Back'),
    ('transfer', 'Transfer Check'),
    ('completed', _lazy('完了')),
)

# A confident, correct first try (quadrant A) has no uncertainty or
# misconception signal to teach back from — it skips straight to Transfer.
DIRECT_BRANCH_STAGES = (
    ('first', _lazy('最初の解答')),
    ('transfer', 'Transfer Check'),
    ('completed', _lazy('完了')),
)

STATE_TO_STAGE = {
    WorkflowState.FIRST_ATTEMPT: 'first',
    WorkflowState.DIAGNOSIS: 'diagnosis',
    WorkflowState.VERIFICATION: 'verification',
    WorkflowState.GUIDED_REVISION: 'revision',
    WorkflowState.TEACH_BACK: 'teach_back',
    WorkflowState.TRANSFER_TASK: 'transfer',
    WorkflowState.MASTERED: 'completed',
    WorkflowState.NEEDS_REVIEW: 'completed',
}


_TEACH_BACK_DECISION_PENDING_STATES = (
    WorkflowState.FIRST_ATTEMPT, WorkflowState.DIAGNOSIS,
    WorkflowState.VERIFICATION, WorkflowState.GUIDED_REVISION,
)


def _display_stages(first_attempt, session):
    if first_attempt is None:
        stages = DIAGNOSIS_BRANCH_STAGES
    elif first_attempt.verification_question:
        stages = VERIFICATION_BRANCH_STAGES
    elif first_attempt.diagnosis_question:
        stages = DIAGNOSIS_BRANCH_STAGES
    else:
        stages = DIRECT_BRANCH_STAGES

    # Once the adaptive Teach-Back decision has actually been made (past
    # Verification/Guided Revision) and it came out as Level 0 (skipped),
    # drop the step from the stepper instead of showing a step that will
    # never become current — see mastery.decide_teach_back_level.
    decision_pending = session.current_state in _TEACH_BACK_DECISION_PENDING_STATES
    if not decision_pending and not session.teach_back_level:
        stages = tuple(item for item in stages if item[0] != 'teach_back')
    return stages


def home(request):
    services.ensure_sample_unit()
    key = request.session.session_key
    courses = []
    for unit in Unit.objects.order_by('name').prefetch_related('sections'):
        mastered, total, percent, complete = services.unit_progress(
            unit=unit, browser_session_key=key,
        )
        courses.append({
            'unit': unit,
            'mastered': mastered,
            'total': total,
            'percent': percent,
            'complete': complete,
        })
    mistake_count = len(services.list_mistakes(browser_session_key=key))
    return render(request, 'math_quiz/mathhome.html', {'courses': courses, 'mistake_count': mistake_count})


def new(request):
    return render(request, 'math_quiz/newmath.html')


def mistakes(request):
    key = request.session.session_key
    items = services.list_mistakes(browser_session_key=key)
    return render(request, 'math_quiz/mistakes.html', {'items': items})


def unit_detail(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)
    if request.session.session_key is None:
        request.session.create()
    key = request.session.session_key

    # get_or_create_unit_diagnostic never resets an existing session (see
    # services.py), so once a learner has completed this unit's diagnostic
    # even once, completed_at stays set and every later visit goes
    # straight to the section list instead of the quiz again.
    diagnostic = services.get_or_create_unit_diagnostic(unit=unit, browser_session_key=key)
    if diagnostic.completed_at is None:
        return redirect('math_quiz:unit_diagnostic', unit_id=unit.id)

    sections = []
    for section in unit.sections.all():
        section_session = SectionSession.objects.filter(
            section=section, browser_session_key=key,
        ).first()
        # Read-only lookup (not get_or_create): browsing the course page
        # shouldn't create a learner-model row for sections never attempted.
        concept_mastery = ConceptMastery.objects.filter(
            section=section, browser_session_key=key,
        ).first()
        state = section_session.current_state if section_session else None
        status_label, status_tone = mastery.classify_section_status(
            section_state=state, concept_mastery=concept_mastery,
        )
        sections.append({
            'section': section,
            'state': state,
            'status_label': status_label,
            'status_tone': status_tone,
        })
    mastered, total, percent, complete = services.unit_progress(unit=unit, browser_session_key=key)
    return render(request, 'math_quiz/unit_detail.html', {
        'unit': unit,
        'sections': sections,
        'mastered': mastered,
        'total': total,
        'percent': percent,
        'complete': complete,
    })


def unit_diagnostic(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)
    if request.session.session_key is None:
        request.session.create()
    key = request.session.session_key
    diagnostic = services.get_or_create_unit_diagnostic(unit=unit, browser_session_key=key)

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'answer':
            try:
                services.submit_unit_diagnostic_answer(
                    diagnostic=diagnostic,
                    answer_id=request.POST.get('answer_id'),
                    answer=request.POST.get('answer', ''),
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
        elif action == 'continue':
            if diagnostic.completed_at is None:
                return HttpResponseBadRequest(_('診断クイズがまだ完了していません。'))
            return redirect('math_quiz:unit_detail', unit_id=unit.id)
        else:
            return HttpResponseBadRequest(_('不明な操作です。'))
        return redirect('math_quiz:unit_diagnostic', unit_id=unit.id)

    diagnostic.refresh_from_db()
    if diagnostic.completed_at is not None:
        result = services.build_unit_diagnostic_result(diagnostic=diagnostic)
        return render(request, 'math_quiz/unit_diagnostic.html', {
            'unit': unit, 'done': True, 'result': result,
        })

    answers = list(diagnostic.answers.all())
    current_item = next((item for item in answers if item.is_correct is None), None)
    answered_count = sum(1 for item in answers if item.is_correct is not None)
    return render(request, 'math_quiz/unit_diagnostic.html', {
        'unit': unit,
        'done': False,
        'current_item': current_item,
        'answered_count': answered_count,
        'total': len(answers),
        'progress_dots': [item.is_correct is not None for item in answers],
    })


def add_unit(request):
    if request.method != 'POST':
        return redirect('math_quiz:new')
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, _('科目名を入力してください。'))
        return redirect('math_quiz:new')

    # Every selected file's contents feed the AI section-generation call
    # (see services.generate_sections), but only the first is kept as the
    # course's downloadable reference file — Unit.file is a single
    # FileField, and changing that isn't needed for multi-file analysis.
    uploaded_files = request.FILES.getlist('file')
    files = []
    for uploaded in uploaded_files:
        files.append((uploaded.read(), uploaded.content_type))
        uploaded.seek(0)

    unit, created = Unit.objects.get_or_create(
        name=name, defaults={'file': uploaded_files[0] if uploaded_files else None},
    )
    if created:
        services.generate_sections(unit, name, files)
        return redirect('math_quiz:unit_detail', unit_id=unit.id)
    messages.info(request, _('「%(name)s」はすでに登録されています。') % {'name': name})
    return redirect('math_quiz:home')


def delete_unit(request, unit_id):
    if request.method != 'POST':
        return HttpResponseBadRequest(_('不正なリクエストです。'))
    unit = get_object_or_404(Unit, id=unit_id)
    if unit.is_demo:
        return HttpResponseBadRequest(_('サンプル科目は削除できません。'))
    if unit.file:
        unit.file.delete(save=False)
    unit.delete()
    return redirect('math_quiz:home')


def _just_completed_key(section_id):
    return f'math_quiz_just_completed_{section_id}'


def _browser_section_session(request, section):
    if request.session.session_key is None:
        request.session.create()
    session, created = services.get_or_create_section_session(
        section=section, browser_session_key=request.session.session_key,
    )
    just_completed = request.session.pop(_just_completed_key(section.id), False)
    if (
        not created
        and not just_completed
        and session.current_state in (WorkflowState.MASTERED, WorkflowState.NEEDS_REVIEW)
    ):
        # Re-selecting a section always starts a brand new round. The
        # `just_completed` flag is what lets the redirect straight after
        # finishing skip this and show the outcome page once first.
        session = services.restart_for_review(
            section=section, browser_session_key=request.session.session_key,
        )
        messages.info(request, _('新しい問題から、この学習セッションを始めます。'))
    return session


def _handle_action(request, session):
    action = request.POST.get('action', '')

    if action == 'first_attempt':
        attempt = services.submit_first_attempt(
            session=session,
            answer=request.POST.get('answer', ''),
            reasoning=request.POST.get('reasoning', ''),
            confidence=int(request.POST.get('confidence') or 0),
        )
        next_note = demo_content.NEXT_STEP_LABELS.get(session.current_state, '')
        if attempt.is_correct:
            messages.success(request, f'{attempt.explanation} {next_note}')
        else:
            messages.warning(request, f'{attempt.explanation} {next_note}')
    elif action == 'verification':
        services.submit_verification(session=session, answer=request.POST.get('answer', ''))
        next_note = demo_content.NEXT_STEP_LABELS.get(session.current_state, '')
        messages.success(request, f'{_("確認質問への回答を保存しました。")} {next_note}')
    elif action == 'diagnosis':
        services.submit_diagnosis(session=session, answer=request.POST.get('answer', ''))
        messages.success(
            request, f'{_("診断質問への回答を保存しました。")} {demo_content.NEXT_STEP_LABELS["GUIDED_REVISION"]}',
        )
    elif action == 'revision':
        attempt = services.submit_revision(
            session=session,
            answer=request.POST.get('answer', ''),
            reasoning=request.POST.get('reasoning', ''),
            confidence=int(request.POST.get('confidence') or 0),
        )
        next_note = demo_content.NEXT_STEP_LABELS.get(session.current_state, '')
        if attempt.is_correct:
            messages.success(request, f'{attempt.explanation} {next_note}')
        elif session.current_state == WorkflowState.NEEDS_REVIEW:
            request.session[_just_completed_key(session.section_id)] = True
            messages.error(request, attempt.explanation)
        else:
            messages.warning(request, f'{attempt.explanation} {_("次のヒントを確認してみましょう。")}')
    elif action == 'teach_back':
        teach_back = services.submit_teach_back(session=session, answer=request.POST.get('answer', ''))
        if session.current_state == WorkflowState.TRANSFER_TASK:
            next_note = demo_content.NEXT_STEP_LABELS['TRANSFER_TASK']
            if teach_back.evaluation == 'CLEAR_UNDERSTANDING':
                messages.success(request, f'{_("理解が確認できました。")} {next_note}')
            else:
                messages.warning(request, f'{teach_back.feedback} {next_note}')
        else:
            messages.warning(request, teach_back.feedback)
    elif action == 'transfer':
        transfer = services.submit_transfer_check(
            session=session,
            answer=request.POST.get('answer', ''),
            reasoning=request.POST.get('reasoning', ''),
            confidence=int(request.POST.get('confidence') or 0),
        )
        request.session[_just_completed_key(session.section_id)] = True
        next_note = demo_content.NEXT_STEP_LABELS.get(session.current_state, '')
        if transfer.is_correct:
            messages.success(request, f'{transfer.explanation} {next_note}')
        else:
            messages.warning(request, f'{transfer.explanation} {next_note}')
    elif action == 'reset':
        services.reset_section_session(
            section=session.section, browser_session_key=request.session.session_key,
        )
        messages.success(request, _('この学習セッションをリセットしました。'))
    else:
        return HttpResponseBadRequest(_('不明な操作です。'))
    return redirect('math_quiz:section_quiz', section_id=session.section_id)


def section_quiz(request, section_id):
    section = get_object_or_404(Section, id=section_id)
    session = _browser_section_session(request, section)

    if request.method == 'POST':
        try:
            return _handle_action(request, session)
        except (ValidationError, PermissionDenied) as exc:
            error_text = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, error_text)

    session.refresh_from_db()

    current_stage = STATE_TO_STAGE[WorkflowState(session.current_state)]
    current_hint = None
    current_teach_back = None
    if current_stage == 'first':
        services.ensure_first_problem(session=session)
    elif current_stage == 'revision':
        current_hint = services.ensure_current_hint(session=session)
    elif current_stage == 'teach_back':
        current_teach_back = services.current_teach_back(session=session)
    elif current_stage == 'transfer':
        services.ensure_transfer_problem(session=session)

    first_attempt = session.attempts.filter(revision_number=0).first()
    latest_attempt = session.attempts.order_by('-revision_number', '-created_at').first()
    hint_usage = list(
        HintUsage.objects.filter(attempt__session=session).order_by('created_at')
    )
    transfer_attempt = session.transfer_attempts.order_by('-created_at').first()
    teach_back_attempts = list(session.teach_backs.exclude(evaluation='').order_by('created_at'))

    display_stages = _display_stages(first_attempt, session)
    stage_names = [key for key, _ in display_stages]
    stage_labels = dict(display_stages)
    current_index = stage_names.index(current_stage)
    progress_steps = [
        {
            'key': key,
            'label': label,
            'current': key == current_stage,
            'complete': index < current_index,
            'locked': index > current_index,
        }
        for index, (key, label) in enumerate(display_stages)
    ]

    final_result_message, review_recommendation = (
        services.build_outcome_summary(session=session) if current_stage == 'completed' else ('', '')
    )

    mastered, total, percent, complete = services.unit_progress(
        unit=section.unit, browser_session_key=request.session.session_key,
    )

    evidence_list = []
    concept_mastery = None
    if current_stage == 'completed':
        concept_mastery = services.get_concept_mastery(
            section=section, browser_session_key=request.session.session_key,
        )
        evidence_list = mastery.build_evidence_list(session=session, concept_mastery=concept_mastery)

    return render(request, 'math_quiz/section_quiz.html', {
        'section': section,
        'session': session,
        'current_stage': current_stage,
        'current_stage_label': stage_labels[current_stage],
        'progress_steps': progress_steps,
        'first_attempt': first_attempt,
        'latest_attempt': latest_attempt,
        'attempts': list(session.attempts.order_by('revision_number', 'created_at')),
        'hint_usage': hint_usage,
        'current_hint': current_hint,
        'current_teach_back': current_teach_back,
        'teach_back_max_rounds': mastery.MAX_TEACH_BACK_ROUNDS,
        'transfer_attempt': transfer_attempt,
        'teach_back_attempts': teach_back_attempts,
        'final_result_message': final_result_message,
        'review_recommendation': review_recommendation,
        'course_percent': percent,
        'course_complete': complete,
        'evidence_list': evidence_list,
        'concept_mastery': concept_mastery,
    })
