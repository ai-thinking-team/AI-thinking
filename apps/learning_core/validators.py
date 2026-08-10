from django.core.exceptions import ValidationError


def validate_first_attempt(*, answer, reasoning, confidence):
    missing = []
    if not str(answer).strip():
        missing.append('answer')
    if not str(reasoning).strip():
        missing.append('reasoning')
    if confidence not in range(1, 6):
        missing.append('confidence')
    if missing:
        raise ValidationError(f"A first attempt requires: {', '.join(missing)}.")
