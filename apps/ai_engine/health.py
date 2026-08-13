import time

from .client import ai_provider_configured, generate_ai_response
from .exceptions import AIEngineError


HEALTH_SCHEMA = {
    'type': 'object',
    'properties': {'status': {'type': 'string', 'enum': ['ok']}},
    'required': ['status'],
    'additionalProperties': False,
}


def probe_ai_provider(*, provider=None):
    """Perform an explicit, data-free provider probe and return safe diagnostics."""
    if provider is None and not ai_provider_configured():
        return {
            'available': False,
            'code': 'NOT_CONFIGURED',
            'message': 'No external AI provider is configured; curated fallback is ready.',
            'latency_ms': None,
        }

    started = time.monotonic()
    try:
        response = generate_ai_response(
            system_prompt='Return only the requested structured object.',
            user_prompt='Return status ok. This health check contains no learner data.',
            response_schema=HEALTH_SCHEMA,
            provider=provider,
        )
    except AIEngineError as exc:
        return {
            'available': False,
            'code': type(exc).__name__,
            'message': 'The configured AI provider could not complete a structured health check.',
            'latency_ms': round((time.monotonic() - started) * 1000),
        }

    valid = response == {'status': 'ok'}
    return {
        'available': valid,
        'code': 'OK' if valid else 'INVALID_HEALTH_RESPONSE',
        'message': (
            'The configured AI provider returned a valid structured response.'
            if valid else
            'The configured AI provider returned an unexpected health response.'
        ),
        'latency_ms': round((time.monotonic() - started) * 1000),
    }
