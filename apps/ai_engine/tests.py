import os
import json
from unittest.mock import patch

from django.test import SimpleTestCase

from .client import generate_ai_response, generate_questions_from_text
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

    @patch.dict(os.environ, {}, clear=True)
    def test_legacy_material_generator_has_safe_openai_fallback(self):
        questions = generate_questions_from_text(
            'Students read the passage carefully because they needed evidence for every answer.',
            count=3,
            section='reading',
        )
        self.assertEqual(len(questions), 3)
        self.assertTrue(all(question['reference_answer'] for question in questions))

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'gpt-test'}, clear=True)
    @patch('apps.ai_engine.client.urlopen')
    def test_configured_openai_returns_structured_json(self, mock_urlopen):
        provider_body = {'output': [{'content': [
            {'type': 'output_text', 'text': '{"is_correct": true}'},
        ]}]}
        response = mock_urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(provider_body).encode('utf-8')

        result = generate_ai_response(
            system_prompt='Evaluate.',
            user_prompt='answer',
            response_schema={'is_correct': 'boolean'},
        )

        self.assertEqual(result, {'is_correct': True})
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.headers['Authorization'], 'Bearer test-key')
        payload = json.loads(request.data.decode('utf-8'))
        self.assertEqual(payload['model'], 'gpt-test')
        self.assertEqual(payload['text']['format']['type'], 'json_schema')
