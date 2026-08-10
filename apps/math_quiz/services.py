def first_incorrect_step(*, submitted_steps, evaluated_steps):
    """Scaffold hook for deterministic, rubric-backed step comparison."""
    for index, (submitted, evaluated) in enumerate(zip(submitted_steps, evaluated_steps), start=1):
        if submitted != evaluated:
            return index
    return None
