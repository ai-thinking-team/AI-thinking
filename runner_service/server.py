import hmac
import json
import logging
import os
import subprocess
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .harness import TEST_CATALOG


HOST = os.environ.get('RUNNER_HOST', '127.0.0.1')
PORT = int(os.environ.get('RUNNER_PORT', '8765'))
IMAGE = os.environ.get('RUNNER_IMAGE', 'ai-thinking-code-runner:local')
DOCKER_BIN = os.environ.get('DOCKER_BIN', 'docker')
AUTH_TOKEN = os.environ.get('RUNNER_AUTH_TOKEN', '')
MAX_REQUEST_BYTES = 25_000
CONTAINER_CREATE_TIMEOUT_SECONDS = int(
    os.environ.get('RUNNER_CONTAINER_CREATE_TIMEOUT_SECONDS', '30')
)
CONTAINER_START_TIMEOUT_SECONDS = int(
    os.environ.get('RUNNER_CONTAINER_START_TIMEOUT_SECONDS', '10')
)
CONTAINER_CLEANUP_TIMEOUT_SECONDS = int(
    os.environ.get('RUNNER_CONTAINER_CLEANUP_TIMEOUT_SECONDS', '5')
)
ALLOWED_TEST_IDS = frozenset(TEST_CATALOG)
LOGGER = logging.getLogger('coding_runner')

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.environ.get('RUNNER_LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )


def _not_executed(message):
    return {'status': 'NOT_EXECUTED', 'message': message, 'tests': []}


def _diagnostic_text(value, limit=240):
    detail = str(value or '').strip().replace('\r', ' ').replace('\n', ' ')
    return detail[:limit]


def _diagnostic_command(command):
    return ' '.join(str(part) for part in command)


def _docker_failure_message(process, phase):
    detail = _diagnostic_text(process.stderr)
    if detail:
        return f'Docker {phase} failed: {detail}'
    return f'Docker {phase} failed without diagnostics. Check Docker Desktop and the runner image.'


def _docker_create_command(container_name):
    return [
        DOCKER_BIN, 'create', '--rm', '--name', container_name,
        '--pull=never',
        '--network', 'none',
        '--memory', '128m',
        '--cpus', '1.0',
        '--pids-limit', '64',
        '--read-only',
        '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
        '--security-opt', 'no-new-privileges',
        '--cap-drop', 'ALL',
        '--init',
        '--interactive', IMAGE,
    ]


def _docker_start_command(container_name):
    return [DOCKER_BIN, 'start', '--attach', '--interactive', container_name]


def _cleanup_container(container_name):
    started = time.perf_counter()
    command = [DOCKER_BIN, 'rm', '--force', container_name]
    try:
        cleanup = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=CONTAINER_CLEANUP_TIMEOUT_SECONDS,
            check=False,
        )
        LOGGER.info(
            'runner_event=container_cleanup name=%s command=%s exit_code=%s elapsed_ms=%d stderr=%s',
            container_name,
            _diagnostic_command(command),
            cleanup.returncode,
            int((time.perf_counter() - started) * 1000),
            _diagnostic_text(cleanup.stderr),
        )
    except FileNotFoundError:
        LOGGER.error('runner_event=container_cleanup name=%s error=docker_not_found', container_name)
    except subprocess.TimeoutExpired:
        LOGGER.error(
            'runner_event=container_cleanup name=%s error=cleanup_timeout timeout_seconds=%s',
            container_name,
            CONTAINER_CLEANUP_TIMEOUT_SECONDS,
        )
    except subprocess.SubprocessError as exc:
        LOGGER.error(
            'runner_event=container_cleanup name=%s error=%s',
            container_name,
            _diagnostic_text(exc),
        )


