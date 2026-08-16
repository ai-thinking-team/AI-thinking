from .exceptions import InvalidCodeSubmission, UnsupportedLanguage

MAX_SOURCE_LENGTH = 20_000


def validate_execution_request(*, language, source_code):
    if language != 'python':
        raise UnsupportedLanguage('The first Coding MVP supports Python only.')
    if not isinstance(source_code, str) or not source_code.strip():
        raise InvalidCodeSubmission('Source code is required.')
    if len(source_code) > MAX_SOURCE_LENGTH:
        raise InvalidCodeSubmission('Source code exceeds the demo size limit.')
