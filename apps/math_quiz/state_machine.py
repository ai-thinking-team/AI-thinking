from django.db import models


class WorkflowState(models.TextChoices):
    FIRST_ATTEMPT = 'FIRST_ATTEMPT', 'First attempt'
    DIAGNOSIS = 'DIAGNOSIS', 'Diagnosis'
    VERIFICATION = 'VERIFICATION', 'Verification'
    GUIDED_REVISION = 'GUIDED_REVISION', 'Guided revision'
    TEACH_BACK = 'TEACH_BACK', 'Teach-Back'
    TRANSFER_TASK = 'TRANSFER_TASK', 'Transfer task'
    MASTERED = 'MASTERED', 'Mastered'
    NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'


ALLOWED_TRANSITIONS = {
    # A confident, correct first try (quadrant A) skips straight to
    # Transfer — no uncertainty or misconception signal to teach back from.
    WorkflowState.FIRST_ATTEMPT: {
        WorkflowState.DIAGNOSIS, WorkflowState.VERIFICATION, WorkflowState.TRANSFER_TASK,
    },
    WorkflowState.DIAGNOSIS: {WorkflowState.GUIDED_REVISION},
    # Correct but unsure (quadrant B) — Teach-Back checks the understanding
    # behind the hedge before moving on, but only when the verification
    # answer itself doesn't already show clear understanding (adaptive
    # Teach-Back level — see mastery.heuristic_verification_signal).
    WorkflowState.VERIFICATION: {WorkflowState.TEACH_BACK, WorkflowState.TRANSFER_TASK},
    # Got here via a wrong first attempt (quadrant C/D) — Teach-Back checks
    # the misconception was actually resolved, not just patched over, but
    # only when warranted (see mastery.decide_teach_back_level).
    WorkflowState.GUIDED_REVISION: {
        WorkflowState.TEACH_BACK, WorkflowState.TRANSFER_TASK, WorkflowState.NEEDS_REVIEW,
    },
    WorkflowState.TEACH_BACK: {WorkflowState.TRANSFER_TASK},
    WorkflowState.TRANSFER_TASK: {WorkflowState.MASTERED, WorkflowState.NEEDS_REVIEW},
    WorkflowState.MASTERED: set(),
    WorkflowState.NEEDS_REVIEW: set(),
}


class InvalidWorkflowTransition(ValueError):
    pass


def validate_transition(current_state, target_state):
    current = WorkflowState(current_state)
    target = WorkflowState(target_state)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidWorkflowTransition(f'Cannot transition from {current} to {target}.')


def hints_allowed(state):
    return WorkflowState(state) == WorkflowState.GUIDED_REVISION
