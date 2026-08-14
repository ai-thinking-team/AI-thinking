import json
import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from . import client
from .client import generate_ai_response
from .exceptions import AIServiceUnavailable
from .schemas import DiagnosticResponse


def _fake_urlopen_response(body):
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(body).encode('utf-8')
    mock_response.__enter__.return_value = mock_response
    return mock_response


class AIClientTests(SimpleTestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_fails_safely(self):
        with self.assertRaises(AIServiceUnavailable):
            generate_ai_response(system_prompt='system', user_prompt='learner')

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'gm-test', 'GROQ_API_KEY': 'gsk-test'}, clear=True)
    @patch.object(client, '_generate_groq_response', return_value='groq answered')
    @patch.object(client, '_generate_gemini_response', side_effect=AIServiceUnavailable('quota exhausted'))
    def test_falls_through_to_the_next_provider_when_the_first_is_configured_but_broken(
        self, mock_gemini, mock_groq,
    ):
        """A provider being configured (a key is present) doesn't mean
        it's currently working — e.g. a Gemini key with no quota left.
        That should transparently fall through to the next configured
        provider rather than making the whole app AI-silent."""
        result = generate_ai_response(system_prompt='system', user_prompt='learner')
        self.assertEqual(result, 'groq answered')
        mock_gemini.assert_called_once()
        mock_groq.assert_called_once()

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'gm-test', 'GROQ_API_KEY': 'gsk-test'}, clear=True)
    @patch.object(client, '_generate_groq_response', side_effect=AIServiceUnavailable('also broken'))
    @patch.object(client, '_generate_gemini_response', side_effect=AIServiceUnavailable('quota exhausted'))
    def test_raises_when_every_configured_provider_fails(self, mock_gemini, mock_groq):
        with self.assertRaises(AIServiceUnavailable):
            generate_ai_response(system_prompt='system', user_prompt='learner')

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'gm-test'}, clear=True)
    @patch('urllib.request.urlopen', side_effect=TimeoutError('The read operation timed out'))
    def test_a_bare_read_timeout_is_reported_as_ai_unavailable_not_a_crash(self, mock_urlopen):
        """A read timeout past the deadline raises a bare TimeoutError from
        urllib — not wrapped in URLError — so it needs its own handler or
        it escapes _request_json as an unhandled exception and crashes the
        calling view with a 500 instead of falling back gracefully."""
        with self.assertRaises(AIServiceUnavailable):
            generate_ai_response(system_prompt='system', user_prompt='learner')

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'gm-test'}, clear=True)
    @patch('urllib.request.urlopen')
    def test_gemini_attaches_one_inline_part_per_file(self, mock_urlopen):
        mock_urlopen.return_value = _fake_urlopen_response(
            {'candidates': [{'content': {'parts': [{'text': '{}'}]}}]}
        )
        generate_ai_response(
            system_prompt='system', user_prompt='learner',
            files=[(b'pdf-bytes', 'application/pdf'), (b'img-bytes', 'image/png')],
        )
        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data)
        parts = payload['contents'][0]['parts']
        # 1 text part + 2 file parts, one inline_data entry per attachment.
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[1]['inline_data']['mime_type'], 'application/pdf')
        self.assertEqual(parts[2]['inline_data']['mime_type'], 'image/png')

    @patch.dict(os.environ, {'GROQ_API_KEY': 'gsk-test'}, clear=True)
    @patch('urllib.request.urlopen')
    def test_groq_request_uses_the_openai_compatible_shape(self, mock_urlopen):
        mock_urlopen.return_value = _fake_urlopen_response(
            {'choices': [{'message': {'content': '{}'}}]}
        )
        generate_ai_response(system_prompt='system', user_prompt='learner')
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, client.GROQ_ENDPOINT)
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], client.DEFAULT_GROQ_MODEL)
        self.assertEqual(
            payload['messages'],
            [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'learner'}],
        )

    @patch.dict(os.environ, {'GROQ_API_KEY': 'gsk-test', 'GROQ_MODEL': 'openai/gpt-oss-120b'}, clear=True)
    @patch('urllib.request.urlopen')
    def test_groq_model_can_be_overridden_by_env_var(self, mock_urlopen):
        mock_urlopen.return_value = _fake_urlopen_response(
            {'choices': [{'message': {'content': '{}'}}]}
        )
        generate_ai_response(system_prompt='system', user_prompt='learner')
        payload = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(payload['model'], 'openai/gpt-oss-120b')

    @patch.dict(os.environ, {'GROQ_API_KEY': 'gsk-test'}, clear=True)
    @patch('urllib.request.urlopen')
    def test_groq_ignores_files_since_vision_support_is_not_reliable(self, mock_urlopen):
        mock_urlopen.return_value = _fake_urlopen_response(
            {'choices': [{'message': {'content': '{}'}}]}
        )
        generate_ai_response(
            system_prompt='system', user_prompt='learner',
            files=[(b'img-bytes', 'image/png')],
        )
        payload = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(payload['messages'][1]['content'], 'learner')

    @patch.dict(
        os.environ,
        {'GEMINI_API_KEY': 'gm-test', 'GROQ_API_KEY': 'gsk-test'},
        clear=True,
    )
    def test_default_provider_order_is_gemini_then_groq(self):
        self.assertEqual(client._provider_order(), ('gemini', 'groq'))

    @patch.dict(
        os.environ,
        {'GEMINI_API_KEY': 'gm-test', 'GROQ_API_KEY': 'gsk-test', 'AI_PROVIDER': 'groq'},
        clear=True,
    )
    def test_ai_provider_env_var_moves_the_chosen_provider_first_without_dropping_fallback(self):
        self.assertEqual(client._provider_order(), ('groq', 'gemini'))

    @patch.dict(
        os.environ,
        {'GEMINI_API_KEY': 'gm-test', 'GROQ_API_KEY': 'gsk-test'},
        clear=True,
    )
    @patch.object(client, '_generate_groq_response', return_value='groq answered')
    @patch.object(client, '_generate_gemini_response', side_effect=AIServiceUnavailable('quota exhausted'))
    def test_ai_provider_preference_is_actually_tried_first(self, mock_gemini, mock_groq):
        with patch.dict(os.environ, {'AI_PROVIDER': 'groq'}):
            result = generate_ai_response(system_prompt='system', user_prompt='learner')
        self.assertEqual(result, 'groq answered')
        mock_groq.assert_called_once()
        mock_gemini.assert_not_called()

    @patch.dict(
        os.environ,
        {'GEMINI_API_KEY': 'gm-test', 'GROQ_API_KEY': 'gsk-test', 'AI_PROVIDER': 'groq'},
        clear=True,
    )
    @patch.object(client, '_generate_groq_response', return_value='groq answered')
    @patch.object(client, '_generate_gemini_response', return_value='gemini answered')
    def test_files_route_to_gemini_first_even_when_groq_is_preferred(self, mock_gemini, mock_groq):
        """Groq can't read attached files at all (see
        test_groq_ignores_files_since_vision_support_is_not_reliable), so
        trying it first when files are given would silently generate
        content while ignoring every attachment — files must override
        AI_PROVIDER's preference, not just the default order."""
        result = generate_ai_response(
            system_prompt='system', user_prompt='learner', files=[(b'pdf-bytes', 'application/pdf')],
        )
        self.assertEqual(result, 'gemini answered')
        mock_gemini.assert_called_once()
        mock_groq.assert_not_called()

    def test_ai_response_schema_has_no_mastery_control(self):
        response = DiagnosticResponse(
            possible_misconception='loop_variable',
            diagnostic_confidence=0.7,
            response_type='guiding_question',
            message='What value does the loop variable hold?',
            hint_level=1,
        )

        self.assertFalse(hasattr(response, 'mastery'))
