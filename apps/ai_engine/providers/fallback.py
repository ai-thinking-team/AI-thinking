import os

from ..exceptions import AIEngineError, AIServiceUnavailable


def _default_providers():
    """The real provider chain, built from whichever API keys are set —
    same priority AI_PROVIDER_CLASS used when only one provider could be
    picked: DeepSeek, then Gemini, then Groq."""
    from .deepseek import DeepSeekProvider
    from .gemini import GeminiProvider
    from .groq import GroqProvider

    candidates = (
        ('DEEPSEEK_API_KEY', DeepSeekProvider),
        ('GEMINI_API_KEY', GeminiProvider),
        ('GROQ_API_KEY', GroqProvider),
    )
    return [provider_cls() for env_var, provider_cls in candidates if os.environ.get(env_var)]


class FallbackProvider:
    """Tries each configured provider in turn, falling through to the
    next on any AIEngineError — a provider being *configured* (a key is
    present) doesn't mean it's currently *working* (out of quota,
    rate-limited, a deprecated model name, network trouble, ...), so a
    failure there shouldn't take AI assistance down entirely when another
    provider is available. Anything else (a bug, not a provider failure)
    still propagates immediately. Mirrors the provider fallback loop
    already used on the mathquiz branch (apps/ai_engine/client.py there).

    `providers`, when given, overrides the real key-driven chain — used
    by tests to inject canned providers without touching os.environ.
    """

    def __init__(self, providers=None):
        self._providers = providers if providers is not None else _default_providers()

    def generate(self, *, system_prompt, user_prompt, response_schema=None):
        if not self._providers:
            raise AIServiceUnavailable('No external AI provider is configured.')
        last_error = None
        for provider in self._providers:
            try:
                return provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=response_schema,
                )
            except AIEngineError as exc:
                last_error = exc
        raise last_error
