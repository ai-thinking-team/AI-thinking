def can_evaluate_open_response(question):
    """Open responses require a reliable reference or explicit rubric."""
    return bool(question.reference_answer.strip() or question.rubric)
