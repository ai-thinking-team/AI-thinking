import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .exceptions import AIServiceUnavailable, InvalidAIResponse


OPENAI_RESPONSES_URL = 'https://api.openai.com/v1/responses'


def _json_schema(schema):
    """Convert the app's compact schema notation to strict JSON Schema."""
    if isinstance(schema, str):
        return {'type': schema}
    if isinstance(schema, list):
        item = schema[0] if schema else 'string'
        return {'type': 'array', 'items': _json_schema(item)}
    if isinstance(schema, dict) and 'type' in schema:
        return schema
    if isinstance(schema, dict):
        properties = {key: _json_schema(value) for key, value in schema.items()}
        return {
            'type': 'object',
            'properties': properties,
            'required': list(properties),
            'additionalProperties': False,
        }
    return {'type': 'string'}


def _extract_output_text(body):
    if isinstance(body.get('output_text'), str):
        return body['output_text']
    for output in body.get('output', []):
        for content in output.get('content', []):
            if content.get('type') == 'output_text' and isinstance(content.get('text'), str):
                return content['text']
    raise InvalidAIResponse('OpenAI returned no readable output.')


def generate_ai_response(*, system_prompt, user_prompt, response_schema=None):
    """Call OpenAI Responses API behind one validated application boundary."""
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key:
        raise AIServiceUnavailable(
            'AI support is unavailable because OPENAI_API_KEY is not configured.'
        )

    payload = {
        'model': os.environ.get('OPENAI_MODEL', 'gpt-5.6-luna'),
        'instructions': system_prompt,
        'input': user_prompt,
        'max_output_tokens': 6000,
    }
    unwrap_array = False
    if response_schema:
        converted = _json_schema(response_schema)
        # Structured Outputs requires a top-level object schema.
        if converted.get('type') == 'array':
            converted = {
                'type': 'object',
                'properties': {'items': converted},
                'required': ['items'],
                'additionalProperties': False,
            }
            unwrap_array = True
        payload['text'] = {
            'format': {
                'type': 'json_schema',
                'name': 'app_response',
                'strict': True,
                'schema': converted,
            }
        }

    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise AIServiceUnavailable(f'OpenAI API request failed (HTTP {exc.code}).') from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AIServiceUnavailable('OpenAI API could not be reached safely.') from exc

    text = _extract_output_text(body)
    if not response_schema:
        return text
    try:
        result = json.loads(text)
        return result['items'] if unwrap_array else result
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidAIResponse('OpenAI returned invalid structured output.') from exc


_MATERIAL_QUESTION_SCHEMA = [{
    'prompt': 'string',
    'reference_answer': 'string',
    'question_type': 'string',
    'skill_focus': 'string',
    'rubric_target_gap': 'string',
    'transfer_prompt': 'string',
}]


def generate_questions_from_text(raw_text, subject_name='Languages', count=10, section='reading'):
    """Compatibility entry point for the legacy upload workflow, now using OpenAI."""
    material = (raw_text or '').strip()[:12000]
    if not material:
        return []
    try:
        specs = generate_ai_response(
            system_prompt=(
                'You are an English teacher. Create questions only from the supplied material. '
                'Return exactly the requested count. Use short, unambiguous reference answers. '
                'For reading, test detail, inference, main idea, vocabulary in context, and cause/effect. '
                'For grammar, use fill-in-the-blank, error correction, and sentence transformation.'
            ),
            user_prompt=(
                f'Subject: {subject_name}\nSection: {section}\nQuestion count: {count}\n'
                f'Material:\n{material}'
            ),
            response_schema=_MATERIAL_QUESTION_SCHEMA,
        )
        if isinstance(specs, list) and len(specs) >= count:
            result = []
            for spec in specs[:count]:
                if not isinstance(spec, dict) or not spec.get('prompt') or not spec.get('reference_answer'):
                    return []
                result.append({
                    'prompt': str(spec['prompt']),
                    'reference_answer': str(spec['reference_answer']).casefold(),
                    'question_type': str(spec.get('question_type') or section.upper()),
                    'skill_focus': str(spec.get('skill_focus') or ''),
                    'rubric': {
                        'target_gap': str(spec.get('rubric_target_gap') or (
                            'context_misunderstanding' if section == 'reading' else 'grammar_misconception'
                        )),
                        'source': 'uploaded_file',
                    },
                    'transfer_prompt': str(spec.get('transfer_prompt') or ''),
                })
            return result
    except (AIServiceUnavailable, InvalidAIResponse):
        pass

    sentences = [
        sentence.strip()
        for sentence in re.split(r'(?<=[.!?])\s+|\r?\n', material)
        if len(sentence.strip()) > 20
    ]
    questions = []
    for index in range(count):
        sentence = sentences[index % len(sentences)] if sentences else material
        words = re.findall(r'\b[A-Za-z]{3,}\b', sentence)
        answer = (words[index % len(words)] if words else sentence.split()[0]).casefold()
        questions.append({
            'prompt': f'Complete or explain this {section} excerpt: "{sentence.replace(answer, "____", 1)}"',
            'reference_answer': answer,
            'question_type': section.upper(),
            'skill_focus': 'Text evidence' if section == 'reading' else 'Grammar in context',
            'rubric': {
                'target_gap': 'context_misunderstanding' if section == 'reading' else 'grammar_misconception',
                'source': 'uploaded_file',
            },
            'transfer_prompt': 'Write one new sentence using the same idea or rule.',
        })
    return questions
