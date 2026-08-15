import contextlib
import io
import json
import sys


def main():
    safe_dumps = json.dumps
    try:
        payload = json.loads(sys.stdin.read())
        compiled = compile(payload['source_code'], 'learner_submission.py', 'exec')
        namespace = {'__name__': 'learner_submission'}
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
        safe_message = str(exc).replace('\n', ' ')[:160]
        encoded = safe_dumps({
            'kind': 'runtime_error',
            'error_type': type(exc).__name__,
            'message': safe_message,
        }, separators=(',', ':'))
    sys.stdout.write(encoded + '\n')


if __name__ == '__main__':
    main()
