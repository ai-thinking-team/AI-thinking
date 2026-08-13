from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.learning_core.services import transition_session
from apps.learning_core.state_machine import WorkflowState, ai_assistance_allowed, hints_allowed

from .forms import (
    FileUploadForm,
    LanguageAttemptForm,
    MaterialQuizForm,
    QuizAnswerForm,
    TeachBackForm,
    TransferAttemptForm,
)
from .models import LanguageQuizRun, MissingLanguageQuestion
from .quiz_engine import (
    COURSES,
    SECTION_LABELS,
    answer_matches,
    course_catalog,
    difficulty_from_diagnostic,
    diagnostic_recommendations,
    generate_section_questions,
    generate_uploaded_questions,
    get_course_questions,
    missing_questions,
    remember_missing,
    resolve_missing,
    update_course_progress,
)
from .services import (
    begin_transfer_check,
    complete_transfer_check,
    create_questions_from_file_upload,
    ensure_demo_question,
    get_demo_session,
    request_curated_hint,
    submit_first_attempt,
    submit_revised_attempt,
    submit_teach_back,
    submit_transfer_attempt,
)


def home(request):
    session_key = _session_key(request)
    return render(request, 'lang_quiz/home.html', {
        'missing_count': MissingLanguageQuestion.objects.filter(browser_session_key=session_key).count(),
        'courses': course_catalog(session_key),
        'material_form': MaterialQuizForm(),
    })


def _session_key(request):
    if request.session.session_key is None:
        request.session.create()
    return request.session.session_key


def _create_run(request, *, section, questions, mode='', course_slug='', source_name='', instruction=''):
    run = LanguageQuizRun.objects.create(
        browser_session_key=_session_key(request),
        section=section,
        mode=mode,
        course_slug=course_slug,
        source_name=source_name,
        instruction=instruction,
        questions=questions,
    )
    return redirect('lang_quiz:quiz_run', run_id=run.id)


def start_quiz(request, section):
    if section not in {'vocabulary', 'reading', 'grammar', 'diagnostic', 'missing'}:
        raise Http404('Unknown language section')
    session_key = _session_key(request)
    if section == 'missing':
        questions = missing_questions(session_key)
        if not questions:
            messages.info(request, 'You have no questions to review in Missing.')
            return redirect('lang_quiz:home')
    else:
        difficulty = difficulty_from_diagnostic(session_key, section)
        questions = generate_section_questions(
            section,
            count=10,
            answer_mode='multiple_choice',
            difficulty=difficulty,
        )
    mode = 'multiple_choice' if section == 'vocabulary' else 'random'
    return _create_run(request, section=section, questions=questions, mode=mode)


def start_vocabulary(request, answer_mode):
    if answer_mode not in {'multiple_choice', 'typing'}:
        raise Http404('Unknown vocabulary answer mode')
    session_key = _session_key(request)
    difficulty = difficulty_from_diagnostic(session_key, 'vocabulary')
    questions = generate_section_questions(
        'vocabulary', count=10, answer_mode=answer_mode, difficulty=difficulty,
    )
    return _create_run(
        request, section='vocabulary', questions=questions, mode=answer_mode,
    )


def start_course(request, course_slug):
    if course_slug not in COURSES:
        raise Http404('Unknown course')
    return _create_run(
        request,
        section='vocabulary',
        questions=get_course_questions(course_slug),
        mode='course',
        course_slug=course_slug,
    )


def start_material_quiz(request, section):
    """Handle file upload for reading/grammar/vocabulary/myself sections.

    When section is 'reading': generates 10 reading comprehension questions from the uploaded file.
    When section is 'grammar': generates 10 grammar questions from the uploaded file.
    """
    if section not in {'myself', 'vocabulary', 'reading', 'grammar'}:
        raise Http404('Unknown upload section')
    if request.method != 'POST':
        return redirect('lang_quiz:material_setup', section=section)
    form = MaterialQuizForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'lang_quiz/material_setup.html', {'form': form, 'section': section}, status=400)
    try:
        answer_mode = form.cleaned_data.get('answer_mode') or 'multiple_choice'
        difficulty = difficulty_from_diagnostic(_session_key(request), section)
        questions, source_name = generate_uploaded_questions(
            form.cleaned_data['files'],
            form.cleaned_data['instruction'],
            section=section,
            count=10,
            answer_mode=answer_mode,
            difficulty=difficulty,
        )
    except ValueError as exc:
        form.add_error('files', exc)
        return render(request, 'lang_quiz/material_setup.html', {'form': form, 'section': section}, status=400)
    return _create_run(
        request,
        section=section,
        questions=questions,
        mode='upload',
        source_name=source_name,
        instruction=form.cleaned_data['instruction'],
    )


def material_setup(request, section):
    if section not in {'myself', 'vocabulary', 'reading', 'grammar'}:
        raise Http404('Unknown upload section')
    return render(request, 'lang_quiz/material_setup.html', {
        'form': MaterialQuizForm(),
        'section': section,
        'courses': course_catalog(_session_key(request)) if section == 'vocabulary' else [],
    })


