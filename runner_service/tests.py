import subprocess
from unittest import TestCase
from unittest.mock import patch

from .harness import execute
from . import server
from .server import run_in_sandbox


class HarnessTests(TestCase):
    def test_dictionary_lookup_cases(self):
        result = execute({
            'language': 'python',
            'source_code': 'def lookup_grade(grades, student_name):\n    return grades.get(student_name, 0)',
            'test_case_ids': ['lookup-public', 'lookup-missing-key', 'lookup-other-key'],
        })
        self.assertEqual(result['status'], 'PASSED')

    def test_dictionary_transfer_cases(self):
        result = execute({
            'language': 'python',
            'source_code': 'def lookup_price(prices, product):\n    return prices.get(product, -1)',
            'test_case_ids': ['price-public', 'price-missing', 'price-other'],
        })
        self.assertEqual(result['status'], 'PASSED')

    def test_curated_public_and_hidden_tests_pass(self):
        result = execute({
            'language': 'python',
            'source_code': (
                'def double_numbers(numbers):\n'
                '    return [number * 2 for number in numbers]\n'
            ),
            'test_case_ids': ['double-public', 'empty-list', 'negative-values'],
        })

        self.assertEqual(result['status'], 'PASSED')
        self.assertEqual(len(result['tests']), 3)

    def test_catalog_exercises_and_transfer_tests_are_curated_in_runner(self):
        cases = (
            (
                'def square_numbers(numbers):\n    return [number ** 2 for number in numbers]',
                ['square-public', 'empty-square', 'zero-square'],
            ),
            (
                'def increment_numbers(numbers):\n    return [number + 1 for number in numbers]',
                ['increment-public', 'empty-increment', 'negative-increment'],
            ),
            (
                'def negate_numbers(numbers):\n    return [-number for number in numbers]',
                ['empty-negate', 'mixed-negate'],
            ),
            (
                'def absolute_numbers(numbers):\n    return [abs(number) for number in numbers]',
                ['empty-absolute', 'mixed-absolute'],
            ),
        )
        for source_code, test_case_ids in cases:
            with self.subTest(test_case_ids=test_case_ids):
                result = execute({
                    'language': 'python',
                    'source_code': source_code,
                    'test_case_ids': test_case_ids,
                })
                self.assertEqual(result['status'], 'PASSED')

    def test_failed_hidden_test_does_not_reveal_expected_value(self):
        result = execute({
            'language': 'python',
            'source_code': 'def double_numbers(numbers):\n    return numbers',
            'test_case_ids': ['negative-values'],
        })

        self.assertEqual(result['status'], 'LOGIC_ERROR')
        self.assertNotIn('expected', result['tests'][0])
        self.assertNotIn('actual', result['tests'][0])

    def test_failed_public_test_is_classified_as_output_mismatch_with_public_evidence(self):
        result = execute({
            'language': 'python',
            'source_code': 'def double_numbers(numbers):\n    return numbers',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'OUTPUT_MISMATCH')
        self.assertEqual(result['tests'][0]['expected'], [2, 6])
        self.assertEqual(result['tests'][0]['actual'], [1, 3])

    def test_missing_required_function_is_classified_as_logic_error(self):
        result = execute({
            'language': 'python',
            'source_code': 'def another_function(numbers):\n    return numbers',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'LOGIC_ERROR')
        self.assertEqual(result['tests'], [])

    def test_syntax_and_runtime_errors_are_classified(self):
        syntax_result = execute({
            'language': 'python',
            'source_code': 'def double_numbers(:',
            'test_case_ids': ['double-public'],
        })
        runtime_result = execute({
            'language': 'python',
            'source_code': 'def double_numbers(numbers):\n    return 1 / 0',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(syntax_result['status'], 'SYNTAX_ERROR')
        self.assertEqual(runtime_result['status'], 'RUNTIME_ERROR')

    def test_unknown_test_id_is_rejected(self):
        result = execute({
            'language': 'python',
            'source_code': 'print(1)',
            'test_case_ids': ['not-curated'],
        })

        self.assertEqual(result['status'], 'NOT_EXECUTED')

    @patch('runner_service.harness.subprocess.run', side_effect=subprocess.TimeoutExpired('python', 2))
    def test_learner_timeout_is_classified(self, mocked_run):
        result = execute({
            'language': 'python',
            'source_code': 'while True: pass',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'TIMEOUT')


class RunnerServiceTests(TestCase):
    @patch('runner_service.server.subprocess.run')
    def test_docker_command_has_required_isolation_limits(self, mocked_run):
        mocked_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"status":"PASSED","message":"ok","tests":[]}', stderr='',
        )
        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'def double_numbers(values): return []',
            'test_case_ids': ['double-public'],
        })

        command = mocked_run.call_args.args[0]
        self.assertEqual(result['status'], 'PASSED')
        self.assertIn('--network', command)
        self.assertIn('none', command)
        self.assertIn('--memory', command)
        self.assertIn('128m', command)
        self.assertIn('--cpus', command)
        self.assertIn('--cap-drop', command)
        self.assertIn('ALL', command)
        self.assertNotIn('SETUID', command)
        self.assertNotIn('SETGID', command)

    @patch('runner_service.server.subprocess.run', side_effect=FileNotFoundError)
    def test_missing_docker_returns_not_executed(self, mocked_run):
        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'print(1)',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'NOT_EXECUTED')

    @patch('runner_service.server.subprocess.run')
    def test_timed_out_container_is_force_removed(self, mocked_run):
        mocked_run.side_effect = [
            subprocess.TimeoutExpired('docker', server.CONTAINER_TIMEOUT_SECONDS),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]

        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'while True: pass',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertIn(
            f'{server.CONTAINER_TIMEOUT_SECONDS}-second container limit',
            result['message'],
        )
        cleanup_command = mocked_run.call_args_list[1].args[0]
        self.assertEqual(cleanup_command[:3], ['docker', 'rm', '-f'])

    @patch('runner_service.server.subprocess.run')
    def test_docker_failure_includes_runner_diagnostic(self, mocked_run):
        mocked_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout='', stderr='error during connect: Docker Desktop is not running\n',
        )

        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'def double_numbers(values): return values',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'NOT_EXECUTED')
        self.assertIn('Docker Desktop is not running', result['message'])

    @patch('runner_service.server.subprocess.run')
    def test_extra_payload_keys_are_sanitized(self, mocked_run):
        mocked_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"status":"PASSED","message":"ok","tests":[]}', stderr='',
        )
        run_in_sandbox({
            'language': 'python',
            'source_code': 'def double_numbers(values): return []',
            'test_case_ids': ['double-public'],
            'malicious_key': 'should_be_stripped',
            'secret_token': '12345',
        })
        input_data = mocked_run.call_args.kwargs['input']
        self.assertNotIn('malicious_key', input_data)
        self.assertNotIn('secret_token', input_data)

    def test_non_object_payload_is_rejected_without_starting_docker(self):
        for payload in (None, [], 'text'):
            with self.subTest(payload_type=type(payload).__name__):
                with patch('runner_service.server.subprocess.run') as mocked_run:
                    result = run_in_sandbox(payload)
                self.assertEqual(result['status'], 'NOT_EXECUTED')
                self.assertIn('JSON object', result['message'])
                mocked_run.assert_not_called()


