import json

from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.ai_engine.client import generate_ai_response
from apps.ai_engine.exceptions import AIEngineError

from .models import Attempt, Section, Unit

SECTIONS_SCHEMA = {
    'type': 'object',
    'properties': {
        'sections': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string'},
                    'content': {'type': 'string'},
                },
                'required': ['title', 'content'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['sections'],
    'additionalProperties': False,
}

PROBLEM_SCHEMA = {
    'type': 'object',
    'properties': {
        'problem': {'type': 'string'},
        'hint': {'type': 'string'},
    },
    'required': ['problem', 'hint'],
    'additionalProperties': False,
}

JUDGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'is_correct': {'type': 'boolean'},
        'explanation': {'type': 'string'},
    },
    'required': ['is_correct', 'explanation'],
    'additionalProperties': False,
}


def home(request):
    return render(request, 'math_quiz/mathhome.html', {'units': Unit.objects.order_by('name')})

def new(request):
    return render(request, 'math_quiz/newmath.html')


def unit_detail(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)
    return render(request, 'math_quiz/unit_detail.html', {'unit': unit})


@require_POST
def add_unit(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return redirect('math_quiz:home')

    uploaded = request.FILES.get('file')
    file_bytes = None
    mime_type = None
    if uploaded is not None:
        file_bytes = uploaded.read()
        mime_type = uploaded.content_type
        uploaded.seek(0)

    unit, created = Unit.objects.get_or_create(name=name, defaults={'file': uploaded})
    if created:
        _generate_sections(unit, name, file_bytes, mime_type)

    return redirect('math_quiz:home')


def _generate_sections(unit, name, file_bytes, mime_type):
    try:
        text = generate_ai_response(
            system_prompt=(
                'あなたは数学教育の専門家です。指定された単元の内容にふさわしい学習セクションを'
                '設計してください。セクション数は内容に応じて自由に決めてよく、3つに固定する必要はありません。'
            ),
            user_prompt=(
                f'単元名: {name}\n\n'
                'この単元を学ぶ上で必要なセクションを、タイトルと内容（日本語での説明）の組で'
                'JSON形式で答えてください。ファイルが添付されている場合は、その内容を踏まえて'
                'セクション構成を決めてください。'
            ),
            response_schema=SECTIONS_SCHEMA,
            file_bytes=file_bytes,
            mime_type=mime_type,
        )
        sections = json.loads(text)['sections']
    except (AIEngineError, json.JSONDecodeError, KeyError) as exc:
        sections = [{
            'title': '生成エラー',
            'content': f'セクションの自動生成に失敗しました（{exc}）。',
        }]

    for order, section in enumerate(sections):
        Section.objects.create(
            unit=unit,
            title=section.get('title', f'セクション{order + 1}'),
            content=section.get('content', ''),
            order=order,
        )


def section_quiz(request, section_id):
    section = get_object_or_404(Section, id=section_id)
    try:
        text = generate_ai_response(
            system_prompt=(
                'あなたは数学教育の専門家です。指定されたセクションの内容にふさわしい練習問題を'
                '1問作成してください。'
            ),
            user_prompt=(
                f'単元: {section.unit.name}\n'
                f'セクション: {section.title}\n'
                f'セクションの内容: {section.content}\n\n'
                'このセクションのレベルに合った問題を1問と、その問題に取り組む際のヒントを'
                '日本語でJSON形式で答えてください。'
            ),
            response_schema=PROBLEM_SCHEMA,
        )
        data = json.loads(text)
        problem = data['problem']
        hint = data['hint']
    except (AIEngineError, json.JSONDecodeError, KeyError) as exc:
        problem = f'問題の自動生成に失敗しました（{exc}）。'
        hint = ''

    return render(request, 'math_quiz/section_quiz.html', {
        'section': section,
        'problem': problem,
        'hint': hint,
    })


@require_POST
def submit_answer(request):
    section = get_object_or_404(Section, id=request.POST.get('section_id'))
    problem = request.POST.get('problem', '')
    answer = request.POST.get('answer', '')

    try:
        text = generate_ai_response(
            system_prompt=(
                'あなたは数学教育の専門家です。学習者の解答を採点してください。'
            ),
            user_prompt=(
                f'問題: {problem}\n'
                f'学習者の解答: {answer}\n\n'
                'この解答が正しいかどうかを判定し、正解・不正解にかかわらず理解の助けになる'
                '解説を日本語でJSON形式で答えてください。'
            ),
            response_schema=JUDGE_SCHEMA,
        )
        data = json.loads(text)
        is_correct = data['is_correct']
        explanation = data['explanation']
    except (AIEngineError, json.JSONDecodeError, KeyError) as exc:
        is_correct = None
        explanation = f'採点に失敗しました（{exc}）。'

    attempt = Attempt.objects.create(
        section=section,
        problem=problem,
        answer=answer,
        confidence=request.POST.get('confidence') or 0,
        is_correct=is_correct,
        explanation=explanation,
    )
    return render(request, 'math_quiz/answer_result.html', {'attempt': attempt})


@require_POST
def delete_unit(request, unit_id):
    unit = get_object_or_404(Unit, id=unit_id)
    if unit.file:
        unit.file.delete(save=False)
    unit.delete()
    return redirect('math_quiz:home')
