import os
import json
from unittest.mock import patch

from django.test import SimpleTestCase

from .client import generate_ai_response
from .exceptions import AIServiceUnavailable
from .schemas import DiagnosticResponse


class AIClientTests(SimpleTestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_fails_safely(self):
        with self.assertRaises(AIServiceUnavailable):
            generate_ai_response(system_prompt='system', user_prompt='learner')

    def test_ai_response_schema_has_no_mastery_control(self):
        response = DiagnosticResponse(
            possible_misconception='loop_variable',
            diagnostic_confidence=0.7,
            response_type='guiding_question',
            message='What value does the loop variable hold?',
            hint_level=1,
        )

        self.assertFalse(hasattr(response, 'mastery'))

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}, clear=True)
    @patch('apps.ai_engine.client.urlopen')
    def test_configured_gemini_returns_structured_json(self, mock_urlopen):
        provider_body = {
            'candidates': [{'content': {'parts': [{'text': '{"is_correct": true}'}]}}]
        }
        response = mock_urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(provider_body).encode('utf-8')

        result = generate_ai_response(
            system_prompt='Evaluate.',
            user_prompt='answer',
            response_schema={'is_correct': 'boolean'},
        )

        self.assertEqual(result, {'is_correct': True})
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.headers['X-goog-api-key'], 'test-key')
