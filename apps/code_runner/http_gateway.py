import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .runner import ExecutionResult, ExecutionStatus
from .validators import validate_execution_request


MAX_RESPONSE_BYTES = 64_000


class HttpCodeExecutionGateway:
    def __init__(self, *, base_url, auth_token='', timeout=20):
        self.execute_url = f'{base_url.rstrip("/")}/execute'
        self.auth_token = auth_token
        self.timeout = timeout

    def run(self, request):
        validate_execution_request(language=request.language, source_code=request.source_code)
        payload = json.dumps({
            'language': request.language,
            'source_code': request.source_code,
            'test_case_ids': list(request.test_case_ids),
        }).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if self.auth_token:
            headers['X-Runner-Token'] = self.auth_token
        http_request = Request(self.execute_url, data=payload, headers=headers, method='POST')
        try:
            with urlopen(http_request, timeout=self.timeout) as response:
                raw_response = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError):
            return self._unavailable()
        if len(raw_response) > MAX_RESPONSE_BYTES:
            return self._unavailable('The isolated runner returned an oversized response.')
        try:
            data = json.loads(raw_response)
            status = ExecutionStatus(data['status'])
            message = str(data['message'])[:500]
            tests = tuple(item for item in data.get('tests', ()) if isinstance(item, dict))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return self._unavailable('The isolated runner returned an invalid response.')
        return ExecutionResult(status=status, message=message, tests=tests)

    @staticmethod
    def _unavailable(message='The isolated execution service is unavailable; the submission was not run.'):
        return ExecutionResult(status=ExecutionStatus.NOT_EXECUTED, message=message)
