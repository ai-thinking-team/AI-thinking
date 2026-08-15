import base64
import json
import os
import re
import urllib.error
import urllib.request

from .exceptions import AIEngineError, AIServiceUnavailable, InvalidAIResponse

GEMINI_MODEL = 'gemini-flash-latest'
GEMINI_ENDPOINT = (
    f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
)

DEFAULT_GROQ_MODEL = 'openai/gpt-oss-20b'
GROQ_ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'

# name -> its required API key env var
_PROVIDER_ENV_VARS = {
    'gemini': 'GEMINI_API_KEY',
    'groq': 'GROQ_API_KEY',
}
_DEFAULT_PROVIDER_ORDER = ('gemini', 'groq')


def is_ai_configured():
    return bool(os.environ.get('GEMINI_API_KEY') or os.environ.get('GROQ_API_KEY'))


def _provider_order():
    """Default order is Gemini, then Groq — but AI_PROVIDER (optional), if
    set to one of the configured names, moves that provider to the front
    without dropping the other as fallback. Lets an operator prefer a
    specific provider (e.g. to route around another provider's rate
    limit) without losing the existing resilience."""
    preferred = os.environ.get('AI_PROVIDER', '').strip().lower()
    if preferred in _PROVIDER_ENV_VARS:
        return (preferred, *(name for name in _DEFAULT_PROVIDER_ORDER if name != preferred))
    return _DEFAULT_PROVIDER_ORDER


def _json_schema(schema):
    """Convert the app's compact schema notation (e.g. a bare 'string', or
    a dict of field name -> type with no explicit 'type' key) to strict
    JSON Schema. A schema that already looks like JSON Schema (has a
    top-level 'type') is returned unchanged, so callers that already build
    full JSON Schema (apps/math_quiz/ai_prompts.py) and callers that use
    the compact shorthand (generate_questions_from_text below) can share
    this one converter."""
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


def generate_ai_response(
    *, system_prompt, user_prompt, response_schema=None, files=None
):
    """Return validated AI output behind one provider-neutral boundary.

    Tries every configured provider in turn — by default Gemini, then
    Groq, or starting from AI_PROVIDER's choice if set (see
    _provider_order) — and returns the first one that actually answers. A
    provider being *configured* (a key is present) doesn't mean it's
    currently *working* (out of quota, rate-limited, network trouble,
    ...), so a failure there falls through to the next provider instead
    of giving up. Set `files` to a list of `(file_bytes, mime_type)` pairs
    to attach one or more uploaded files (image, PDF, ...) alongside the
    prompt — Groq's request is text-only (see _generate_groq_response)
    and ignores this, so whenever `files` is non-empty Gemini is tried
    first regardless of AI_PROVIDER: trying a file-blind provider first
    would silently succeed while ignoring every attached file.

    Returns the provider's raw text when no response_schema is given.
    When one is given (as either full JSON Schema or the compact
    shorthand — see _json_schema), the response is parsed here and the
    resulting dict/list is returned directly: passing a schema is the
    caller's declaration that it wants structured output, so parsing is
    this function's job rather than every caller's. A schema whose
    natural shape is a list gets wrapped in a top-level object for the
    request (both providers' structured-output modes require that) and
    unwrapped again before returning.
    """
    converted_schema = None
    unwrap_array = False
    if response_schema is not None:
        converted_schema = _json_schema(response_schema)
        if converted_schema.get('type') == 'array':
            converted_schema = {
                'type': 'object',
                'properties': {'items': converted_schema},
                'required': ['items'],
                'additionalProperties': False,
            }
            unwrap_array = True

    generators = {
        'gemini': _generate_gemini_response,
        'groq': _generate_groq_response,
    }
    order = _provider_order()
    if files:
        order = ('gemini', *(name for name in order if name != 'gemini'))
    attempts = [
        generators[name] for name in order
        if os.environ.get(_PROVIDER_ENV_VARS[name])
    ]

    if not attempts:
        raise AIServiceUnavailable(
            'AI support is unavailable. Continue with the curated diagnostic and hint ladder.'
        )

    text = None
    last_error = None
    for generate in attempts:
        try:
            text = generate(
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_schema=converted_schema, files=files,
            )
            break
        except AIEngineError as exc:
            last_error = exc
    if text is None:
        raise last_error

    if response_schema is None:
        return text
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidAIResponse('AI provider returned invalid structured output.') from exc
    if not unwrap_array:
        return result
    try:
        return result['items']
    except (KeyError, TypeError) as exc:
        raise InvalidAIResponse('AI provider returned invalid structured output.') from exc


