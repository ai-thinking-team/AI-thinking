import subprocess
from unittest import TestCase
from unittest.mock import patch

from .harness import execute
from .server import run_in_sandbox


class HarnessTests(TestCase):
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

    def test_failed_hidden_test_does_not_reveal_expected_value(self):
        result = execute({
            'language': 'python',
            'source_code': 'def double_numbers(numbers):\n    return numbers',
            'test_case_ids': ['negative-values'],
        })

        self.assertEqual(result['status'], 'FAILED')
        self.assertNotIn('expected', result['tests'][0])
        self.assertNotIn('actual', result['tests'][0])

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
        self.assertIn('--read-only', command)
        self.assertIn('--cap-drop', command)
        self.assertIn('--cap-add', command)
        self.assertIn('SETUID', command)
        self.assertIn('SETGID', command)

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
            subprocess.TimeoutExpired('docker', 3),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]

        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'while True: pass',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'TIMEOUT')
        cleanup_command = mocked_run.call_args_list[1].args[0]
        self.assertEqual(cleanup_command[:3], ['docker', 'rm', '-f'])
