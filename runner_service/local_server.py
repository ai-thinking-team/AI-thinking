"""Lightweight local code-execution server — LOCAL TESTING ONLY.

Runs learner code directly (subprocess + timeout only, no container
sandboxing). Single-threaded — handles one request at a time, which is fine
for one person testing locally. Do not use this for anything but running
your own test code on your own machine. For anything closer to production,
use a Docker-based runner with real sandboxing (network=none, read-only
rootfs, dropped capabilities, resource limits) instead.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from harness import execute

HOST = os.environ.get('RUNNER_HOST', '127.0.0.1')
PORT = int(os.environ.get('RUNNER_PORT', '8765'))
AUTH_TOKEN = os.environ.get('RUNNER_AUTH_TOKEN', '')
MAX_REQUEST_BYTES = 25_000


def _not_executed(message):
    return {'status': 'NOT_EXECUTED', 'message': message, 'tests': []}


class RunnerRequestHandler(BaseHTTPRequestHandler):
    server_version = 'LocalCodingRunner/1.0'

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
        if AUTH_TOKEN and self.headers.get('X-Runner-Token') != AUTH_TOKEN:
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
        self._send_json(200, execute(payload))

    def log_message(self, format, *args):
        return


def main():
    # Single-threaded on purpose: harness.py's per-request timeout uses
    # SIGALRM, which only works in the process's main thread.
    server = HTTPServer((HOST, PORT), RunnerRequestHandler)
    print(f'Local coding runner (no sandbox) listening on http://{HOST}:{PORT}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