REQUEST_TIMEOUT_SECONDS = 45

# urllib's default User-Agent ("Python-urllib/3.x") is bot-flagged by
# Cloudflare (fronting Groq's API, and possibly others) and gets a bare
# 403 before the request ever reaches the provider's own API layer — a
# generic browser-like one gets through. Set centrally here rather than
# per-provider since every request goes through this one function.
_USER_AGENT = 'Mozilla/5.0'

# Matches Groq's API key format (gsk_...) so it never leaks into a
# surfaced error message if it happens to appear in the provider's
# response body (e.g. an auth error echoing the bad key back).
_API_KEY_PATTERN = re.compile(r'gsk_[A-Za-z0-9_-]+')


def _request_json(request):
    request.add_header('User-Agent', _USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = _API_KEY_PATTERN.sub('[redacted]', exc.read().decode('utf-8', errors='replace'))
        if exc.code == 429:
            raise AIServiceUnavailable(
                'AI利用の上限（レート制限）に達しました。しばらく待ってから再試行してください。'
            ) from exc
        raise AIServiceUnavailable(f'AI provider returned an error ({exc.code}): {detail}') from exc
    except urllib.error.URLError as exc:
        raise AIServiceUnavailable('Could not reach the AI provider.') from exc
    except TimeoutError as exc:
        # A read timeout past the deadline raises bare TimeoutError, not
        # URLError — must be caught separately or it escapes as an
        # unhandled 500 instead of the graceful AIServiceUnavailable path.
        raise AIServiceUnavailable('AI provider did not respond in time.') from exc


# --- Gemini -----------------------------------------------------------

def _gemini_schema(schema):
    """Strip schema keys Gemini's structured-output parser rejects
    (e.g. `additionalProperties`, included for the stricter OpenAI format)."""
    if isinstance(schema, dict):
        return {
            key: _gemini_schema(value)
            for key, value in schema.items()
            if key != 'additionalProperties'
        }
    if isinstance(schema, list):
        return [_gemini_schema(item) for item in schema]
    return schema


def _generate_gemini_response(*, system_prompt, user_prompt, response_schema, files):
    api_key = os.environ['GEMINI_API_KEY']

    parts = [{'text': f'{system_prompt}\n\n{user_prompt}'}]
    for file_bytes, mime_type in (files or []):
        parts.append({
            'inline_data': {
                'mime_type': mime_type or 'application/octet-stream',
                'data': base64.b64encode(file_bytes).decode('ascii'),
            }
        })

    payload = {'contents': [{'parts': parts}]}
    if response_schema is not None:
        payload['generationConfig'] = {
            'response_mime_type': 'application/json',
            'response_schema': _gemini_schema(response_schema),
        }

    request = urllib.request.Request(
        f'{GEMINI_ENDPOINT}?key={api_key}',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    body = _request_json(request)
    try:
        return body['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError) as exc:
        raise InvalidAIResponse('AI provider returned an unexpected response shape.') from exc


# --- Groq -----------------------------------------------------------

def _generate_groq_response(*, system_prompt, user_prompt, response_schema, files):
    """Groq exposes an OpenAI-compatible Chat Completions endpoint (hence
    the request shape below). `files` is ignored entirely: unlike Gemini,
    vision support isn't consistently available across Groq's text
    models, so attaching images here would be unreliable rather than just
    incomplete."""
    api_key = os.environ['GROQ_API_KEY']

    payload = {
        'model': os.environ.get('GROQ_MODEL') or DEFAULT_GROQ_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_completion_tokens': 6000,
    }
    if response_schema is not None:
        payload['response_format'] = {
            'type': 'json_schema',
            'json_schema': {'name': 'response', 'schema': response_schema, 'strict': True},
        }

    request = urllib.request.Request(
        GROQ_ENDPOINT,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    body = _request_json(request)
    try:
        return body['choices'][0]['message']['content']
    except (KeyError, IndexError) as exc:
        raise InvalidAIResponse('AI provider returned an unexpected response shape.') from exc


# --- Legacy upload workflow (lang_quiz) --------------------------------

_MATERIAL_QUESTION_SCHEMA = [{
    'prompt': 'string',
    'reference_answer': 'string',
    'question_type': 'string',
    'skill_focus': 'string',
    'rubric_target_gap': 'string',
    'transfer_prompt': 'string',
}]


def generate_questions_from_text(raw_text, subject_name='Languages', count=10, section='reading'):
    """Compatibility entry point for the legacy upload workflow, now using
    the shared generate_ai_response() boundary (Gemini/Groq) instead of
    calling Groq directly."""
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
