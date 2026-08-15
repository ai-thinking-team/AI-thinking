from .runner import ExecutionRequest


def build_python_request(*, source_code, test_case_ids=()):
    return ExecutionRequest(
        language='python',
        source_code=source_code,
        test_case_ids=tuple(test_case_ids),
    )
