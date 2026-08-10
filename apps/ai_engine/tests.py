import os
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
