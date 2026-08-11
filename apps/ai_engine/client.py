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


def generate_questions_from_text(raw_text, subject_name='Languages', count=3):
    """Generate diagnostic quiz questions based on raw text extracted from uploaded files."""
    cleaned_text = (raw_text or '').strip()
    if not cleaned_text:
        return []

    lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
    words = re.findall(r'\b[A-Za-z]{3,}\b', cleaned_text)

    questions = []
    total_items = max(1, len(lines))

    for i in range(min(count, total_items)):
        line = lines[i % total_items]
        target_word = words[i % len(words)] if words else 'key_concept'

        if target_word in line:
            blanked_prompt = line.replace(target_word, '____', 1)
        else:
            blanked_prompt = f'取り込んだ教材テキストに基づく確認問題: "{line[:70]}..." に当てはまるキーワード "____"'

        q_type = 'vocabulary' if i % 2 == 0 else 'grammar'
        gap_type = 'vocabulary_gap' if i % 2 == 0 else 'grammar_misconception'

        questions.append({
            'prompt': f'【ファイル取り込み問題 {i+1}】 {blanked_prompt}',
            'reference_answer': target_word.lower(),
            'question_type': q_type,
            'rubric': {
                'target_gap': gap_type,
                'source': 'uploaded_file',
                'extracted_line': line[:100],
            },
            'transfer_prompt': f'【応用問題 {i+1}】 次の類似文脈に当てはまる語句を選択してください: "{target_word.capitalize()} の適切な用法: ____"',
        })

    return questions
