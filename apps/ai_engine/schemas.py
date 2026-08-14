from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticResponse:
    possible_misconception: str
    diagnostic_confidence: float
    response_type: str
    message: str
    hint_level: int
    should_reveal_solution: bool = False
