from django.db import transaction

from .models import LearningSession
from .state_machine import WorkflowState, validate_transition


@transaction.atomic
def transition_session(learning_session, target_state):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    validate_transition(locked_session.current_state, target_state)
    locked_session.current_state = WorkflowState(target_state)
    locked_session.save(update_fields=('current_state', 'updated_at'))
    learning_session.current_state = locked_session.current_state
    return learning_session


def get_or_create_demo_session(*, browser_session_key, topic):
    return LearningSession.objects.get_or_create(
        browser_session_key=browser_session_key,
        topic=topic,
    )


def mastery_requirements_met(*, original_passed, teach_back_clear, transfer_passed,
                             transfer_unassisted, misconception_repeated):
    return all((original_passed, teach_back_clear, transfer_passed, transfer_unassisted)) and not misconception_repeated
