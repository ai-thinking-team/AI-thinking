from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Protocol
from urllib.parse import urlparse

from django.conf import settings
from django.utils.module_loading import import_string

from .validators import validate_execution_request


class ExecutionStatus(str, Enum):
    PASSED = 'PASSED'
    OUTPUT_MISMATCH = 'OUTPUT_MISMATCH'
    LOGIC_ERROR = 'LOGIC_ERROR'
    # Kept for compatibility with an older runner deployment.
    FAILED = 'FAILED'
    SYNTAX_ERROR = 'SYNTAX_ERROR'
    RUNTIME_ERROR = 'RUNTIME_ERROR'
    TIMEOUT = 'TIMEOUT'
    NOT_EXECUTED = 'NOT_EXECUTED'


@dataclass(frozen=True)
class ExecutionRequest:
    language: str
    source_code: str
    test_case_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    message: str
    tests: tuple[dict, ...] = ()


class CodeExecutionGateway(Protocol):
    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Send hostile learner code to a separately isolated service."""


class UnavailableCodeExecutionGateway:
    """Safe local placeholder that never runs learner code."""

    def run(self, request):
        validate_execution_request(language=request.language, source_code=request.source_code)
        return ExecutionResult(
            status=ExecutionStatus.NOT_EXECUTED,
            message='No isolated execution service is configured; the submission was not run.',
        )


_local_runner_process = None


def _local_runner_url(base_url):
    parsed = urlparse(base_url)
    return parsed.hostname in {'127.0.0.1', 'localhost', '::1'}, parsed.port or 8765


def _runner_port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.15):
            return True
    except OSError:
        return False


def ensure_local_runner_started(base_url):
    """Start the local runner on demand without enabling this behavior in production."""
    global _local_runner_process
    if getattr(settings, 'IS_PRODUCTION', False) or not getattr(settings, 'CODE_RUNNER_AUTOSTART', False):
        return False
    is_local, port = _local_runner_url(base_url)
    if not is_local:
        return False
    if _runner_port_open('127.0.0.1', port):
        return True
    if _local_runner_process is not None and _local_runner_process.poll() is None:
        return False

    repo_root = Path(__file__).resolve().parents[2]
    start_script = repo_root / 'runner_service' / 'start.ps1'
    if os.name == 'nt' and start_script.exists():
        command = [
            'powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(start_script),
        ]
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    else:
        command = [sys.executable, '-m', 'runner_service.server']
        startupinfo = None
        creationflags = 0
    try:
        _local_runner_process = subprocess.Popen(
            command,
            cwd=str(repo_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except OSError:
        _local_runner_process = None
        return False

    deadline = time.monotonic() + getattr(settings, 'CODE_RUNNER_AUTOSTART_TIMEOUT_SECONDS', 20)
    while time.monotonic() < deadline:
        if _runner_port_open('127.0.0.1', port):
            return True
        if _local_runner_process.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def get_code_execution_gateway():
    gateway_path = getattr(settings, 'CODE_RUNNER_GATEWAY_CLASS', '')
    if gateway_path:
        return import_string(gateway_path)()
    base_url = getattr(settings, 'CODE_RUNNER_URL', '')
    if base_url:
        ensure_local_runner_started(base_url)
        from .http_gateway import HttpCodeExecutionGateway

        return HttpCodeExecutionGateway(
            base_url=base_url,
            auth_token=getattr(settings, 'CODE_RUNNER_AUTH_TOKEN', ''),
            timeout=getattr(settings, 'CODE_RUNNER_TIMEOUT_SECONDS', 20),
        )
    return UnavailableCodeExecutionGateway()


def code_runner_status():
    """Return a safe learner-facing readiness summary without exposing secrets."""
    gateway_path = getattr(settings, 'CODE_RUNNER_GATEWAY_CLASS', '')
    if gateway_path:
        return {
            'mode': 'CUSTOM_GATEWAY',
            'label': 'Configured',
            'detail': 'A configured isolated execution gateway is available for submissions.',
        }

    base_url = getattr(settings, 'CODE_RUNNER_URL', '').strip()
    if not base_url:
        return {
            'mode': 'UNCONFIGURED',
            'label': 'Not configured',
            'detail': 'Code is stored but cannot be executed until an isolated runner URL is configured.',
        }

    is_local, port = _local_runner_url(base_url)
    if is_local and not _runner_port_open('127.0.0.1', port):
        return {
            'mode': 'UNAVAILABLE',
            'label': 'Configured, unavailable',
            'detail': 'The isolated runner URL is configured, but the local runner is not reachable yet.',
        }
    return {
        'mode': 'CONFIGURED',
        'label': 'Configured',
        'detail': 'Submissions are sent to the isolated runner for verification.',
    }
