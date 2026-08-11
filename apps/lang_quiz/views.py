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
            messages.info(request, 'Missing に復習する問題はありません。')
            return redirect('lang_quiz:home')
    else:
        questions = generate_section_questions(section, count=10)
    return _create_run(request, section=section, questions=questions, mode='random')


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
    if section not in {'myself', 'vocabulary'}:
        raise Http404('Unknown upload section')
    if request.method != 'POST':
        return redirect('lang_quiz:material_setup', section=section)
    form = MaterialQuizForm(request.POST, request.FILES)
    if not form.is_valid():
        template = 'lang_quiz/material_setup.html'
        return render(request, template, {'form': form, 'section': section}, status=400)
    try:
        questions, source_name = generate_uploaded_questions(
            form.cleaned_data['files'],
            form.cleaned_data['instruction'],
            section=section,
            count=10,
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
    if section not in {'myself', 'vocabulary'}:
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
            form = QuizAnswerForm(request.POST)
            gave_up = action == 'give_up' and question.get('hint_level', 1) >= 5
            if gave_up or form.is_valid():
                correct = False if gave_up else answer_matches(
                    form.cleaned_data['answer'], question['answer']
                )
                if correct:
                    question['resolved'] = True
                    question['is_correct'] = True
                    question['last_feedback'] = '正解です！'
                    run.correct_count += 1
                    resolve_missing(session_key, question)
                    update_course_progress(session_key, run.course_slug, question)
                elif question.get('hint_level', 1) >= 5:
                    question['resolved'] = True
                    question['is_correct'] = False
                    question['last_feedback'] = 'レベル5まで取り組んだため、この問題は不正解として Missing に保存しました。'
                    remember_missing(session_key, question)
                else:
                    question['attempt_count'] = question.get('attempt_count', 0) + 1
                    question['hint_level'] = question.get('hint_level', 1) + 1
                    question['last_feedback'] = f'まだ正解ではありません。ヒントをレベル{question["hint_level"]}に更新しました。'
                questions[run.current_index] = question
                run.questions = questions
                run.save()
                return redirect('lang_quiz:quiz_run', run_id=run.id)

    question = None if run.finished else questions[run.current_index]
    recommendations = diagnostic_recommendations(questions) if run.finished else []
    score_percent = round(run.correct_count / max(1, len(questions)) * 100)
    return render(request, 'lang_quiz/quiz_run.html', {
        'run': run,
        'question': question,
        'form': QuizAnswerForm(),
        'section_label': SECTION_LABELS.get(run.section, run.section),
        'question_number': run.current_index + 1,
        'total_questions': len(questions),
        'score_percent': score_percent,
        'recommendations': recommendations,
    })


def exercise(request):
    question = ensure_demo_question()
    evaluation = None

    if request.session.session_key is None:
        request.session.create()

    learning_session, _ = get_demo_session(
        browser_session_key=request.session.session_key,
        question=question,
    )

    if learning_session.current_state == WorkflowState.TOPIC_SELECTED:
        transition_session(learning_session, WorkflowState.DIAGNOSTIC_QUIZ)

    form = LanguageAttemptForm(request.POST or None)
    teach_back_form = TeachBackForm(request.POST or None if request.POST and request.POST.get('action') == 'submit_teach_back' else None)
    transfer_form = TransferAttemptForm(request.POST or None if request.POST and request.POST.get('action') == 'submit_transfer' else None)
    file_form = FileUploadForm(request.POST or None, request.FILES or None if request.POST and request.POST.get('action') == 'upload_file' else None)

    if request.method == 'POST':
        action = request.POST.get('action', 'submit_attempt')

        if action == 'upload_file':
            if file_form.is_valid():
                created = create_questions_from_file_upload(file_form.cleaned_data['file'])
                if created:
                    messages.success(request, f'取り込んだファイルから AI が {len(created)} 件の単元確認問題を生成しました！')
                    learning_session.current_state = WorkflowState.DIAGNOSTIC_QUIZ
                    learning_session.save()
                    return redirect('lang_quiz:exercise')

        elif action == 'reset_session':
            learning_session.current_state = WorkflowState.DIAGNOSTIC_QUIZ
            learning_session.score_percent = 0
            learning_session.mastered = False
            learning_session.save()
            messages.success(request, 'セッションをリセットし、診断クイズを再開しました。')
            return redirect('lang_quiz:exercise')

        elif action == 'request_hint':
            try:
                hint = request_curated_hint(learning_session=learning_session)
                messages.info(request, f'ヒント Level {hint.level}: {hint.content}')
            except Exception as exc:
                messages.error(request, str(exc))

        elif action == 'submit_teach_back':
            if teach_back_form.is_valid():
                try:
                    tb_attempt = submit_teach_back(
                        learning_session=learning_session,
                        response=teach_back_form.cleaned_data['response'],
                    )
                    if tb_attempt.evaluation == 'CLEAR_UNDERSTANDING':
                        begin_transfer_check(
                            learning_session=learning_session,
                            teach_back_evaluation='CLEAR_UNDERSTANDING',
                        )
                        messages.success(request, '自分の言葉での説明（Teach-Back）が確認されました！応用問題（Transfer Check）に進みます。')
                    else:
                        messages.warning(request, '説明がやや不十分です。より詳しく概念を説明してください。')
                except ValidationError as exc:
                    teach_back_form.add_error(None, exc)
                except Exception as exc:
                    messages.error(request, str(exc))

        elif action == 'submit_transfer':
            if transfer_form.is_valid():
                try:
                    raw_answer = transfer_form.cleaned_data['answer'].strip().lower()
                    ref_answer = (question.reference_answer or 'accept').strip().lower()
                    passed = raw_answer == ref_answer or ref_answer in raw_answer

                    submit_transfer_attempt(
                        learning_session=learning_session,
                        question=question,
                        response=transfer_form.cleaned_data['answer'],
                        reasoning=transfer_form.cleaned_data['reasoning'],
                        confidence=transfer_form.cleaned_data['confidence'],
                        passed=passed,
                    )

                    target_state = complete_transfer_check(
                        learning_session=learning_session,
                        original_passed=True,
                        teach_back_clear=True,
                        transfer_passed=passed,
                        used_assistance=False,
                        misconception_repeated=False,
                    )
                    if target_state == WorkflowState.MASTERED:
                        learning_session.score_percent = 100
                        learning_session.mastered = True
                        learning_session.correct_count = 1
                        learning_session.total_questions = 1
                        learning_session.save()
                        messages.success(request, 'おめでとうございます！正答率 100% でこのコースを「Mastered! (習得済み)」として完了しました。')
                    else:
                        learning_session.score_percent = 50
                        learning_session.mastered = False
                        learning_session.save()
                        messages.warning(request, '応用問題の検証結果に基づき、「Needs Review（復習が必要）」として記録されました。')
                except ValidationError as exc:
                    transfer_form.add_error(None, exc)
                except Exception as exc:
                    messages.error(request, str(exc))

        else:
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
                            messages.success(request, '正解です！Teach-Back（自分の言葉で説明する）段階に進みます。')
                        else:
                            gap = evaluation.get("gap_type")
                            messages.info(request, f'誤り検出: {gap} — ヒントを活用して再回答してください。')
                except ValidationError as exc:
                    form.add_error(None, exc)
                except Exception as exc:
                    messages.error(request, str(exc))

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

    recommended_courses = []
    if learning_session.current_state == WorkflowState.MASTERED:
        recommended_courses = [
            {'title': '【発展コース 1】 高度な文脈表現とビジネス英語 (Advanced Business Vocabulary)', 'tag': 'Mastered!おすすめ', 'description': '実践的なビジネストラブルや専門用語の使い分けを学ぶ上級単元。'},
            {'title': '【発展コース 2】 英語イディオム・慣用句コロケーションマスター', 'tag': 'Mastered!おすすめ', 'description': 'ネイティブが頻用する慣用句や句動詞のニュアンスを深く理解する単元。'},
            {'title': '【発展コース 3】 実践長文読解と筆者の意図推測', 'tag': 'Mastered!おすすめ', 'description': '長文の論理構造を正確に捉え、行間を読み解く応用読解コース。'},
        ]
    elif learning_session.current_state in (WorkflowState.NEEDS_REVIEW, WorkflowState.GUIDED_REVISION):
        gap = evaluation.get('gap_type') if evaluation else 'vocabulary_gap'
        if gap == 'grammar_misconception':
            recommended_courses = [
                {'title': '【復習コース 1】 英文法ルールの基礎総点検コース', 'tag': '要復習: 文法ギャップ', 'description': '品詞・時制・関係代詞の基本原則を振り返り基礎を固めるおすすめ単元。'},
                {'title': '【復習コース 2】 構文パターンと主語・動詞の対応集中講座', 'tag': '要復習: 文法ギャップ', 'description': '文構造の読み違いを防ぐ基本構文チェックコース。'},
            ]
        elif gap == 'context_misunderstanding':
            recommended_courses = [
                {'title': '【復習コース 1】 文脈捉え直しと指示語・代名詞確認コース', 'tag': '要復習: 文脈理解ギャップ', 'description': '前後の文章の流れや指示語が指す具体的な内容を追うステップ講座。'},
                {'title': '【復習コース 2】 パラグラフリーディング基礎入門', 'tag': '要復習: 文脈理解ギャップ', 'description': '段落ごとのトピック文と要点を素早く把握するトレーニング。'},
            ]
        else:
            recommended_courses = [
                {'title': '【復習コース 1】 必須英単語・類義語のニュアンス使い分けコース', 'tag': '要復習: 語彙ギャップ', 'description': '混同しやすい重要単語の定義と例文を丁寧に見直す単元。'},
                {'title': '【復習コース 2】 文脈別ベスト単語選択トレーニング', 'tag': '要復習: 語彙ギャップ', 'description': '空欄前後の状況にぴったりの単語を選ぶ集中穴埋め問題。'},
            ]

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