class DefenseInDepthSecurityTests(TestCase):
    def test_dangerous_builtins_and_imports_fail_safely(self):
        dangerous_codes = (
            'import os',
            'import sys',
            'import subprocess',
            'open("/etc/passwd", "r")',
            'eval("1 + 1")',
            'exec("x = 1")',
            'compile("x = 1", "", "exec")',
        )
        for code in dangerous_codes:
            with self.subTest(code=code):
                result = execute({
                    'language': 'python',
                    'source_code': f'def double_numbers(numbers):\n    {code}\n    return numbers',
                    'test_case_ids': ['double-public'],
                })
                self.assertEqual(result['status'], 'RUNTIME_ERROR')

    def test_class_definitions_and_comprehensions_and_standard_builtins_work(self):
        source = (
            'class Transformer:\n'
            '    def double(self, vals):\n'
            '        print("Processing", len(vals))\n'
            '        res = []\n'
            '        for v in vals:\n'
            '            res.append(v * 2)\n'
            '        return [x for x in res]\n'
            'def double_numbers(numbers):\n'
            '    t = Transformer()\n'
            '    return t.double(numbers)\n'
        )
        result = execute({
            'language': 'python',
            'source_code': source,
            'test_case_ids': ['double-public'],
        })
        self.assertEqual(result['status'], 'PASSED')

    def test_runtime_error_sanitizes_internal_container_paths(self):
        result = execute({
            'language': 'python',
            'source_code': 'def double_numbers(numbers):\n    raise RuntimeError("Custom error from /runner/worker.py")',
            'test_case_ids': ['double-public'],
        })
        self.assertEqual(result['status'], 'RUNTIME_ERROR')
        self.assertNotIn('/runner/worker.py', result['message'])
        self.assertIn('<submission>', result['message'])

    def test_token_authentication_handling(self):
        from runner_service.server import RunnerRequestHandler
        from io import BytesIO

        body = b'{"language":"python","source_code":"x=1","test_case_ids":["double-public"]}'
        handler = RunnerRequestHandler.__new__(RunnerRequestHandler)

        with patch('runner_service.server.AUTH_TOKEN', 'correct-token'), \
             patch.object(RunnerRequestHandler, '_send_json') as mock_send, \
             patch('runner_service.server.run_in_sandbox', return_value={'status': 'PASSED'}):
            handler.path = '/execute'
            handler.headers = {'X-Runner-Token': 'correct-token', 'Content-Length': str(len(body))}
            handler.rfile = BytesIO(body)
            handler.do_POST()
            mock_send.assert_called_with(200, {'status': 'PASSED'})

        with patch('runner_service.server.AUTH_TOKEN', 'correct-token'), \
             patch.object(RunnerRequestHandler, '_send_json') as mock_send:
            handler.path = '/execute'
            handler.headers = {'X-Runner-Token': 'wrong-token', 'Content-Length': str(len(body))}
            handler.rfile = BytesIO(body)
            handler.do_POST()
            mock_send.assert_called_with(403, {'error': 'forbidden'})

        with patch('runner_service.server.AUTH_TOKEN', 'correct-token'), \
             patch.object(RunnerRequestHandler, '_send_json') as mock_send:
            handler.path = '/execute'
            handler.headers = {'Content-Length': str(len(body))}  # missing token header
            handler.rfile = BytesIO(body)
            handler.do_POST()
            mock_send.assert_called_with(403, {'error': 'forbidden'})
