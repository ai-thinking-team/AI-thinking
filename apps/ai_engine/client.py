import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .exceptions import AIServiceUnavailable, InvalidAIResponse


def _gemini_schema(schema):
    """Convert the app's compact schema notation to Gemini JSON Schema."""
    if not schema:
        return None
    if isinstance(schema, str):
        return {'type': schema}
    if isinstance(schema, list):
        item = schema[0] if schema else 'string'
        return {'type': 'array', 'items': _gemini_schema(item)}
    if isinstance(schema, dict) and 'type' in schema:
        return schema
    if isinstance(schema, dict):
        properties = {key: _gemini_schema(value) for key, value in schema.items()}
        if 'gap_type' in properties:
            properties['gap_type'] = {'type': ['string', 'null']}
        return {'type': 'object', 'properties': properties, 'required': list(properties)}
    return {'type': 'string'}


def generate_ai_response(*, system_prompt, user_prompt, response_schema=None):
    """Return validated AI output behind one provider-neutral boundary.

    Provider integration is intentionally deferred. Importing this module never
    performs a network call, and missing configuration fails safely.
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise AIServiceUnavailable(
            'AI support is unavailable. Continue with the curated diagnostic and hint ladder.'
        )

    model = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash-lite')
    payload = {
        'system_instruction': {'parts': [{'text': system_prompt}]},
        'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
        'generationConfig': {'temperature': 0.35, 'maxOutputTokens': 4096},
    }
    converted_schema = _gemini_schema(response_schema)
    if converted_schema:
        payload['generationConfig'].update({
            'responseMimeType': 'application/json',
            'responseSchema': converted_schema,
        })

    request = Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key},
        method='POST',
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AIServiceUnavailable('Gemini API could not be reached safely.') from exc

    try:
        text = body['candidates'][0]['content']['parts'][0]['text']
        return json.loads(text) if converted_schema else text
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidAIResponse('Gemini returned an invalid or blocked response.') from exc


_QUESTION_SCHEMA = [{
    'prompt': 'string',
    'reference_answer': 'string',
    'question_type': 'string',
    'skill_focus': 'string',
    'rubric_target_gap': 'string',
    'transfer_prompt': 'string',
}]

_SECTION_SYSTEM_PROMPTS = {
    'reading': (
        'You are an expert English reading teacher designing questions for language learners. '
        'Create EXACTLY {{count}} questions STRICTLY based on the supplied passage. '
        'Distribute across these reading skill levels (Bloom\'s Taxonomy): '
        '- 2 LITERAL questions: ask who/what/where/when using exact words from the text. '
        '- 3 INFERENCE questions: ask why/how/what-does-this-imply — answer derived from clues, not stated directly. '
        '- 2 MAIN IDEA questions: ask about the central message or purpose of a paragraph. '
        '- 2 VOCABULARY-IN-CONTEXT questions: ask what a specific word/phrase means AS USED in the passage. '
        '- 1 CAUSE-AND-EFFECT question: ask what caused X, or what was the result of Y. '
        'Rules: '
        '(1) Every reference_answer must be a short phrase (1-6 words) supported by the text. '
        '(2) question_type must always be "READING". '
        '(3) skill_focus must be one of: Literal Detail, Inference, Main Idea, Vocabulary in Context, Cause and Effect. '
        '(4) rubric_target_gap must always be "context_misunderstanding". '
        '(5) transfer_prompt must ask the learner to find and quote the supporting sentence from the text.'
    ),
    'grammar': (
        'You are an expert English grammar teacher designing questions for language learners. '
        'Create EXACTLY {{count}} questions STRICTLY based on sentences from the supplied text. '
        'Mix these question types evenly across the set: '
        '- FILL-IN-THE-BLANK: take a sentence from the text, remove one grammatical element, ask the learner to fill it in. '
        '- ERROR CORRECTION: take a sentence from the text, introduce one grammatical error, ask the learner to identify and correct it. '
        '- SENTENCE TRANSFORMATION: give a sentence from the text and ask the learner to rewrite it (e.g., active->passive, present->past). '
        'Target grammar points present in the material such as: verb tenses, subject-verb agreement, '
        'articles (a/an/the), prepositions, passive voice, relative clauses, conditionals, modal verbs, '
        'gerunds vs infinitives, comparatives/superlatives. '
        'Rules: '
        '(1) question_type must always be "GRAMMAR". '
        '(2) skill_focus must name the exact grammar rule being tested (e.g., "Present Perfect Tense", "Passive Voice"). '
        '(3) rubric_target_gap must always be "grammar_misconception". '
        '(4) prompt must start with the question type label: "Fill in the blank:", "Correct the error:", or "Transform the sentence:". '
        '(5) reference_answer must be the corrected/completed short phrase or clause. '
        '(6) transfer_prompt must ask the learner to write one original sentence using the same grammar rule.'
    ),
}


def generate_questions_from_text(raw_text, subject_name='Languages', count=10, section='reading'):
    """Generate AI-powered quiz questions from raw text for reading or grammar sections.

    Calls Gemini with a section-aware prompt to produce high-quality English questions.
    Falls back to rule-based generation if AI is unavailable.

    Args:
        raw_text: Extracted text from the uploaded file.
        subject_name: Used for context (default 'Languages').
        count: Number of questions to generate (default 10).
        section: 'reading' or 'grammar' — controls the AI prompt used.

    Returns:
        List of question spec dicts with keys:
            prompt, reference_answer, question_type, rubric, transfer_prompt.
    """
    cleaned_text = (raw_text or '').strip()
    if not cleaned_text:
        return []

    # --- Attempt AI generation ---
    system_template = _SECTION_SYSTEM_PROMPTS.get(section, _SECTION_SYSTEM_PROMPTS['reading'])
    system_prompt = system_template.format(count=count)
    material = cleaned_text[:12000]  # Limit to avoid token overflow

    try:
        specs = generate_ai_response(
            system_prompt=system_prompt,
            user_prompt=(
                f'Generate {count} {section} questions from this material.\n\n'
                f'Material:\n{material}'
            ),
            response_schema=_QUESTION_SCHEMA,
        )
        if isinstance(specs, list) and len(specs) >= count:
            questions = []
            for spec in specs[:count]:
                if not isinstance(spec, dict):
                    continue
                questions.append({
                    'prompt': str(spec.get('prompt', '')),
                    'reference_answer': str(spec.get('reference_answer', '')).lower(),
                    'question_type': str(spec.get('question_type', section.upper())),
                    'rubric': {
                        'target_gap': str(spec.get('rubric_target_gap', 'context_misunderstanding')),
                        'source': 'uploaded_file',
                    },
                    'transfer_prompt': str(spec.get('transfer_prompt', '')),
                })
            if len(questions) >= count:
                return questions
    except (AIServiceUnavailable, InvalidAIResponse):
        pass

    # --- Smart rule-based fallback (when AI is unavailable) ---
    # Use full sentences as source — much better than individual words
    sentences = [
        s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned_text)
        if len(s.strip()) > 40
    ]
    if not sentences:
        sentences = [line.strip() for line in cleaned_text.splitlines() if len(line.strip()) > 20]
    if not sentences:
        return []

    q_type = section.upper()
    gap_type = 'context_misunderstanding' if section == 'reading' else 'grammar_misconception'
    skill_cycle_reading = ['Literal Detail', 'Inference', 'Main Idea', 'Vocabulary in Context', 'Cause and Effect']
    questions = []

    for i in range(min(count, len(sentences) * 3)):
        sentence = sentences[i % len(sentences)]
        words = re.findall(r'\b[A-Za-z]{4,}\b', sentence)

        if section == 'reading':
            skill_label = skill_cycle_reading[i % len(skill_cycle_reading)]
            if skill_label == 'Literal Detail':
                target = words[0] if words else sentence.split()[0]
                blanked = sentence.replace(target, '____', 1)
                q_prompt = f'According to the passage, fill in the missing detail:\n\n"{blanked}"'
                q_answer = target.lower()
                transfer = 'Find and quote the sentence from the passage that confirms this detail.'
            elif skill_label == 'Main Idea':
                q_prompt = f'What is the main idea expressed in this sentence from the passage?\n\n"{sentence}"'
                q_answer = (words[-1] if words else sentence.split()[-1]).lower()
                transfer = 'In your own words, write a one-sentence summary of this part of the passage.'
            elif skill_label == 'Vocabulary in Context':
                target = max(words, key=len) if words else 'concept'
                q_prompt = f'What does the word "{target}" mean as used in the following sentence?\n\n"{sentence}"'
                q_answer = target.lower()
                transfer = f'Use "{target}" in a new sentence about a different topic.'
            elif skill_label == 'Cause and Effect':
                q_prompt = f'What is the cause or effect described in this sentence?\n\n"{sentence}"'
                q_answer = (words[-1] if words else 'result').lower()
                transfer = 'Find another sentence in the passage that also shows a cause-and-effect relationship.'
            else:  # Inference
                q_prompt = f'Based on this sentence, what can you infer about the topic?\n\n"{sentence}"'
                q_answer = (words[len(words) // 2] if words else 'concept').lower()
                transfer = 'Explain in one sentence what evidence in the text supports this inference.'

        else:  # grammar
            # Target real grammar words: auxiliary verbs, prepositions, articles, conjunctions
            grammar_targets = re.findall(
                r'\b(is|are|was|were|has|have|had|will|would|could|should|may|might'
                r'|be|been|being|do|does|did'
                r'|a|an|the'
                r'|in|on|at|by|for|with|about|from|to|of|into|through|before|after'
                r'|because|although|however|therefore|since|while|when|if|unless|until'
                r'|which|who|that|whose)\b',
                sentence, flags=re.IGNORECASE
            )
            if grammar_targets:
                target = grammar_targets[i % len(grammar_targets)]
                blanked = re.sub(r'\b' + re.escape(target) + r'\b', '____', sentence, count=1, flags=re.IGNORECASE)
                q_prompt = f'Fill in the blank with the correct grammatical word:\n\n"{blanked}"'
                q_answer = target.lower()
                skill_label = 'Grammar: Function Word'
            else:
                target = max(words, key=len) if words else 'word'
                blanked = sentence.replace(target, '____', 1)
                q_prompt = f'Fill in the blank with the correct word:\n\n"{blanked}"'
                q_answer = target.lower()
                skill_label = 'Grammar: Vocabulary'
            transfer = f'Write a new sentence using "{target}" in the same grammatical role.'

        questions.append({
            'prompt': q_prompt,
            'reference_answer': q_answer,
            'question_type': q_type,
            'skill_focus': skill_label if section == 'reading' else skill_label,
            'rubric': {
                'target_gap': gap_type,
                'source': 'uploaded_file',
                'sentence': sentence[:120],
            },
            'transfer_prompt': transfer,
        })

    return questions[:count]

