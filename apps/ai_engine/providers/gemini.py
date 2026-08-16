import json
import os
from copy import deepcopy

from django.conf import settings

from ..exceptions import AIServiceUnavailable, InvalidAIResponse


def _gemini_compatible_schema(schema):
    compatible = deepcopy(schema or {})

    def simplify(value):
        if isinstance(value, dict):
            value.pop('additionalProperties', None)
            value.pop('const', None)
            for nested in value.values():
                simplify(nested)
        elif isinstance(value, list):
            for nested in value:
                simplify(nested)

    simplify(compatible)
    return compatible


class GeminiProvider:
    def __init__(self, *, api_key=None, model=None, timeout=None, client=None):
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY', '')
        self.model = model or getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')
        self.timeout = timeout or getattr(settings, 'GEMINI_TIMEOUT_SECONDS', 20)
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise AIServiceUnavailable('Gemini is not configured.')
        try:
            from google import genai
        except ImportError as exc:
            raise AIServiceUnavailable('The Google Gen AI SDK is not installed.') from exc
        self._client = genai.Client(
            api_key=self.api_key,
            http_options={'timeout': self.timeout * 1000},
        )
        return self._client

    def generate(self, *, system_prompt, user_prompt, response_schema=None):
        client = self._get_client()
        response = client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config={
                'system_instruction': system_prompt,
                'response_mime_type': 'application/json',
                'response_json_schema': _gemini_compatible_schema(response_schema),
                # Teach-Back evaluates five fields; 512 tokens can truncate otherwise-valid JSON.
                'max_output_tokens': 2048,
                'temperature': 0,
            },
        )
        if isinstance(getattr(response, 'parsed', None), dict):
            return response.parsed
        response_text = getattr(response, 'text', '')
        if not response_text:
            raise InvalidAIResponse('Gemini returned no structured response.')
        try:
            return json.loads(response_text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise InvalidAIResponse('Gemini returned invalid JSON.') from exc
