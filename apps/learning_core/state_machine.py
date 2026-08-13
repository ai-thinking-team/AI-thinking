from django.db import models


class WorkflowState(models.TextChoices):
    TOPIC_SELECTED = 'TOPIC_SELECTED', 'Topic selected'
    DIAGNOSTIC_QUIZ = 'DIAGNOSTIC_QUIZ', 'Diagnostic quiz'
    FIRST_ATTEMPT = 'FIRST_ATTEMPT', 'First attempt'
    RESPONSE_EVALUATION = 'RESPONSE_EVALUATION', 'Response evaluation'
    DIAGNOSIS = 'DIAGNOSIS', 'Diagnosis'
    VERIFICATION = 'VERIFICATION', 'Verification'
    GUIDED_REVISION = 'GUIDED_REVISION', 'Guided revision'
    TEACH_BACK = 'TEACH_BACK', 'Teach-Back'
    TRANSFER_TASK = 'TRANSFER_TASK', 'Transfer task'
    MASTERED = 'MASTERED', 'Mastered'
    NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'


ALLOWED_TRANSITIONS = {
    WorkflowState.TOPIC_SELECTED: {WorkflowState.DIAGNOSTIC_QUIZ},
    WorkflowState.DIAGNOSTIC_QUIZ: {WorkflowState.FIRST_ATTEMPT},
    WorkflowState.FIRST_ATTEMPT: {WorkflowState.RESPONSE_EVALUATION},
    WorkflowState.RESPONSE_EVALUATION: {
        WorkflowState.DIAGNOSIS, WorkflowState.VERIFICATION, WorkflowState.TEACH_BACK,
    },
    WorkflowState.DIAGNOSIS: {WorkflowState.GUIDED_REVISION},
    WorkflowState.VERIFICATION: {WorkflowState.TEACH_BACK},
    WorkflowState.GUIDED_REVISION: {WorkflowState.RESPONSE_EVALUATION, WorkflowState.TEACH_BACK},
    WorkflowState.TEACH_BACK: {WorkflowState.GUIDED_REVISION, WorkflowState.TRANSFER_TASK},
    WorkflowState.TRANSFER_TASK: {WorkflowState.MASTERED, WorkflowState.NEEDS_REVIEW},
    WorkflowState.MASTERED: set(),
    WorkflowState.NEEDS_REVIEW: {WorkflowState.TOPIC_SELECTED},
}


class InvalidWorkflowTransition(ValueError):
    pass


def validate_transition(current_state, target_state):
    current = WorkflowState(current_state)
    target = WorkflowState(target_state)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidWorkflowTransition(f'Cannot transition from {current} to {target}.')


def ai_assistance_allowed(state):
    return WorkflowState(state) in {
        WorkflowState.DIAGNOSIS, WorkflowState.VERIFICATION, WorkflowState.GUIDED_REVISION,
    }


def hints_allowed(state):
    return WorkflowState(state) == WorkflowState.GUIDED_REVISION
