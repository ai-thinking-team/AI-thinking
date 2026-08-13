from dataclasses import dataclass
from enum import Enum
from typing import Protocol

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


def get_code_execution_gateway():
    gateway_path = getattr(settings, 'CODE_RUNNER_GATEWAY_CLASS', '')
    if gateway_path:
        return import_string(gateway_path)()
    base_url = getattr(settings, 'CODE_RUNNER_URL', '')
    if base_url:
        from .http_gateway import HttpCodeExecutionGateway

        return HttpCodeExecutionGateway(
            base_url=base_url,
            auth_token=getattr(settings, 'CODE_RUNNER_AUTH_TOKEN', ''),
            timeout=getattr(settings, 'CODE_RUNNER_TIMEOUT_SECONDS', 20),
        )
    return UnavailableCodeExecutionGateway()
