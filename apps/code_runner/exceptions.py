class CodeRunnerError(RuntimeError):
    """Base error for the isolated code-execution boundary."""


class UnsupportedLanguage(CodeRunnerError):
    pass


class InvalidCodeSubmission(CodeRunnerError):
    pass
