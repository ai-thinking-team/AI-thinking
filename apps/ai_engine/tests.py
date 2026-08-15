import os
import json
from io import BytesIO
from urllib.error import HTTPError
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
    def test_legacy_material_generator_has_safe_groq_fallback(self):
        questions = generate_questions_from_text(
            'Students read the passage carefully because they needed evidence for every answer.',
            count=3,
            section='reading',
        )
        self.assertEqual(len(questions), 3)
        self.assertTrue(all(question['reference_answer'] for question in questions))

    @patch.dict(os.environ, {'GROQ_API_KEY': 'test-key', 'GROQ_MODEL': 'groq-test'}, clear=True)
    @patch('apps.ai_engine.client.urllib.request.urlopen')
    def test_configured_groq_returns_structured_json(self, mock_urlopen):
        provider_body = {
            'choices': [{'message': {'content': '{"is_correct": true}'}}],
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
        self.assertEqual(request.full_url, 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(request.headers['Authorization'], 'Bearer test-key')
        # A generic browser-like User-Agent avoids Cloudflare (fronting
        # Groq's API) bot-flagging urllib's default identifier.
        self.assertEqual(request.headers['User-agent'], 'Mozilla/5.0')
        payload = json.loads(request.data.decode('utf-8'))
        self.assertEqual(payload['model'], 'groq-test')
        self.assertEqual(payload['messages'][0], {'role': 'system', 'content': 'Evaluate.'})
        self.assertEqual(payload['messages'][1], {'role': 'user', 'content': 'answer'})
        self.assertEqual(payload['response_format']['type'], 'json_schema')

    @patch.dict(os.environ, {'GROQ_API_KEY': 'test-key', 'GROQ_MODEL': ''}, clear=True)
    @patch('apps.ai_engine.client.urllib.request.urlopen')
    def test_empty_model_uses_default(self, mock_urlopen):
        response = mock_urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps({
            'choices': [{'message': {'content': 'ready'}}],
        }).encode('utf-8')

        self.assertEqual(
            generate_ai_response(system_prompt='Teach.', user_prompt='Create a quiz.'),
            'ready',
        )
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode('utf-8'))
        self.assertEqual(payload['model'], 'openai/gpt-oss-20b')

    @patch.dict(os.environ, {'GROQ_API_KEY': 'test-key'}, clear=True)
    @patch('apps.ai_engine.client.urllib.request.urlopen')
    def test_groq_http_error_includes_safe_provider_message(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url='https://api.groq.com/openai/v1/chat/completions',
            code=403,
            msg='Forbidden',
            hdrs=None,
            fp=BytesIO(json.dumps({
                'error': {'message': 'Key gsk_should_not_leak is not permitted.'},
            }).encode('utf-8')),
        )

        with self.assertRaisesRegex(
            AIServiceUnavailable,
            r'error \(403\).*Key \[redacted\] is not permitted',
        ):
            generate_ai_response(system_prompt='Teach.', user_prompt='Create a quiz.')
