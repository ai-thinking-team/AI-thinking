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
    'skill_focus': 'string',
    'explanation': 'string',
    'next_step': 'string',
    'hints': ['string'],
}]


def _question(key, prompt, answer, explanation, next_step, *, section, hints=None):
    hints = hints or [
        'Focus on the key word in the question and the context around the blank.',
        f'This is a {SECTION_LABELS.get(section, section)} question — recall the core rule or meaning.',
        'Narrow down the part of speech, tense, or contextual role of the answer.',
        f'The first letter of the answer is "{str(answer)[:1]}".',
        f'The answer is "{answer}". If you cannot type it, select "Give up".',
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
    ('g1', 'She ____ to school every day. (go)', 'goes', 'Third-person singular present tense requires "goes".'),
    ('g2', 'I have lived here ____ 2020.', 'since', 'Use "since" to indicate the starting point of an action.'),
    ('g3', 'If I ____ more time, I would travel.', 'had', 'Subjunctive past: the if-clause uses the past tense form.'),
    ('g4', 'This book ____ by many students.', 'is read', 'Passive voice = be verb + past participle.'),
    ('g5', 'He is taller ____ his brother.', 'than', 'Comparative adjectives are followed by "than".'),
    ('g6', 'There ____ two apples on the table.', 'are', 'The plural noun "two apples" requires the plural verb "are".'),
    ('g7', 'I enjoy ____ music. (listen)', 'listening to', '"enjoy" is followed by a gerund; "listen" requires "to".'),
    ('g8', 'She asked me ____ I was ready.', 'whether', '"whether" introduces an indirect yes/no question.'),
    ('g9', 'By next year, they ____ the project.', 'will have completed', 'Future perfect expresses an action completed before a future point.'),
    ('g10', 'The man ____ lives next door is a doctor.', 'who', '"who" is the subject relative pronoun for people.'),
    ('g11', 'Neither answer ____ correct.', 'is', '"Neither" is treated as singular and takes a singular verb.'),
    ('g12', 'I wish I ____ speak French.', 'could', 'Use "could" (past form) to express an unattainable present wish.'),
]

READING_DATA = [
    ('r1', 'Mina missed the bus, so she walked to school. How did Mina get to school?', 'walked', 'The text explicitly states she walked because she missed the bus.'),
    ('r2', 'The library closes at six, but Ken arrived at six thirty. Why could he not enter?', 'it was closed', 'Ken arrived 30 minutes after closing time, so the library was shut.'),
    ('r3', 'Aya took an umbrella because dark clouds covered the sky. What weather did she expect?', 'rain', 'Dark clouds and an umbrella signal she expected rain.'),
    ('r4', 'The blue whale is larger than any other animal. Which animal is the largest?', 'blue whale', 'The comparative phrase "larger than any other animal" identifies the blue whale as the largest.'),
    ('r5', 'Tom studied all week and passed the exam. What helped Tom pass?', 'studying', 'Studying all week is the cause directly linked to passing the exam.'),
    ('r6', 'Plants use sunlight to make food. What energy source do plants use?', 'sunlight', 'The text states "sunlight" directly as the energy source.'),
    ('r7', 'The café was crowded, yet we found one empty table. Was seating available?', 'yes', 'One empty table was found, so seating was available.'),
    ('r8', 'Lena whispered because the baby was sleeping. Why did Lena speak quietly?', 'the baby was sleeping', 'The "because" clause directly gives the reason for whispering.'),
    ('r9', 'After the storm, several roads were flooded. What caused the road closures?', 'flooding', 'Flooding after the storm caused the road closures.'),
    ('r10', 'The recipe serves four people. We have eight guests. How many batches are needed?', 'two', '8 ÷ 4 = 2, so two batches are needed.'),
    ('r11', 'Although the task was difficult, Rui finished it. Did difficulty stop Rui?', 'no', '"Although" signals contrast — Rui completed the task despite the difficulty.'),
    ('r12', 'The museum is free on Sundays. Today is Sunday. What is today\'s admission cost?', 'free', 'The text states the museum is free on Sundays.'),
]


def _vocabulary_questions(prefix='vocab'):
    return [
        _question(
            f'{prefix}-{word}', prompt, word,
            f'"{word}" means "{meaning}" and fits naturally in this context.',
            f'Now write one original sentence using "{word}".', section='vocabulary',
        )
        for word, meaning, prompt in VOCABULARY_DATA
    ]


