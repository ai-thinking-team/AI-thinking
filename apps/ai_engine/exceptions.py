class AIEngineError(RuntimeError):
    """Base exception for the shared AI boundary."""


class AIServiceUnavailable(AIEngineError):
    """Raised when no configured AI provider can safely answer."""


class InvalidAIResponse(AIEngineError):
    """Raised when provider output does not match the requested schema."""