def quiz_run(request, run_id):
    session_key = _session_key(request)
    run = get_object_or_404(LanguageQuizRun, id=run_id, browser_session_key=session_key)
    questions = list(run.questions)

    if request.method == 'POST' and not run.finished:
        question = questions[run.current_index]
        action = request.POST.get('action', 'answer')

        if question.get('resolved') and action == 'next':
            if run.current_index + 1 >= len(questions):
                run.finished = True
            else:
                run.current_index += 1
            run.save(update_fields=('current_index', 'finished', 'updated_at'))
            return redirect('lang_quiz:quiz_run', run_id=run.id)

        if not question.get('resolved'):
            form = QuizAnswerForm(request.POST, question=question)
            gave_up = action == 'give_up' and question.get('hint_level', 0) >= 5
            if gave_up or form.is_valid():
                correct = False if gave_up else answer_matches(
                    form.cleaned_data['answer'], question['answer']
                )
                question['submitted_answer'] = (
                    '' if gave_up else form.cleaned_data['answer']
                )
                if gave_up:
                    question['resolved'] = True
                    question['is_correct'] = False
                    question['last_feedback'] = (
                        'This question was marked as unknown and counts as incorrect. '
                        'It has been saved to Missing for review.'
                    )
                    remember_missing(session_key, question)
                elif correct:
                    question['resolved'] = True
                    used_hint = question.get('hint_level', 0) > 0
                    question['is_correct'] = not used_hint
                    if used_hint:
                        question['last_feedback'] = (
                            'The answer is correct, but this question counts as incorrect because a hint was used.'
                        )
                        remember_missing(session_key, question)
                    else:
                        question['last_feedback'] = 'Correct!'
                        run.correct_count += 1
                        resolve_missing(session_key, question)
                        update_course_progress(session_key, run.course_slug, question)
                elif run.section == 'diagnostic':
                    question['attempt_count'] = question.get('attempt_count', 0) + 1
                    question['resolved'] = True
                    question['is_correct'] = False
                    question['last_feedback'] = (
                        'Incorrect. Diagnostic questions do not provide hints. '
                        'This question has been saved to Missing for review.'
                    )
                    remember_missing(session_key, question)
                elif question.get('hint_level', 0) >= 5:
                    question['resolved'] = True
                    question['is_correct'] = False
                    question['last_feedback'] = (
                        'You reached hint level 5. '
                        'This question has been saved to Missing for later review.'
                    )
                    remember_missing(session_key, question)
                else:
                    question['attempt_count'] = question.get('attempt_count', 0) + 1
                    question['hint_level'] = min(5, question.get('hint_level', 0) + 1)
                    question['last_feedback'] = f'Not quite. Hint updated to level {question["hint_level"]}.'
                    # Every wrong attempt is review material, even before level 5.
                    remember_missing(session_key, question)
                questions[run.current_index] = question
                run.questions = questions
                if run.section == 'diagnostic' and question.get('resolved'):
                    # Diagnostic feedback is withheld until every question is answered.
                    if run.current_index + 1 >= len(questions):
                        run.finished = True
                    else:
                        run.current_index += 1
                elif gave_up:
                    if run.current_index + 1 >= len(questions):
                        run.finished = True
                    else:
                        run.current_index += 1
                run.save()
                return redirect('lang_quiz:quiz_run', run_id=run.id)

    question = None if run.finished else questions[run.current_index]
    recommendations = diagnostic_recommendations(questions) if run.finished else []
    score_percent = round(run.correct_count / max(1, len(questions)) * 100)
    return render(request, 'lang_quiz/quiz_run.html', {
        'run': run,
        'question': question,
        'form': QuizAnswerForm(question=question),
        'section_label': SECTION_LABELS.get(run.section, run.section),
        'question_number': run.current_index + 1,
        'total_questions': len(questions),
        'score_percent': score_percent,
        'recommendations': recommendations,
    })


