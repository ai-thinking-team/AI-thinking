import base64
import json
import os
import urllib.error
import urllib.request

from .exceptions import AIEngineError, AIServiceUnavailable, InvalidAIResponse

GEMINI_MODEL = 'gemini-flash-latest'
GEMINI_ENDPOINT = (
    f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
)

DEFAULT_GROQ_MODEL = 'llama-3.3-70b-versatile'
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
    """
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

    last_error = None
    for generate in attempts:
        try:
            return generate(
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_schema=response_schema, files=files,
            )
        except AIEngineError as exc:
            last_error = exc
    raise last_error


REQUEST_TIMEOUT_SECONDS = 45

# urllib's default User-Agent ("Python-urllib/3.x") is bot-flagged by
# Cloudflare (fronting Groq's API, and possibly others) and gets a bare
# 403 before the request ever reaches the provider's own API layer — a
# generic browser-like one gets through. Set centrally here rather than
# per-provider since every request goes through this one function.
_USER_AGENT = 'Mozilla/5.0'


def _request_json(request):
    request.add_header('User-Agent', _USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
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
