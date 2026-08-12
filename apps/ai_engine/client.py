from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

from .exceptions import AIEngineError, AIServiceUnavailable


class AIProvider(Protocol):
    def generate(self, *, system_prompt, user_prompt, response_schema=None):
        """Return provider output without controlling application workflow."""


class UnavailableAIProvider:
    def generate(self, *, system_prompt, user_prompt, response_schema=None):
        raise AIServiceUnavailable('No external AI provider is configured.')


def get_ai_provider():
    provider_path = getattr(settings, 'AI_PROVIDER_CLASS', '')
    if not provider_path:
        return UnavailableAIProvider()
    return import_string(provider_path)()


def ai_provider_configured():
    return bool(getattr(settings, 'AI_PROVIDER_CLASS', ''))


def generate_ai_response(*, system_prompt, user_prompt, response_schema=None, provider=None):
    """Call a replaceable provider and normalize failures at one boundary."""
    selected_provider = provider or get_ai_provider()
    try:
        return selected_provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=response_schema,
        )
    except AIEngineError:
        raise
    except Exception as exc:
        raise AIServiceUnavailable('The configured AI provider failed.') from exc
