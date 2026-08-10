import os

from .exceptions import AIServiceUnavailable


def generate_ai_response(*, system_prompt, user_prompt, response_schema=None):
    """Return validated AI output behind one provider-neutral boundary.

    Provider integration is intentionally deferred. Importing this module never
    performs a network call, and missing configuration fails safely.
    """
    if not os.environ.get('GEMINI_API_KEY'):
        raise AIServiceUnavailable(
            'AI support is unavailable. Continue with the curated diagnostic and hint ladder.'
        )
    raise AIServiceUnavailable('The external AI provider adapter is not implemented in this scaffold.')