def _grammar_questions():
    return [
        _question(key, prompt, answer, explanation, 'Write one original sentence using the same grammar rule.', section='grammar')
        for key, prompt, answer, explanation in GRAMMAR_DATA
    ]


def _reading_questions():
    return [
        _question(key, prompt, answer, explanation, 'Identify the exact words in the passage that support your answer.', section='reading')
        for key, prompt, answer, explanation in READING_DATA
    ]


COURSES = {
    'daily-english': {
        'title': 'Daily English Essentials',
        'description': 'Learn essential everyday vocabulary in context.',
        'questions': _vocabulary_questions('daily')[:10],
    },
    'academic-words': {
        'title': 'Academic Word Builder',
        'description': 'Build academic vocabulary for reports and presentations.',
        'questions': _vocabulary_questions('academic')[3:13],
    },
    'business-context': {
        'title': 'Business Vocabulary',
        'description': 'Practice business vocabulary with real-world example sentences.',
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
        q = _question(
            key,
            str(spec['prompt']),
            str(spec['answer']),
            str(spec['explanation']),
            str(spec.get('next_step') or 'Write one original sentence using the same concept.'),
            section=item_section,
            hints=hints,
        )
        # Carry the skill_focus label into the question dict for display in the UI
        q['skill_focus'] = str(spec.get('skill_focus') or '')
        questions.append(q)
    return questions


def generate_section_questions(section, *, count=10):
    if section in {'vocabulary', 'grammar', 'reading', 'diagnostic'}:
        try:
            specs = generate_ai_response(
                system_prompt=(
                    'You are an expert English language teacher creating quiz questions. '
                    'Return exactly the requested number of well-crafted questions. Each question must have: '
                    'prompt (the question text), '
                    'answer (short, unambiguous correct answer), '
                    'skill_focus (the specific language skill tested, e.g. "Past Tense", "Inference", "Vocabulary in Context"), '
                    'explanation (clear English explanation of why the answer is correct and what rule/principle applies), '
                    'next_step (one actionable study task in English for the learner to practise further), '
                    'hints (exactly 5 English hints progressing from a gentle nudge at level 1 to revealing the full answer at level 5).'
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
        raise ValueError('The selected course was not found.')
    return [dict(question) for question in course['questions']]


def _extract_pdf_text(data: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf. Returns empty string on failure."""
    try:
        import io as _io
        from pypdf import PdfReader
        reader = PdfReader(_io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ''
            if text.strip():
                pages.append(text)
        return '\n'.join(pages)
    except Exception:
        return ''


def _decode_upload(upload) -> str:
    """Read an uploaded file and return its plain text content.

    Handles PDF via pypdf, JSON/CSV/text via encoding detection.
    Falls back to latin-1 byte decoding as a last resort for unknown formats.
    """
    data = upload.read()
    name = upload.name.lower()

    # PDF: use a proper PDF parser — never decode binary PDF as text
    if name.endswith('.pdf'):
        text = _extract_pdf_text(data)
        if text.strip():
            return text
        # PDF has no extractable text (e.g. scanned image-only PDF)
        raise ValueError(
            'The PDF appears to be a scanned image with no extractable text. '
            'Please upload a text-based PDF, TXT, or Markdown file.'
        )

    # Plain text files: try common encodings
    for encoding in ('utf-8-sig', 'utf-8', 'utf-16', 'shift-jis'):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode('latin-1', errors='ignore')


_UPLOAD_SYSTEM_PROMPTS = {
    'reading': (
        'You are an expert English reading teacher designing questions for language learners. '
        'Create questions STRICTLY based on the supplied passage. '
        'Distribute the questions across these reading skill levels (Bloom\'s Taxonomy): '
        '- 2 LITERAL questions: ask who/what/where/when using exact words from the text. '
        '- 3 INFERENCE questions: ask why/how/what-does-this-imply — answer must be derived from clues in the text, not stated directly. '
        '- 2 MAIN IDEA questions: ask about the central message, topic, or purpose of a paragraph. '
        '- 2 VOCABULARY-IN-CONTEXT questions: ask what a specific word or phrase means AS USED in the passage (not a dictionary definition). '
        '- 1 CAUSE-AND-EFFECT question: ask what caused X, or what was the result of Y. '
        'Rules: '
        '(1) Every answer must be a short phrase (1–6 words). '
        '(2) Answers must be clearly supported by the text. '
        '(3) skill_focus must be one of: Literal Detail, Inference, Main Idea, Vocabulary in Context, Cause and Effect. '
        '(4) explanation must quote the relevant sentence from the passage and explain why that answer is correct. '
        '(5) next_step must ask the learner to find and quote the supporting sentence from the text. '
        '(6) hints must be exactly 5, progressing: '
        '  hint1=point to the relevant paragraph, '
        '  hint2=point to the relevant sentence, '
        '  hint3=give a conceptual clue about the answer type, '
        '  hint4=give the first word of the answer, '
        '  hint5=state the full answer. '
        'Return exactly the requested count as a JSON array.'
    ),
    'grammar': (
        'You are an expert English grammar teacher designing questions for language learners. '
        'Create questions STRICTLY based on sentences from the supplied text. '
        'Mix these question types evenly: '
        '- FILL-IN-THE-BLANK: take a sentence from the text, remove one grammatical element, ask the learner to fill it in. '
        '- ERROR CORRECTION: take a sentence from the text, introduce one grammatical error, ask the learner to identify and correct it. '
        '- SENTENCE TRANSFORMATION: give a sentence from the text and ask the learner to rewrite it in another form (e.g., active→passive, affirmative→negative, present→past). '
        'Target grammar points present in the material such as: verb tenses, subject-verb agreement, articles (a/an/the), '
        'prepositions, passive voice, relative clauses, conditionals, modal verbs, gerunds vs infinitives, '
        'comparatives/superlatives, reported speech, conjunctions. '
        'Rules: '
        '(1) skill_focus must name the exact grammar rule being tested, e.g. "Present Perfect Tense", "Passive Voice", "Third Conditional". '
        '(2) prompt must clearly show the question type (e.g., start with "Fill in the blank:", "Correct the error:", "Transform the sentence:"). '
        '(3) answer must be the corrected or completed text (short phrase or full clause). '
        '(4) explanation must state the grammar RULE explicitly (e.g., "The present perfect uses have/has + past participle to...") and then show why the answer applies. '
        '(5) next_step must ask the learner to write one original sentence using the same grammar rule. '
        '(6) hints must be exactly 5, progressing: '
        '  hint1=name the grammar category (e.g., "Think about verb tense here."), '
        '  hint2=state the grammar rule in simple terms, '
        '  hint3=give the sentence structure/formula (e.g., "Subject + have/has + past participle"), '
        '  hint4=give the first word(s) of the answer, '
        '  hint5=state the full answer. '
        'Return exactly the requested count as a JSON array.'
    ),
    'vocabulary': (
        'You are an expert English vocabulary teacher. '
        'Create vocabulary questions ONLY from the supplied learning material. '
        'Follow the learner instruction. '
        'For each question: skill_focus must name the vocabulary strategy used '
        '(e.g., "Context Clues", "Word Form", "Collocations", "Synonyms/Antonyms"). '
        'Return exactly the requested count. Each item must have one concise answer, '
        'a clear English explanation showing why that word fits, a next study step, '
        'and exactly five English hints that progress from subtle to answer-revealing at level 5.'
    ),
    'myself': (
        'You create language-learning questions only from the supplied learning material. '
        'Follow the learner instruction. Return exactly the requested count. Each item must '
        'have one concise answer, a clear English explanation, next study step, skill_focus label, '
        'and exactly five English hints that progress from subtle to revealing the answer at level 5.'
    ),
}


def generate_uploaded_questions(files, instruction, *, section='myself', count=10):
    """Create questions from user-uploaded material using section-aware AI prompts."""
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
        raise ValueError('No readable text could be extracted from the uploaded file(s).')

    material = '\n'.join(chunks)[:16000]
    system_prompt = _UPLOAD_SYSTEM_PROMPTS.get(section, _UPLOAD_SYSTEM_PROMPTS['myself'])
    try:
        specs = generate_ai_response(
            system_prompt=system_prompt,
            user_prompt=(
                f'Learner instruction: {instruction}\n'
                f'Question count: {count}\n'
                f'Material:\n{material}'
            ),
            response_schema=AI_QUESTION_SCHEMA,
        )
        generated = _questions_from_ai(specs, section, count)
        if generated:
            return generated, ', '.join(names)
    except AIEngineError:
        pass

    # --- Smart rule-based fallback (when AI is unavailable) ---
    # Pick the longest, most content-rich sentences as source material
    sentences = [
        s.strip() for s in re.split(r'(?<=[.!?])\s+', '\n'.join(chunks))
        if len(s.strip()) > 40
    ]
    if not sentences:
        sentences = [c for c in chunks if len(c) > 20] or chunks

    random.shuffle(sentences)
    questions = []

    for index in range(count):
        sentence = sentences[index % len(sentences)]
        words = re.findall(r'\b[A-Za-z]{4,}\b', sentence)
        key = hashlib.sha256(f'{sentence}|{index}|{section}'.encode('utf-8')).hexdigest()[:20]

        if section == 'reading':
            # Reading fallback: ask a genuine comprehension question about the sentence
            skill_types = [
                'main_idea', 'detail', 'inference', 'vocab', 'cause_effect'
            ]
            skill = skill_types[index % len(skill_types)]

            if skill == 'main_idea':
                q_prompt = f'What is the main idea expressed in this sentence from the passage?\n\n"{sentence}"'
                q_answer = words[-1].lower() if words else sentence.split()[-1].lower()
                skill_label = 'Main Idea'
                explanation = f'The sentence "{ sentence }" expresses its central point through the word "{q_answer}".'
                next_step_text = 'Re-read the surrounding paragraph and identify which sentence best supports this idea.'
                hints = [
                    'Read the full sentence carefully and identify its subject.',
                    'Ask yourself: what is this sentence primarily about?',
                    f'Focus on the final part of the sentence: "...{sentence[-50:]}"',
                    f'The answer is a word found near the end of the sentence.',
                    f'The answer is "{q_answer}".'
                ]
            elif skill == 'detail':
                target = words[0] if words else sentence.split()[0]
                q_prompt = f'According to the passage, complete the detail: "{sentence.replace(target, "____", 1)}"'
                q_answer = target.lower()
                skill_label = 'Literal Detail'
                explanation = f'The text states this directly: "{sentence}". The missing word is "{target}".'
                next_step_text = 'Find and quote the exact sentence from the passage that confirms this detail.'
                hints = [
                    'Look at the beginning of the sentence for context.',
                    'The answer is a specific word used directly in the passage.',
                    f'The sentence starts with: "{sentence[:40]}..."',
                    f'The answer has {len(target)} letters and starts with "{target[0]}".'
                    f' The answer is "{q_answer}".'
                ]
            elif skill == 'vocab':
                target = max(words, key=len) if words else 'word'
                q_prompt = f'What does the word "{target}" mean as used in this sentence?\n\n"{sentence}"'
                q_answer = target.lower()
                skill_label = 'Vocabulary in Context'
                explanation = f'In context, "{target}" refers to the concept described in the sentence: "{sentence}".'
                next_step_text = f'Use "{target}" in a new sentence with a different subject.'
                hints = [
                    f'Read the whole sentence and think about what "{target}" is doing grammatically.',
                    'Is it a noun, verb, or adjective? That helps narrow the meaning.',
                    f'Look at the words before and after "{target}" for clues.',
                    f'The answer is the word itself: it starts with "{target[0]}".'
                    f' The answer is "{q_answer}".'
                ]
            elif skill == 'cause_effect':
                q_prompt = f'What is the likely cause or result described in this sentence?\n\n"{sentence}"'
                q_answer = (words[-1] if words else 'result').lower()
                skill_label = 'Cause and Effect'
                explanation = f'The sentence "{sentence}" describes a cause-and-effect relationship. The key outcome is "{q_answer}".'
                next_step_text = 'Find another sentence in the passage that shows a cause-and-effect relationship.'
                hints = [
                    'Look for signal words like "because", "therefore", "as a result", "so".'
                    ' These words mark cause-effect relationships.',
                    'Identify what happened and why it happened in the sentence.',
                    f'Focus on the second half of the sentence: "...{sentence[-60:]}"',
                    f'The key term starts with "{q_answer[0]}".'
                    f' The answer is "{q_answer}".'
                ]
            else:  # inference
                q_prompt = f'Based on this sentence, what can you infer about the topic?\n\n"{sentence}"'
                q_answer = (words[len(words) // 2] if words else 'implied').lower()
                skill_label = 'Inference'
                explanation = f'Although not stated directly, the sentence "{sentence}" implies that "{q_answer}" is a key concept.'
                next_step_text = 'Explain in one sentence why you think this inference is supported by the text.'
                hints = [
                    'Inferences are not stated directly — you need to "read between the lines".',
                    'Think about what the author assumes the reader already knows.',
                    f'Look at the whole sentence and consider its broader context.',
                    f'The implied concept starts with "{q_answer[0]}".'
                    f' The answer is "{q_answer}".'
                ]

        else:  # grammar section
            # Grammar fallback: create fill-in-the-blank on actual grammatical words
            # Target prepositions, auxiliary verbs, articles, conjunctions — real grammar words
            grammar_targets = re.findall(
                r'\b(is|are|was|were|has|have|had|will|would|could|should|may|might'
                r'|be|been|being|do|does|did'
                r'|a|an|the'
                r'|in|on|at|by|for|with|about|from|to|of|into|through|during|before|after'
                r'|because|although|however|therefore|since|while|when|if|unless|until'
                r'|which|who|that|whose)\b',
                sentence, flags=re.IGNORECASE
            )
            if grammar_targets:
                target = grammar_targets[0]
                blanked = re.sub(r'\b' + re.escape(target) + r'\b', '____', sentence, count=1, flags=re.IGNORECASE)
                q_prompt = f'Fill in the blank with the correct word:\n\n"{blanked}"'
                q_answer = target.lower()
                skill_label = 'Grammar: Function Word'
                explanation = (
                    f'The correct word is "{target}". In the sentence "{sentence}", '
                    f'it functions as a grammatical element that connects or qualifies other parts of the sentence.'
                )
                next_step_text = f'Write a new sentence using "{target}" in the same grammatical role.'
                hints = [
                    'Focus on the grammatical structure of the sentence — what type of word is missing? (preposition, article, conjunction, auxiliary verb)',
                    'Look at what comes before and after the blank to determine the word type needed.',
                    f'The sentence structure suggests a {"preposition" if target.lower() in "in on at by for with about from to of into through during before after" else "function word"} is needed.',
                    f'The answer starts with "{target[0]}" and has {len(target)} letters.',
                    f'The answer is "{q_answer}".'
                ]
            else:
                # Last-resort: find a content word to blank
                target = max(words, key=len) if words else 'concept'
                blanked = sentence.replace(target, '____', 1)
                q_prompt = f'Fill in the blank with the correct word from the passage:\n\n"{blanked}"'
                q_answer = target.lower()
                skill_label = 'Grammar: Vocabulary'
                explanation = f'The word "{target}" completes the sentence correctly: "{sentence}"'
                next_step_text = f'Use "{target}" in a new sentence that demonstrates the same meaning.'
                hints = [
                    'Read the full sentence and think about what part of speech fits in the blank.',
                    f'The sentence context is: "{sentence[:60]}..."',
                    f'The answer has {len(target)} letters.',
                    f'The answer starts with "{target[0]}".'
                    f' The answer is "{q_answer}".'
                ]

        questions.append(_question(
            f'upload-{key}',
            q_prompt,
            q_answer,
            explanation,
            next_step_text,
            section=section,
            hints=hints[:5],
        ))
        questions[-1]['skill_focus'] = skill_label

    return questions, ', '.join(names)


def missing_questions(session_key, *, count=10):
    records = list(MissingLanguageQuestion.objects.filter(browser_session_key=session_key))
    random.shuffle(records)
    return [
        _question(
            record.fingerprint, record.prompt, record.reference_answer,
            record.explanation, record.next_step, section='missing',
            hints=record.hints if record.hints else None,
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
            {'title': 'Academic Word Builder', 'detail': 'Your foundations look solid — try advancing to higher-level vocabulary.'},
            {'title': 'Long-form Reading', 'detail': 'Practice finding supporting evidence quickly in longer passages.'},
        ]
    weakest = max(wrong_sections, key=wrong_sections.get)
    mapping = {
        'vocabulary': ('Vocabulary', 'Review words alongside example sentences in Missing and the Vocabulary courses.'),
        'grammar': ('Grammar', 'Turn each incorrect grammar rule into an example sentence and try again.'),
        'reading': ('Reading', 'Practice marking conjunctions and evidence sentences while reading.'),
    }
    title, detail = mapping.get(weakest, mapping['vocabulary'])
    return [
        {'title': f'Recommended: {title}', 'detail': detail},
        {'title': 'Related: Missing', 'detail': 'Questions you got wrong this session are saved in Missing. They disappear once you answer correctly.'},
    ]