def _parse_runner_result(stdout):
    try:
        result = json.loads(stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return None
    if result.get('status') not in {
        'PASSED', 'OUTPUT_MISMATCH', 'LOGIC_ERROR', 'FAILED',
        'SYNTAX_ERROR', 'RUNTIME_ERROR', 'TIMEOUT', 'NOT_EXECUTED',
    }:
        return None
    return result


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
    request_id = uuid.uuid4().hex
    container_name = f'ai-thinking-run-{request_id}'
    created = False
    started = time.perf_counter()
    LOGGER.info(
        'runner_event=request_received request_id=%s test_count=%d source_bytes=%d',
        request_id,
        len(test_case_ids),
        len(payload['source_code'].encode('utf-8')),
    )
    try:
        create_started = time.perf_counter()
        create_command = _docker_create_command(container_name)
        LOGGER.info(
            'runner_event=container_create_start request_id=%s name=%s command=%s timeout_seconds=%s',
            request_id,
            container_name,
            _diagnostic_command(create_command),
            CONTAINER_CREATE_TIMEOUT_SECONDS,
        )
        create_process = subprocess.run(
            create_command,
            capture_output=True,
            text=True,
            timeout=CONTAINER_CREATE_TIMEOUT_SECONDS,
            check=False,
        )
        LOGGER.info(
            'runner_event=container_create_finish request_id=%s exit_code=%s elapsed_ms=%d stdout=%s stderr=%s',
            request_id,
            create_process.returncode,
            int((time.perf_counter() - create_started) * 1000),
            _diagnostic_text(create_process.stdout),
            _diagnostic_text(create_process.stderr),
        )
        if create_process.returncode != 0:
            return {
                'status': 'RUNNER_ERROR',
                'message': _docker_failure_message(create_process, 'container creation'),
                'tests': [],
            }
        created = True

        start_started = time.perf_counter()
        start_command = _docker_start_command(container_name)
        LOGGER.info(
            'runner_event=execution_start request_id=%s name=%s command=%s timeout_seconds=%s',
            request_id,
            container_name,
            _diagnostic_command(start_command),
            CONTAINER_START_TIMEOUT_SECONDS,
        )
        start_process = subprocess.run(
            start_command,
            input=json.dumps(sanitized_payload),
            capture_output=True,
            text=True,
            timeout=CONTAINER_START_TIMEOUT_SECONDS,
            check=False,
        )
        LOGGER.info(
            'runner_event=execution_finish request_id=%s exit_code=%s elapsed_ms=%d stdout=%s stderr=%s',
            request_id,
            start_process.returncode,
            int((time.perf_counter() - start_started) * 1000),
            _diagnostic_text(start_process.stdout),
            _diagnostic_text(start_process.stderr),
        )
        result = _parse_runner_result(start_process.stdout)
        if result is not None and start_process.returncode == 0:
            return result
        if start_process.returncode != 0:
            return {
                'status': 'RUNNER_ERROR',
                'message': _docker_failure_message(start_process, 'execution'),
                'tests': [],
            }
        return {
            'status': 'RUNNER_ERROR',
            'message': 'The isolated runner returned no valid execution result.',
            'tests': [],
        }
    except subprocess.TimeoutExpired as exc:
        phase = 'container creation' if not created else 'execution transport'
        LOGGER.error(
            'runner_event=timeout request_id=%s phase=%s timeout_seconds=%s stdout=%s stderr=%s',
            request_id,
            phase,
            exc.timeout,
            _diagnostic_text(exc.stdout),
            _diagnostic_text(exc.stderr),
        )
        return {
            'status': 'RUNNER_ERROR',
            'message': (
                f'The runner {phase} exceeded its {exc.timeout}-second infrastructure limit '
                'before a student execution result was received.'
            ),
            'tests': [],
        }
    except FileNotFoundError:
        LOGGER.error('runner_event=process_error request_id=%s error=docker_not_found', request_id)
        return {
            'status': 'RUNNER_ERROR',
            'message': 'Docker is not installed or is not available on PATH.',
            'tests': [],
        }
    except subprocess.SubprocessError as exc:
        LOGGER.error('runner_event=process_error request_id=%s error=%s', request_id, _diagnostic_text(exc))
        return {
            'status': 'RUNNER_ERROR',
            'message': 'The isolated runner could not start or complete the execution container.',
            'tests': [],
        }
    finally:
        LOGGER.info(
            'runner_event=request_finish request_id=%s elapsed_ms=%d container_created=%s',
            request_id,
            int((time.perf_counter() - started) * 1000),
            created,
        )
        if created:
            _cleanup_container(container_name)


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
