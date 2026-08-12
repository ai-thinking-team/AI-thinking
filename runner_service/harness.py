import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


TEST_CATALOG = {
    'double-public': {
        'function': 'double_numbers',
        'args': ([1, 3],),
        'expected': [2, 6],
        'public': True,
    },
    'empty-list': {
        'function': 'double_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'negative-values': {
        'function': 'double_numbers',
        'args': ([-2, 0, 5],),
        'expected': [-4, 0, 10],
        'public': False,
    },
    'empty-words': {
        'function': 'word_lengths',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'mixed-word-lengths': {
        'function': 'word_lengths',
        'args': (['a', 'loop', 'python'],),
        'expected': [1, 4, 6],
        'public': False,
    },
    'square-public': {
        'function': 'square_numbers',
        'args': ([2, -3],),
        'expected': [4, 9],
        'public': True,
    },
    'empty-square': {
        'function': 'square_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'zero-square': {
        'function': 'square_numbers',
        'args': ([0, 4],),
        'expected': [0, 16],
        'public': False,
    },
    'empty-negate': {
        'function': 'negate_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'mixed-negate': {
        'function': 'negate_numbers',
        'args': ([-2, 0, 5],),
        'expected': [2, 0, -5],
        'public': False,
    },
    'increment-public': {
        'function': 'increment_numbers',
        'args': ([1, 3],),
        'expected': [2, 4],
        'public': True,
    },
    'empty-increment': {
        'function': 'increment_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'negative-increment': {
        'function': 'increment_numbers',
        'args': ([-2, 0],),
        'expected': [-1, 1],
        'public': False,
    },
    'empty-absolute': {
        'function': 'absolute_numbers',
        'args': ([],),
        'expected': [],
        'public': False,
    },
    'mixed-absolute': {
        'function': 'absolute_numbers',
        'args': ([-3, 0, 4],),
        'expected': [3, 0, 4],
        'public': False,
    },
}

EXECUTION_SECONDS = 2


class ExecutionTimedOut(Exception):
    pass


def _timeout_handler(signum, frame):
    raise ExecutionTimedOut


def _start_timeout():
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(EXECUTION_SECONDS)


def _cancel_timeout():
    if hasattr(signal, 'SIGALRM'):
        signal.alarm(0)


def _result(status, message, tests=()):
    return {'status': status, 'message': message, 'tests': list(tests)}


def _run_learner(source_code, test):
    worker_payload = json.dumps({
        'source_code': source_code,
        'function': test['function'],
        'args': test['args'],
    })
    worker_path = str(Path(__file__).with_name('worker.py'))
    process_options = {
        'input': worker_payload,
        'capture_output': True,
        'text': True,
        'timeout': EXECUTION_SECONDS,
        'check': False,
        'env': {'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'},
        'cwd': tempfile.gettempdir(),
    }
    if os.name == 'posix' and hasattr(os, 'geteuid') and os.geteuid() == 0:
        process_options.update(user=10001, group=10001)
    try:
        process = subprocess.run(
            [sys.executable, worker_path],
            **process_options,
        )
    except subprocess.TimeoutExpired:
        raise ExecutionTimedOut
    if process.returncode != 0:
        return {'kind': 'runtime_error', 'error_type': 'ProcessExit', 'message': 'Learner process exited unexpectedly.'}
    try:
        return json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {'kind': 'runtime_error', 'error_type': 'InvalidOutput', 'message': 'Learner process returned invalid output.'}


def execute(payload):
    source_code = payload.get('source_code')
    test_case_ids = payload.get('test_case_ids')
    if payload.get('language') != 'python':
        return _result('NOT_EXECUTED', 'The runner supports Python only.')
    if not isinstance(source_code, str) or not source_code.strip():
        return _result('NOT_EXECUTED', 'Source code is required.')
    if not isinstance(test_case_ids, list) or not test_case_ids:
        return _result('NOT_EXECUTED', 'At least one curated test-case ID is required.')
    if any(test_id not in TEST_CATALOG for test_id in test_case_ids):
        return _result('NOT_EXECUTED', 'The request contains an unknown test-case ID.')

    try:
        compiled = compile(source_code, 'learner_submission.py', 'exec')
    except SyntaxError as exc:
        clean_msg = str(exc.msg).replace('\n', ' ')[:160]
        return _result(
            'SYNTAX_ERROR',
            f'Syntax error on line {exc.lineno}: {clean_msg}',
        )

    _start_timeout()
    try:
        test_results = []
        for test_id in test_case_ids:
            test = TEST_CATALOG[test_id]
            worker_result = _run_learner(source_code, test)
            if worker_result.get('kind') == 'missing_function':
                return _result('FAILED', f"Required function `{test['function']}` was not defined.")
            if worker_result.get('kind') != 'ok':
                return _result(
                    'RUNTIME_ERROR',
                    f"{worker_result.get('error_type', 'RuntimeError')}: "
                    f"{worker_result.get('message', 'Learner code failed.')}",
                )
            actual = worker_result.get('value')
            passed = actual == test['expected']
            evidence = {'id': test_id, 'passed': passed}
            if test['public'] and not passed:
                evidence['expected'] = test['expected']
                evidence['actual'] = actual
            test_results.append(evidence)
            if not passed:
                message = (
                    'A public test returned an unexpected result.'
                    if test['public']
                    else 'A hidden boundary test failed.'
                )
                return _result('FAILED', message, test_results)
    except ExecutionTimedOut:
        return _result('TIMEOUT', 'Execution exceeded the 2-second limit.')
    finally:
        _cancel_timeout()

    return _result('PASSED', 'All requested public and hidden tests passed.', test_results)


def main():
    safe_dumps = json.dumps
    try:
        payload = json.loads(sys.stdin.read())
        result = execute(payload)
    except (json.JSONDecodeError, TypeError):
        result = _result('NOT_EXECUTED', 'The runner received an invalid request.')
    sys.stdout.write(safe_dumps(result, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
