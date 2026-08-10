from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .validators import validate_execution_request


class ExecutionStatus(str, Enum):
    PASSED = 'PASSED'
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
