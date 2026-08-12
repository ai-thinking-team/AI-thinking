import contextlib
import io
import json
import sys

# Defense-in-depth builtins restrictor for beginner Python exercises.
# NOTE: This is NOT a complete standalone Python sandbox.
# Docker container isolation remains the primary security boundary.
_raw_builtins = __builtins__.__dict__ if isinstance(__builtins__, type(sys)) else __builtins__
SAFE_BUILTINS = {
    '__build_class__': _raw_builtins.get('__build_class__'),
    '__name__': '__main__',
    '__doc__': None,
    'abs': abs,
    'all': all,
    'any': any,
    'bool': bool,
    'callable': callable,
    'chr': chr,
    'dict': dict,
    'enumerate': enumerate,
    'float': float,
    'format': format,
    'getattr': getattr,
    'hasattr': hasattr,
    'int': int,
    'isinstance': isinstance,
    'issubclass': issubclass,
    'iter': iter,
    'len': len,
    'list': list,
    'max': max,
    'min': min,
    'next': next,
    'ord': ord,
    'print': print,
    'range': range,
    'repr': repr,
    'reversed': reversed,
    'round': round,
    'set': set,
    'slice': slice,
    'sorted': sorted,
    'str': str,
    'sum': sum,
    'tuple': tuple,
    'type': type,
    'zip': zip,
    'ArithmeticError': ArithmeticError,
    'AssertionError': AssertionError,
    'AttributeError': AttributeError,
    'BaseException': BaseException,
    'Exception': Exception,
    'IndexError': IndexError,
    'KeyError': KeyError,
    'LookupError': LookupError,
    'NameError': NameError,
    'OverflowError': OverflowError,
    'RuntimeError': RuntimeError,
    'StopIteration': StopIteration,
    'TypeError': TypeError,
    'ValueError': ValueError,
    'ZeroDivisionError': ZeroDivisionError,
}


def _sanitize_message(message):
    clean = str(message).replace('\n', ' ')
    for path in ('/runner/worker.py', '/runner/harness.py', 'learner_submission.py'):
        clean = clean.replace(path, '<submission>')
    return clean[:160]


def main():
    safe_dumps = json.dumps
    try:
        payload = json.loads(sys.stdin.read())
        compiled = compile(payload['source_code'], 'learner_submission.py', 'exec')
        namespace = {'__name__': 'learner_submission', '__builtins__': SAFE_BUILTINS}
        captured_output = io.StringIO()
        with contextlib.redirect_stdout(captured_output), contextlib.redirect_stderr(captured_output):
            exec(compiled, namespace, namespace)
            learner_function = namespace.get(payload['function'])
            if not callable(learner_function):
                result = {'kind': 'missing_function'}
            else:
                value = learner_function(*payload['args'])
                result = {'kind': 'ok', 'value': value}
        encoded = safe_dumps(result, separators=(',', ':'))
    except BaseException as exc:
        safe_message = _sanitize_message(exc)
        encoded = safe_dumps({
            'kind': 'runtime_error',
            'error_type': type(exc).__name__,
            'message': safe_message,
        }, separators=(',', ':'))
    sys.stdout.write(encoded + '\n')


if __name__ == '__main__':
    main()
