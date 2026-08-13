import hmac
import json
import os
import subprocess
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = os.environ.get('RUNNER_HOST', '127.0.0.1')
PORT = int(os.environ.get('RUNNER_PORT', '8765'))
IMAGE = os.environ.get('RUNNER_IMAGE', 'ai-thinking-code-runner:local')
AUTH_TOKEN = os.environ.get('RUNNER_AUTH_TOKEN', '')
MAX_REQUEST_BYTES = 25_000
CONTAINER_TIMEOUT_SECONDS = int(os.environ.get('RUNNER_CONTAINER_TIMEOUT_SECONDS', '15'))
ALLOWED_TEST_IDS = {
    'lookup-public',
    'lookup-missing-key',
    'lookup-other-key',
    'price-public',
    'price-missing',
    'price-other',
    'double-public',
    'empty-list',
    'negative-values',
    'empty-words',
    'mixed-word-lengths',
    'square-public',
    'empty-square',
    'zero-square',
    'empty-negate',
    'mixed-negate',
    'increment-public',
    'empty-increment',
    'negative-increment',
    'empty-absolute',
    'mixed-absolute',
}


def _not_executed(message):
    return {'status': 'NOT_EXECUTED', 'message': message, 'tests': []}


def _docker_command(container_name):
    return [
        'docker', 'run', '--rm', '--name', container_name,
        '--network', 'none',
        '--memory', '128m',
        '--cpus', '1.0',
        '--pids-limit', '64',
        '--read-only',
        '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
        '--security-opt', 'no-new-privileges',
        '--cap-drop', 'ALL',
        '-i', IMAGE,
    ]


def _cleanup_container(container_name):
    try:
        subprocess.run(
            ['docker', 'rm', '-f', container_name],
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def run_in_sandbox(payload):
    if not isinstance(payload, dict):
        return _not_executed('The execution request must be a JSON object.')
    test_case_ids = payload.get('test_case_ids')
    if payload.get('language') != 'python':
        return _not_executed('The runner supports Python only.')
    if not isinstance(payload.get('source_code'), str):
        return _not_executed('Source code is required.')
    if not isinstance(test_case_ids, list) or not test_case_ids:
        return _not_executed('At least one curated test-case ID is required.')
    if any(test_id not in ALLOWED_TEST_IDS for test_id in test_case_ids):
        return _not_executed('The request contains an unknown test-case ID.')

    sanitized_payload = {
        'language': payload.get('language'),
        'source_code': payload.get('source_code'),
        'test_case_ids': test_case_ids,
    }
    container_name = f'ai-thinking-run-{uuid.uuid4().hex}'
    try:
        process = subprocess.run(
            _docker_command(container_name),
            input=json.dumps(sanitized_payload),
            capture_output=True,
            text=True,
            timeout=CONTAINER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _cleanup_container(container_name)
        return {
            'status': 'TIMEOUT',
            'message': (
                f'Execution exceeded the {CONTAINER_TIMEOUT_SECONDS}-second container limit.'
            ),
            'tests': [],
        }
    except FileNotFoundError:
        return _not_executed('Docker is not installed or is not available on PATH.')
    except subprocess.SubprocessError:
        return _not_executed('The isolated runner could not start the execution container.')

    if process.returncode != 0:
        return _not_executed('Docker could not run the isolated execution image.')
    try:
        result = json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return _not_executed('The execution container returned an invalid response.')
    if result.get('status') not in {
        'PASSED', 'OUTPUT_MISMATCH', 'LOGIC_ERROR', 'FAILED',
        'SYNTAX_ERROR', 'RUNTIME_ERROR', 'TIMEOUT', 'NOT_EXECUTED'
    }:
        return _not_executed('The execution container returned an unknown status.')
    return result


class RunnerRequestHandler(BaseHTTPRequestHandler):
    server_version = 'CodingRunner/1.0'

    def _send_json(self, status_code, payload):
        encoded = json.dumps(payload).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == '/health':
            self._send_json(200, {'status': 'ok'})
        else:
            self._send_json(404, {'error': 'not_found'})

    def do_POST(self):
        if self.path != '/execute':
            self._send_json(404, {'error': 'not_found'})
            return
        token = self.headers.get('X-Runner-Token') or ''
        if AUTH_TOKEN and not hmac.compare_digest(token, AUTH_TOKEN):
            self._send_json(403, {'error': 'forbidden'})
            return
        try:
            content_length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self._send_json(400, _not_executed('Invalid Content-Length.'))
            return
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json(413, _not_executed('The execution request is too large.'))
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, _not_executed('The runner received invalid JSON.'))
            return
        self._send_json(200, run_in_sandbox(payload))

    def log_message(self, format, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), RunnerRequestHandler)
    print(f'Coding runner listening on http://{HOST}:{PORT}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
