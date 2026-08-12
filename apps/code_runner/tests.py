import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.test import SimpleTestCase, override_settings

from .exceptions import UnsupportedLanguage
from .http_gateway import HttpCodeExecutionGateway
from .runner import (
    ExecutionRequest,
    ExecutionStatus,
    UnavailableCodeExecutionGateway,
    get_code_execution_gateway,
)


class CodeRunnerBoundaryTests(SimpleTestCase):
    def test_local_placeholder_never_claims_code_was_run(self):
        result = UnavailableCodeExecutionGateway().run(
            ExecutionRequest(language='python', source_code='print(1)')
        )

        self.assertEqual(result.status, ExecutionStatus.NOT_EXECUTED)

    def test_only_python_is_accepted(self):
        with self.assertRaises(UnsupportedLanguage):
            UnavailableCodeExecutionGateway().run(
                ExecutionRequest(language='javascript', source_code='console.log(1)')
            )


class HttpCodeExecutionGatewayTests(SimpleTestCase):
    def setUp(self):
        self.gateway = HttpCodeExecutionGateway(base_url='http://127.0.0.1:8765')
        self.request = ExecutionRequest(
            language='python',
            source_code='def double_numbers(values):\n    return [value * 2 for value in values]',
            test_case_ids=('double-public', 'empty-list'),
        )

    @patch('apps.code_runner.http_gateway.urlopen')
    def test_valid_runner_response_is_mapped_to_execution_result(self, mocked_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            'status': 'PASSED',
            'message': 'All tests passed.',
            'tests': [{'id': 'double-public', 'passed': True}],
        }).encode()
        mocked_urlopen.return_value.__enter__.return_value = response

        result = self.gateway.run(self.request)

        self.assertEqual(result.status, ExecutionStatus.PASSED)
        self.assertEqual(result.tests[0]['id'], 'double-public')
        sent_request = mocked_urlopen.call_args.args[0]
        sent_payload = json.loads(sent_request.data)
        self.assertEqual(sent_payload['test_case_ids'], ['double-public', 'empty-list'])

    @patch('apps.code_runner.http_gateway.urlopen', side_effect=URLError('offline'))
    def test_unavailable_runner_fails_closed(self, mocked_urlopen):
        result = self.gateway.run(self.request)

        self.assertEqual(result.status, ExecutionStatus.NOT_EXECUTED)

    @override_settings(
        CODE_RUNNER_URL='http://127.0.0.1:8765',
        CODE_RUNNER_AUTH_TOKEN='runner-token',
        CODE_RUNNER_TIMEOUT_SECONDS=17,
        CODE_RUNNER_GATEWAY_CLASS='',
    )
    def test_factory_uses_http_gateway_when_url_is_configured(self):
        gateway = get_code_execution_gateway()

        self.assertIsInstance(gateway, HttpCodeExecutionGateway)
        self.assertEqual(gateway.auth_token, 'runner-token')
        self.assertEqual(gateway.timeout, 17)
