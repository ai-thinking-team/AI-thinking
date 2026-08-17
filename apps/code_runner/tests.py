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
    code_runner_status,
    get_code_execution_gateway,
)


class CodeRunnerBoundaryTests(SimpleTestCase):
    @override_settings(CODE_RUNNER_URL='', CODE_RUNNER_GATEWAY_CLASS='')
    def test_status_distinguishes_unconfigured_runner(self):
        status = code_runner_status()
        self.assertEqual(status['mode'], 'UNCONFIGURED')
        self.assertEqual(status['label'], 'Not configured')

    @override_settings(CODE_RUNNER_URL='http://127.0.0.1:8765', CODE_RUNNER_GATEWAY_CLASS='')
    @patch('apps.code_runner.runner._runner_port_open', return_value=False)
    def test_status_distinguishes_configured_but_unavailable_local_runner(self, mocked_port):
        status = code_runner_status()
        self.assertEqual(status['mode'], 'UNAVAILABLE')
        self.assertEqual(status['label'], 'Configured, unavailable')
        mocked_port.assert_called_once_with('127.0.0.1', 8765)

    @override_settings(CODE_RUNNER_URL='https://runner.example.test/execute', CODE_RUNNER_GATEWAY_CLASS='')
    def test_status_does_not_probe_remote_runner_or_expose_credentials(self):
        status = code_runner_status()
        self.assertEqual(status['mode'], 'CONFIGURED')
        self.assertNotIn('token', status['detail'].lower())

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

    @patch('apps.code_runner.http_gateway.urlopen')
    def test_classified_failure_statuses_are_mapped_without_becoming_unavailable(
        self,
        mocked_urlopen,
    ):
        for status in ('OUTPUT_MISMATCH', 'LOGIC_ERROR', 'RUNNER_ERROR'):
            with self.subTest(status=status):
                response = MagicMock()
                response.read.return_value = json.dumps({
                    'status': status,
                    'message': 'Classified learner result.',
                    'tests': [{'id': 'double-public', 'passed': False}],
                }).encode()
                mocked_urlopen.return_value.__enter__.return_value = response

                result = self.gateway.run(self.request)

                self.assertEqual(result.status, ExecutionStatus(status))

    @patch('apps.code_runner.http_gateway.urlopen')
    def test_unknown_runner_status_still_fails_closed(self, mocked_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            'status': 'MASTERED',
            'message': 'Unauthorized workflow result.',
        }).encode()
        mocked_urlopen.return_value.__enter__.return_value = response

        result = self.gateway.run(self.request)

        self.assertEqual(result.status, ExecutionStatus.RUNNER_ERROR)

    @patch('apps.code_runner.http_gateway.urlopen', side_effect=URLError('offline'))
    def test_unavailable_runner_is_runner_error(self, mocked_urlopen):
        result = self.gateway.run(self.request)

        self.assertEqual(result.status, ExecutionStatus.RUNNER_ERROR)
        self.assertIn('could not be reached', result.message)

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

    @override_settings(
        CODE_RUNNER_URL='http://127.0.0.1:8765',
        CODE_RUNNER_AUTOSTART=True,
        IS_PRODUCTION=False,
    )
    @patch('apps.code_runner.runner._runner_port_open', return_value=True)
    @patch('apps.code_runner.runner.subprocess.Popen')
    def test_factory_does_not_spawn_when_local_runner_is_already_ready(self, mocked_popen, mocked_port):
        get_code_execution_gateway()
        mocked_popen.assert_not_called()
        mocked_port.assert_called()

    @override_settings(
        CODE_RUNNER_URL='http://127.0.0.1:8765',
        CODE_RUNNER_AUTOSTART=True,
        IS_PRODUCTION=False,
        CODE_RUNNER_AUTOSTART_TIMEOUT_SECONDS=0,
    )
    @patch('apps.code_runner.runner._runner_port_open', return_value=False)
    @patch('apps.code_runner.runner.subprocess.Popen')
    def test_factory_can_start_local_runner_on_demand(self, mocked_popen, mocked_port):
        mocked_popen.return_value.poll.return_value = None
        get_code_execution_gateway()
        mocked_popen.assert_called_once()

    @override_settings(
        CODE_RUNNER_URL='http://127.0.0.1:8765',
        CODE_RUNNER_AUTOSTART=True,
        IS_PRODUCTION=True,
    )
    @patch('apps.code_runner.runner.subprocess.Popen')
    def test_production_never_spawns_local_runner(self, mocked_popen):
        get_code_execution_gateway()
        mocked_popen.assert_not_called()
