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
                'def safe_divide(a, b):\n    return 0 if b == 0 else a / b',
                ['divide-public', 'divide-by-zero', 'divide-negative'],
            ),
            (
                'def first_item(items):\n    return items[0] if items else None',
                ['first-item-public', 'first-item-empty', 'first-item-single'],
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

    def test_added_topic_family_cases_pass(self):
        cases = (
            ('def classify_number(n):\n    return "positive" if n > 0 else "zero" if n == 0 else "negative"', ['classify-number-public', 'classify-number-zero', 'classify-number-negative']),
            ('def rectangle_area(width, height):\n    return width * height', ['rectangle-area-public', 'rectangle-area-zero', 'rectangle-area-other']),
            ('def sum_numbers(numbers):\n    return sum(numbers)', ['sum-list-public', 'sum-list-empty', 'sum-list-negative']),
            ('def matrix_total(matrix):\n    return sum(sum(row) for row in matrix)', ['matrix-total-public', 'matrix-total-empty', 'matrix-total-uneven']),
            ('def reverse_text(text):\n    return text[::-1]', ['reverse-string-public', 'reverse-string-empty', 'reverse-string-unicode']),
            ('def triple_numbers(numbers):\n    return [number * 3 for number in numbers]', ['triple-numbers-public', 'triple-numbers-empty', 'triple-numbers-negative']),
            ('def factorial(n):\n    return 1 if n == 0 else n * factorial(n - 1)', ['factorial-public', 'factorial-zero', 'factorial-one']),
        )
        for source_code, test_case_ids in cases:
            with self.subTest(test_case_ids=test_case_ids):
                result = execute({
                    'language': 'python',
                    'source_code': source_code,
                    'test_case_ids': test_case_ids,
                })
                self.assertEqual(result['status'], 'PASSED')

    def test_dsa_topic_family_cases_pass(self):
        cases = (
            (
                'def binary_search(numbers, target):\n    left, right = 0, len(numbers) - 1\n    while left <= right:\n        middle = (left + right) // 2\n        if numbers[middle] == target:\n            return middle\n        if numbers[middle] < target:\n            left = middle + 1\n        else:\n            right = middle - 1\n    return -1',
                ['binary-search-public', 'binary-search-missing', 'binary-search-single'],
            ),
            (
                'def valid_brackets(text):\n    pairs = {\")\": \"(\", \"]\": \"[\", \"}\": \"{\"}\n    stack = []\n    for char in text:\n        if char in \"([{\":\n            stack.append(char)\n        elif char in pairs:\n            if not stack or stack.pop() != pairs[char]:\n                return False\n    return not stack',
                ['valid-brackets-public', 'valid-brackets-unclosed', 'valid-brackets-wrong-order'],
            ),
            ('def rotate_queue(items):\n    return items[1:] + items[:1] if items else []', ['rotate-queue-public', 'rotate-queue-empty', 'rotate-queue-single']),
            ('def selection_sort(numbers):\n    result = []\n    remaining = numbers[:]\n    while remaining:\n        smallest = min(remaining)\n        remaining.remove(smallest)\n        result.append(smallest)\n    return result', ['selection-sort-public', 'selection-sort-empty', 'selection-sort-duplicates']),
            ('def two_sum_indexes(numbers, target):\n    seen = {}\n    for index, number in enumerate(numbers):\n        complement = target - number\n        if complement in seen:\n            return [seen[complement], index]\n        seen[number] = index\n    return [-1, -1]', ['two-sum-public', 'two-sum-duplicate', 'two-sum-missing']),
            ('def has_path(graph, start, target):\n    stack = [start]\n    visited = set()\n    while stack:\n        node = stack.pop()\n        if node == target:\n            return True\n        if node in visited:\n            continue\n        visited.add(node)\n        stack.extend(graph.get(node, []))\n    return False', ['graph-path-public', 'graph-path-missing', 'graph-path-cycle']),
            ('def climb_stairs(n):\n    previous, current = 1, 1\n    for _ in range(n):\n        previous, current = current, previous + current\n    return previous', ['climb-stairs-public', 'climb-stairs-zero', 'climb-stairs-other']),
        )
        for source_code, test_case_ids in cases:
            with self.subTest(test_case_ids=test_case_ids):
                result = execute({
                    'language': 'python',
                    'source_code': source_code,
                    'test_case_ids': test_case_ids,
                })
                self.assertEqual(result['status'], 'PASSED')

    def test_second_exercise_for_each_single_exercise_topic_passes(self):
        cases = (
            (
                'def is_leap_year(year):\n    return year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)',
                ['leap-year-public', 'leap-year-century', 'leap-year-four-hundred'],
            ),
            ('def is_palindrome(text):\n    return text == text[::-1]', ['palindrome-public', 'palindrome-false', 'palindrome-empty']),
            ('def power_of_two(n):\n    return 1 if n == 0 else 2 * power_of_two(n - 1)', ['power-two-public', 'power-two-zero', 'power-two-one']),
            (
                'def first_binary_search(numbers, target):\n    left, right, answer = 0, len(numbers) - 1, -1\n    while left <= right:\n        middle = (left + right) // 2\n        if numbers[middle] >= target:\n            if numbers[middle] == target:\n                answer = middle\n            right = middle - 1\n        else:\n            left = middle + 1\n    return answer',
                ['first-binary-public', 'first-binary-missing', 'first-binary-later'],
            ),
            (
                'def insertion_sort(numbers):\n    result = []\n    for number in numbers:\n        index = 0\n        while index < len(result) and result[index] <= number:\n            index += 1\n        result.insert(index, number)\n    return result',
                ['insertion-sort-public', 'insertion-sort-empty', 'insertion-sort-duplicates'],
            ),
            (
                'def character_frequencies(text):\n    counts = {}\n    for char in text:\n        counts[char] = counts.get(char, 0) + 1\n    return counts',
                ['char-frequency-public', 'char-frequency-empty', 'char-frequency-other'],
            ),
            (
                'def shortest_path_length(graph, start, target):\n    queue = [(start, 0)]\n    visited = {start}\n    while queue:\n        node, distance = queue.pop(0)\n        if node == target:\n            return distance\n        for neighbor in graph.get(node, []):\n            if neighbor not in visited:\n                visited.add(neighbor)\n                queue.append((neighbor, distance + 1))\n    return -1',
                ['shortest-path-public', 'shortest-path-missing', 'shortest-path-cycle'],
            ),
            (
                'def min_cost_climbing_stairs(cost):\n    previous, current = 0, 0\n    for stair_cost in cost:\n        previous, current = current, min(previous, current) + stair_cost\n    return min(previous, current)',
                ['min-cost-public', 'min-cost-empty', 'min-cost-other'],
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

    def test_set_membership_and_for_loop_pass(self):
        result = execute({
            'language': 'python',
            'source_code': (
                'def count_allowed(numbers, allowed_values):\n'
                '    allowed_set = set(allowed_values)\n'
                '    count = 0\n'
                '    for number in numbers:\n'
                '        if number in allowed_set:\n'
                '            count += 1\n'
                '    return count\n'
            ),
            'test_case_ids': ['set-membership-public', 'set-membership-none', 'set-membership-other'],
        })
        self.assertEqual(result['status'], 'PASSED')

    def test_large_reasonable_input_passes(self):
        result = execute({
            'language': 'python',
            'source_code': (
                'def count_allowed(numbers, allowed_values):\n'
                '    allowed_set = set(allowed_values)\n'
                '    count = 0\n'
                '    for number in numbers:\n'
                '        if number in allowed_set:\n'
                '            count += 1\n'
                '    return count\n'
            ),
            'test_case_ids': ['set-membership-large'],
        })
        self.assertEqual(result['status'], 'PASSED')

    def test_terminating_while_loop_passes(self):
        result = execute({
            'language': 'python',
            'source_code': (
                'def safe_divide(a, b):\n'
                '    quotient = 0\n'
                '    remaining = a\n'
                '    while remaining >= b:\n'
                '        remaining -= b\n'
                '        quotient += 1\n'
                '    return quotient\n'
            ),
            'test_case_ids': ['divide-public'],
        })
        self.assertEqual(result['status'], 'PASSED')

    def test_repeated_sequential_submissions_remain_stable(self):
        source_code = 'def count_allowed(numbers, allowed_values):\n    return sum(number in set(allowed_values) for number in numbers)'
        for _ in range(5):
            with self.subTest(attempt=_):
                result = execute({
                    'language': 'python',
                    'source_code': source_code,
                    'test_case_ids': ['set-membership-public'],
                })
                self.assertEqual(result['status'], 'PASSED')


class RunnerServiceTests(TestCase):
    @patch('runner_service.server.subprocess.run')
    def test_docker_command_has_required_isolation_limits(self, mocked_run):
        mocked_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout='container-id\n', stderr=''),
            subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout='{"status":"PASSED","message":"ok","tests":[]}', stderr='',
            ),
            subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr=''),
        ]
        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'def double_numbers(values): return []',
            'test_case_ids': ['double-public'],
        })

        command = mocked_run.call_args_list[0].args[0]
        self.assertEqual(result['status'], 'PASSED')
        self.assertEqual(command[1], 'create')
        self.assertIn('--pull=never', command)
        self.assertIn('--network', command)
        self.assertIn('none', command)
        self.assertIn('--memory', command)
        self.assertIn('128m', command)
        self.assertIn('--cpus', command)
        self.assertIn('--cap-drop', command)
        self.assertIn('ALL', command)
        self.assertIn('--init', command)
        self.assertNotIn('SETUID', command)
        self.assertNotIn('SETGID', command)
        self.assertEqual(mocked_run.call_args_list[1].args[0][1:3], ['start', '--attach'])

    @patch('runner_service.server.subprocess.run', side_effect=FileNotFoundError)
    def test_missing_docker_returns_runner_error(self, mocked_run):
        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'print(1)',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'RUNNER_ERROR')

    @patch('runner_service.server.subprocess.run')
    def test_execution_transport_timeout_is_runner_error_and_force_removed(self, mocked_run):
        mocked_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout='container-id\n', stderr=''),
            subprocess.TimeoutExpired('docker', server.CONTAINER_START_TIMEOUT_SECONDS),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]

        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'while True: pass',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'RUNNER_ERROR')
        self.assertIn(
            'infrastructure limit',
            result['message'],
        )
        cleanup_command = mocked_run.call_args_list[2].args[0]
        self.assertEqual(cleanup_command[:3], ['docker', 'rm', '--force'])

    @patch('runner_service.server.subprocess.run')
    def test_container_creation_timeout_is_runner_error_without_student_timeout(self, mocked_run):
        mocked_run.side_effect = subprocess.TimeoutExpired(
            'docker', server.CONTAINER_CREATE_TIMEOUT_SECONDS
        )

        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'def double_numbers(values): return values',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'RUNNER_ERROR')
        self.assertIn('container creation', result['message'])
        mocked_run.assert_called_once()

    @patch('runner_service.server.subprocess.run')
    def test_student_timeout_result_is_preserved(self, mocked_run):
        mocked_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout='container-id\n', stderr=''),
            subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout='{"status":"TIMEOUT","message":"Execution exceeded the 2-second limit.","tests":[]}',
                stderr='',
            ),
            subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr=''),
        ]

        result = run_in_sandbox({
            'language': 'python',
            'source_code': 'def double_numbers(values):\n    while True: pass',
            'test_case_ids': ['double-public'],
        })

        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertIn('2-second', result['message'])

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

        self.assertEqual(result['status'], 'RUNNER_ERROR')
        self.assertIn('Docker Desktop is not running', result['message'])

    @patch('runner_service.server.subprocess.run')
    def test_extra_payload_keys_are_sanitized(self, mocked_run):
        mocked_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout='container-id\n', stderr=''),
            subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout='{"status":"PASSED","message":"ok","tests":[]}', stderr='',
            ),
            subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr=''),
        ]
        run_in_sandbox({
            'language': 'python',
            'source_code': 'def double_numbers(values): return []',
            'test_case_ids': ['double-public'],
            'malicious_key': 'should_be_stripped',
            'secret_token': '12345',
        })
        input_data = mocked_run.call_args_list[1].kwargs['input']
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
