import re
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


def ai_provider_status(*, assistance_enabled=True):
    """Return a local, non-network status for the learner-facing AI Coach."""
    if not ai_provider_configured():
        return {
            'mode': 'CURATED_FALLBACK',
            'label': 'Curated fallback ready',
            'detail': 'No external API is required. Curated questions, hints, and rubrics remain available.',
            'configured': False,
            'assistance_enabled': assistance_enabled,
        }
    if not assistance_enabled:
        return {
            'mode': 'CONFIGURED_LOCKED',
            'label': 'Live AI configured; currently locked',
            'detail': 'The workflow unlocks AI Coach assistance only after the Think-First gate.',
            'configured': True,
            'assistance_enabled': False,
        }
    return {
        'mode': 'LIVE_PROVIDER',
        'label': 'Live AI provider available',
        'detail': 'Provider failures automatically fall back to curated responses.',
        'configured': True,
        'assistance_enabled': True,
    }


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


def generate_questions_from_text(raw_text, subject_name='Languages', count=10, section='reading'):
    """Create upload-grounded questions locally without exporting document text."""
    material = (raw_text or '').strip()[:12000]
    if not material:
        return []
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