def exercise(request):
    """Demo exercise view following the full Think-First → Evaluate → Hint → Teach-Back → Transfer workflow."""
    question = ensure_demo_question()
    evaluation = None
    recommended_courses = []

    if request.session.session_key is None:
        request.session.create()

    learning_session, _ = get_demo_session(
        browser_session_key=request.session.session_key,
        question=question,
    )

    if learning_session.current_state == WorkflowState.TOPIC_SELECTED:
        transition_session(learning_session, WorkflowState.DIAGNOSTIC_QUIZ)

    action = request.POST.get('action') if request.method == 'POST' else None
    form = LanguageAttemptForm(request.POST or None)
    teach_back_form = TeachBackForm(
        request.POST or None if action == 'submit_teach_back' else None
    )
    transfer_form = TransferAttemptForm(
        request.POST or None if action == 'submit_transfer' else None
    )
    file_form = FileUploadForm(
        request.POST or None,
        request.FILES or None if action == 'upload_file' else None,
    )

    if request.method == 'POST':
        if action in (None, 'submit_answer'):
            if form.is_valid():
                try:
                    if learning_session.current_state == WorkflowState.DIAGNOSTIC_QUIZ:
                        _, evaluation = submit_first_attempt(
                            learning_session=learning_session,
                            question=question,
                            **form.cleaned_data,
                        )
                    elif learning_session.current_state == WorkflowState.GUIDED_REVISION:
                        _, evaluation = submit_revised_attempt(
                            learning_session=learning_session,
                            question=question,
                            **form.cleaned_data,
                        )
                    if evaluation:
                        if evaluation.get('is_correct'):
                            messages.success(
                                request,
                                'Correct! Moving on to the Teach-Back stage — explain the concept in your own words.',
                            )
                        else:
                            gap = evaluation.get('gap_type', 'unknown')
                            messages.info(request, f'Error detected: {gap} — use the hints and try again.')
                except ValidationError as exc:
                    form.add_error(None, exc)
                except Exception as exc:
                    messages.error(request, str(exc))

        elif action == 'request_hint':
            try:
                request_curated_hint(learning_session=learning_session)
            except Exception as exc:
                messages.error(request, str(exc))

        elif action == 'submit_teach_back':
            if teach_back_form.is_valid():
                try:
                    teach_back_attempt = submit_teach_back(
                        learning_session=learning_session,
                        response=teach_back_form.cleaned_data['response'],
                    )
                    if teach_back_attempt.evaluation == 'CLEAR_UNDERSTANDING':
                        messages.success(request, 'Great explanation! Proceeding to the Transfer Task.')
                        begin_transfer_check(
                            learning_session=learning_session,
                            original_passed=True,
                        )
                    else:
                        messages.warning(request, 'Provide more detail in your explanation to demonstrate understanding.')
                except Exception as exc:
                    messages.error(request, str(exc))

        elif action == 'submit_transfer':
            if transfer_form.is_valid():
                try:
                    attempt = submit_transfer_attempt(
                        learning_session=learning_session,
                        question=question,
                        **transfer_form.cleaned_data,
                    )
                    passed = attempt.passed
                    complete_transfer_check(
                        learning_session=learning_session,
                        original_passed=True,
                        teach_back_clear=True,
                        transfer_passed=passed,
                        used_assistance=False,
                        misconception_repeated=False,
                    )
                    if passed:
                        messages.success(request, 'Excellent! Concept marked as Mastered.')
                    else:
                        messages.warning(request, 'Keep practising — this concept has been marked for review.')
                except Exception as exc:
                    messages.error(request, str(exc))

    # Build recommended courses based on the latest evaluation gap type
    if evaluation:
        gap = evaluation.get('gap_type')
        if gap == 'grammar_misconception':
            recommended_courses = [
                {
                    'title': 'Grammar Error Patterns — Intensive Review',
                    'tag': 'Needs Review: Grammar Gap',
                    'description': 'Focused drills on tense, passive voice, and relative clauses.',
                },
                {
                    'title': 'Sentence Structure Essentials',
                    'tag': 'Needs Review: Grammar Gap',
                    'description': 'Step-by-step exercises on subject-verb agreement and clause building.',
                },
            ]
        elif gap == 'context_misunderstanding':
            recommended_courses = [
                {
                    'title': 'Context Clues and Pronoun Reference',
                    'tag': 'Needs Review: Context Gap',
                    'description': 'Practice tracing pronoun references and following discourse flow.',
                },
                {
                    'title': 'Paragraph Reading Fundamentals',
                    'tag': 'Needs Review: Context Gap',
                    'description': 'Identify topic sentences and key supporting details quickly.',
                },
            ]
        else:
            recommended_courses = [
                {
                    'title': 'Core Vocabulary in Context',
                    'tag': 'Needs Review: Vocabulary Gap',
                    'description': 'Review commonly confused words with targeted example sentences.',
                },
                {
                    'title': 'Best-Word Selection Training',
                    'tag': 'Needs Review: Vocabulary Gap',
                    'description': 'Fill-in-the-blank exercises focused on contextual word choice.',
                },
            ]

    # Gather hint history for the latest attempt
    recent_hints = []
    active_hint_level = 0
    if learning_session:
        latest_attempt = learning_session.attempts.order_by('-created_at').first()
        if latest_attempt:
            recent_hints = list(latest_attempt.hint_usage.all())
            if recent_hints:
                active_hint_level = recent_hints[-1].level
            if not evaluation and latest_attempt.evaluation:
                evaluation = latest_attempt.evaluation

    return render(request, 'lang_quiz/exercise.html', {
        'form': form,
        'teach_back_form': teach_back_form or TeachBackForm(),
        'transfer_form': transfer_form or TransferAttemptForm(),
        'file_form': file_form or FileUploadForm(),
        'question': question,
        'evaluation': evaluation,
        'learning_session': learning_session,
        'ai_enabled': bool(learning_session and ai_assistance_allowed(learning_session.current_state)),
        'hints_allowed': bool(learning_session and hints_allowed(learning_session.current_state)),
        'hints': recent_hints,
        'active_hint_level': active_hint_level,
        'recommended_courses': recommended_courses,
    })
