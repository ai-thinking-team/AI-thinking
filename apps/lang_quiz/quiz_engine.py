"""Ten-question language quiz generation and anonymous progress tracking."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re

from django.db import transaction

from apps.ai_engine.client import generate_ai_response
from apps.ai_engine.exceptions import AIEngineError

from .models import LanguageCourseProgress, MissingLanguageQuestion


SECTION_LABELS = {
    'vocabulary': 'Vocabulary',
    'reading': 'Reading',
    'grammar': 'Grammar',
    'myself': 'Myself',
    'missing': 'Missing',
    'diagnostic': '診断テスト',
}

AI_QUESTION_SCHEMA = [{
    'prompt': 'string',
    'answer': 'string',
    'explanation': 'string',
    'next_step': 'string',
    'hints': ['string'],
}]


def _question(key, prompt, answer, explanation, next_step, *, section, hints=None):
    hints = hints or [
        '問題文の中心語と、空欄の前後に注目しましょう。',
        f'これは {SECTION_LABELS.get(section, section)} の基本事項を確認する問題です。',
        '答えの品詞、時制、または文脈上の役割を絞り込みましょう。',
        f'答えの最初の文字は「{str(answer)[:1]}」です。',
        f'答えは「{answer}」です。入力できなければ「わからない」を選びましょう。',
    ]
    return {
        'key': key,
        'prompt': prompt,
        'answer': str(answer),
        'explanation': explanation,
        'next_step': next_step,
        'hints': list(hints)[:5],
        'section': section,
        'attempt_count': 0,
        'hint_level': 1,
        'resolved': False,
        'is_correct': None,
        'last_feedback': '',
    }


VOCABULARY_DATA = [
    ('abundant', '豊富な', 'The region has ____ natural resources.'),
    ('accurate', '正確な', 'Please provide ____ information.'),
    ('adapt', '適応する', 'Animals must ____ to environmental change.'),
    ('benefit', '利益・恩恵', 'Exercise has a positive ____ for health.'),
    ('concise', '簡潔な', 'Keep your summary clear and ____.'),
    ('decline', '減少する・断る', 'Sales began to ____ in winter.'),
    ('essential', '不可欠な', 'Water is ____ for life.'),
    ('fragile', '壊れやすい', 'Handle the ____ glass carefully.'),
    ('generate', '生み出す', 'Solar panels ____ electricity.'),
    ('maintain', '維持する', 'It is important to ____ a steady pace.'),
    ('persuade', '説得する', 'She tried to ____ him to join.'),
    ('reliable', '信頼できる', 'We need a ____ source of information.'),
    ('significant', '重要な・かなりの', 'The study found a ____ difference.'),
    ('temporary', '一時的な', 'This is only a ____ solution.'),
    ('verify', '確かめる', 'Always ____ a claim before sharing it.'),
]

GRAMMAR_DATA = [
    ('g1', 'She ____ to school every day. (go)', 'goes', '三人称単数の現在形なので goes です。'),
    ('g2', 'I have lived here ____ 2020.', 'since', '開始時点には since を使います。'),
    ('g3', 'If I ____ more time, I would travel.', 'had', '仮定法過去では if 節を過去形にします。'),
    ('g4', 'This book ____ by many students.', 'is read', '受動態は be動詞 + 過去分詞です。'),
    ('g5', 'He is taller ____ his brother.', 'than', '比較級の比較対象は than で結びます。'),
    ('g6', 'There ____ two apples on the table.', 'are', '複数名詞 two apples に合わせて are を使います。'),
    ('g7', 'I enjoy ____ music. (listen)', 'listening to', 'enjoy の後は動名詞、listen は to を伴います。'),
    ('g8', 'She asked me ____ I was ready.', 'whether', '「〜かどうか」は whether で表せます。'),
    ('g9', 'By next year, they ____ the project.', 'will have completed', '未来の時点までの完了には未来完了形を使います。'),
    ('g10', 'The man ____ lives next door is a doctor.', 'who', '人を先行詞とする主格の関係代名詞は who です。'),
    ('g11', 'Neither answer ____ correct.', 'is', 'neither は単数扱いです。'),
    ('g12', 'I wish I ____ speak French.', 'could', '現在の実現困難な願望には過去形 could を使います。'),
]

READING_DATA = [
    ('r1', 'Mina missed the bus, so she walked to school. How did Mina get to school?', 'walked', 'バスに乗れなかったため、歩いたと明記されています。'),
    ('r2', 'The library closes at six, but Ken arrived at six thirty. Why could he not enter?', 'it was closed', '到着時刻が閉館時刻より後だからです。'),
    ('r3', 'Aya took an umbrella because dark clouds covered the sky. What weather did she expect?', 'rain', '暗い雲と傘から雨を予想したと推測できます。'),
    ('r4', 'The blue whale is larger than any other animal. Which animal is the largest?', 'blue whale', '比較表現 larger than any other animal が根拠です。'),
    ('r5', 'Tom studied all week and passed the exam. What helped Tom pass?', 'studying', '一週間勉強したことが合格につながっています。'),
    ('r6', 'Plants use sunlight to make food. What energy source do plants use?', 'sunlight', '本文に sunlight と直接書かれています。'),
    ('r7', 'The café was crowded, yet we found one empty table. Was seating available?', 'yes', 'one empty table があったため、席は利用可能でした。'),
    ('r8', 'Lena whispered because the baby was sleeping. Why did Lena speak quietly?', 'the baby was sleeping', 'because 以下が理由を示しています。'),
    ('r9', 'After the storm, several roads were flooded. What caused the road closures?', 'flooding', '嵐の後に道路が冠水したことが原因です。'),
    ('r10', 'The recipe serves four people. We have eight guests. How many batches are needed?', 'two', '8 ÷ 4 = 2 なので2回分必要です。'),
    ('r11', 'Although the task was difficult, Rui finished it. Did difficulty stop Rui?', 'no', 'although は逆接で、実際には完了しています。'),
    ('r12', 'The museum is free on Sundays. Today is Sunday. What is today’s admission cost?', 'free', '日曜日は無料と明記されています。'),
]


def _vocabulary_questions(prefix='vocab'):
    return [
        _question(
            f'{prefix}-{word}', prompt, word,
            f'「{word}」は「{meaning}」という意味で、この文脈に適合します。',
            f'次は「{word}」を使って自分の例文を1つ作りましょう。', section='vocabulary',
        )
        for word, meaning, prompt in VOCABULARY_DATA
    ]


def _grammar_questions():
    return [
        _question(key, prompt, answer, explanation, '同じ文法ルールを使う例文を1つ作りましょう。', section='grammar')
        for key, prompt, answer, explanation in GRAMMAR_DATA
    ]


def _reading_questions():
    return [
        _question(key, prompt, answer, explanation, '答えの根拠となる本文の語句を確認しましょう。', section='reading')
        for key, prompt, answer, explanation in READING_DATA
    ]


COURSES = {
    'daily-english': {
        'title': 'Daily English Essentials',
        'description': '日常会話で頻出する基本語彙を文脈で学びます。',
        'questions': _vocabulary_questions('daily')[:10],
    },
    'academic-words': {
        'title': 'Academic Word Builder',
        'description': 'レポートや発表に役立つアカデミック語彙コースです。',
        'questions': _vocabulary_questions('academic')[3:13],
    },
    'business-context': {
        'title': 'Business Vocabulary',
        'description': '仕事の場面で使う語彙を実践的な例文で確認します。',
        'questions': _vocabulary_questions('business')[5:15],
    },
}


def course_catalog(session_key):
    progress = {
        item.course_slug: item
        for item in LanguageCourseProgress.objects.filter(browser_session_key=session_key)
    }
    catalog = []
    for slug, course in COURSES.items():
        item = progress.get(slug)
        catalog.append({
            'slug': slug,
            'title': course['title'],
            'description': course['description'],
            'score_percent': item.score_percent if item else 0,
            'completed': item.completed if item else False,
        })
    return catalog


def _questions_from_ai(specs, section, count):
    if not isinstance(specs, list) or len(specs) < count:
        return []
    questions = []
    for index, spec in enumerate(specs[:count]):
        if not isinstance(spec, dict) or not all(spec.get(key) for key in ('prompt', 'answer', 'explanation')):
            return []
        hints = spec.get('hints') if isinstance(spec.get('hints'), list) else []
        if len(hints) < 5:
            hints = None
        key = hashlib.sha256(
            f"ai|{section}|{spec['prompt']}|{spec['answer']}|{index}".encode('utf-8')
        ).hexdigest()[:24]
        item_section = ('vocabulary', 'grammar', 'reading')[index % 3] if section == 'diagnostic' else section
        questions.append(_question(
            key,
            str(spec['prompt']),
            str(spec['answer']),
            str(spec['explanation']),
            str(spec.get('next_step') or '同じ知識を使う例文を1つ作りましょう。'),
            section=item_section,
            hints=hints,
        ))
    return questions


def generate_section_questions(section, *, count=10):
    if section in {'vocabulary', 'grammar', 'reading', 'diagnostic'}:
        try:
            specs = generate_ai_response(
                system_prompt=(
                    'You create accurate language-learning quizzes for Japanese-speaking learners. '
                    'Return exactly the requested number of independent questions. Each question needs '
                    'a short unambiguous answer, Japanese explanation, next study step, and exactly five '
                    'Japanese hints from subtle level 1 to answer-revealing level 5.'
                ),
                user_prompt=(
                    f'Section: {section}. Create {count} fresh questions. '
                    'For diagnostic, mix vocabulary, grammar, and short reading questions. '
                    'Avoid duplicates and keep prompts self-contained.'
                ),
                response_schema=AI_QUESTION_SCHEMA,
            )
            generated = _questions_from_ai(specs, section, count)
            if generated:
                return generated
        except AIEngineError:
            pass

    if section == 'vocabulary':
        pool = _vocabulary_questions()
    elif section == 'grammar':
        pool = _grammar_questions()
    elif section == 'reading':
        pool = _reading_questions()
    elif section == 'diagnostic':
        pool = _vocabulary_questions() + _grammar_questions() + _reading_questions()
    else:
        raise ValueError('Unsupported language section.')
    return random.sample(pool, min(count, len(pool)))


def get_course_questions(course_slug):
    course = COURSES.get(course_slug)
    if course is None:
        raise ValueError('選択されたコースが見つかりません。')
    return [dict(question) for question in course['questions']]


def _decode_upload(upload):
    data = upload.read()
    for encoding in ('utf-8-sig', 'utf-16', 'shift-jis'):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode('latin-1', errors='ignore')


def generate_uploaded_questions(files, instruction, *, section='myself', count=10):
    """Create deterministic local questions from user material (AI adapter-ready fallback)."""
    chunks = []
    names = []
    for upload in files:
        names.append(upload.name)
        text = _decode_upload(upload)
        if upload.name.lower().endswith('.json'):
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        elif upload.name.lower().endswith('.csv'):
            rows = csv.reader(io.StringIO(text))
            text = '\n'.join(' : '.join(cell.strip() for cell in row if cell.strip()) for row in rows)
        chunks.extend(line.strip() for line in text.splitlines() if line.strip())

    if not chunks:
        raise ValueError('ファイルから問題に使える文字を読み取れませんでした。')

    material = '\n'.join(chunks)[:16000]
    try:
        specs = generate_ai_response(
            system_prompt=(
                'You create language-learning questions only from supplied learning material. '
                'Follow the learner instruction. Return exactly the requested count. Each item must '
                'have one concise answer, a Japanese explanation, next study step, and exactly five '
                'Japanese hints that progress from subtle to revealing the answer at level 5.'
            ),
            user_prompt=f'Learner instruction: {instruction}\nQuestion count: {count}\nMaterial:\n{material}',
            response_schema=AI_QUESTION_SCHEMA,
        )
        generated = _questions_from_ai(specs, section, count)
        if generated:
            return generated, ', '.join(names)
    except AIEngineError:
        pass

    random.shuffle(chunks)
    questions = []
    for index in range(count):
        line = chunks[index % len(chunks)]
        pair = re.split(r'\s*(?:,|:|=|\t| - )\s*', line, maxsplit=1)
        if len(pair) == 2 and pair[0] and pair[1]:
            answer, context = pair[0].strip(), pair[1].strip()
            prompt = f'「{context[:140]}」に対応する語句を答えてください。'
        else:
            tokens = re.findall(r"[\wÀ-ỹぁ-んァ-ヶ一-龯'-]+", line, flags=re.UNICODE)
            answer = max(tokens, key=len) if tokens else line[:30]
            prompt = line.replace(answer, '____', 1)
            prompt = f'教材の空欄を補ってください: {prompt[:180]}'
        key = hashlib.sha256(f'{line}|{index}|{instruction}'.encode('utf-8')).hexdigest()[:20]
        questions.append(_question(
            f'upload-{key}', prompt, answer,
            f'アップロード教材では「{answer}」が対応する内容です。',
            '教材の同じ段落を読み直し、この語句を別の文脈でも使ってみましょう。',
            section=section,
            hints=[
                'アップロードした教材の該当箇所を思い出しましょう。',
                f'作問リクエストは「{instruction[:80]}」です。',
                f'答えは {len(answer)} 文字前後です。',
                f'答えの最初の文字は「{answer[:1]}」です。',
                f'答えは「{answer}」です。',
            ],
        ))
    return questions, ', '.join(names)


def missing_questions(session_key, *, count=10):
    records = list(MissingLanguageQuestion.objects.filter(browser_session_key=session_key))
    random.shuffle(records)
    return [
        _question(
            record.fingerprint, record.prompt, record.reference_answer,
            record.explanation, record.next_step, section='missing', hints=record.hints,
        )
        for record in records[:count]
    ]


def answer_matches(answer, reference):
    normalize = lambda value: re.sub(r'[\s\W_]+', ' ', str(value).casefold()).strip()
    supplied = normalize(answer)
    expected = normalize(reference)
    return bool(supplied and (supplied == expected or supplied in {part.strip() for part in expected.split('/')}))


def fingerprint(question):
    return hashlib.sha256(f"{question['prompt']}|{question['answer']}".encode('utf-8')).hexdigest()


@transaction.atomic
def remember_missing(session_key, question):
    key = fingerprint(question)
    MissingLanguageQuestion.objects.update_or_create(
        browser_session_key=session_key,
        fingerprint=key,
        defaults={
            'section': question.get('section', ''),
            'prompt': question['prompt'],
            'reference_answer': question['answer'],
            'explanation': question.get('explanation', ''),
            'next_step': question.get('next_step', ''),
            'hints': question.get('hints', []),
        },
    )


def resolve_missing(session_key, question):
    keys = {question.get('key'), fingerprint(question)}
    MissingLanguageQuestion.objects.filter(
        browser_session_key=session_key,
        fingerprint__in=[key for key in keys if key],
    ).delete()


@transaction.atomic
def update_course_progress(session_key, course_slug, question):
    if not course_slug:
        return None
    progress, _ = LanguageCourseProgress.objects.get_or_create(
        browser_session_key=session_key,
        course_slug=course_slug,
    )
    keys = set(progress.correct_question_keys)
    keys.add(question['key'])
    total = len(COURSES[course_slug]['questions'])
    progress.correct_question_keys = sorted(keys)
    progress.score_percent = min(100, round(len(keys) / total * 100))
    progress.completed = progress.score_percent == 100
    progress.save()
    return progress


def diagnostic_recommendations(questions):
    wrong_sections = {}
    for question in questions:
        if question.get('is_correct') is False:
            section = question.get('section', 'vocabulary')
            wrong_sections[section] = wrong_sections.get(section, 0) + 1
    if not wrong_sections:
        return [
            {'title': 'Academic Word Builder', 'detail': '基礎は安定しています。より高度な語彙へ進みましょう。'},
            {'title': '長文読解への発展', 'detail': '根拠を短時間で見つける練習がおすすめです。'},
        ]
    weakest = max(wrong_sections, key=wrong_sections.get)
    mapping = {
        'vocabulary': ('Vocabulary', 'Missing と語彙コースで、意味と例文をセットで復習しましょう。'),
        'grammar': ('Grammar', '間違えた文法規則を例文にしてから再挑戦しましょう。'),
        'reading': ('Reading', '接続詞と根拠文に印を付ける読解練習がおすすめです。'),
    }
    title, detail = mapping.get(weakest, mapping['vocabulary'])
    return [
        {'title': f'おすすめ: {title}', 'detail': detail},
        {'title': '関連学習: Missing', 'detail': '今回間違えた問題は Missing に保存されています。正解すると自動で消えます。'},
    ]
