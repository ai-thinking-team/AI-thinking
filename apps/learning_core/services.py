from dataclasses import dataclass

from django.db import transaction

from .models import ConceptMastery, LearningSession
from .state_machine import InvalidWorkflowTransition, WorkflowState, validate_transition


@transaction.atomic
def transition_session(learning_session, target_state):
    locked_session = LearningSession.objects.select_for_update().get(pk=learning_session.pk)
    validate_transition(locked_session.current_state, target_state)
    target = WorkflowState(target_state)
    if target in {WorkflowState.MASTERED, WorkflowState.NEEDS_REVIEW}:
        latest_decision = locked_session.mastery_records.order_by('-created_at', '-pk').first()
        if latest_decision is None or latest_decision.status != target.value:
            raise InvalidWorkflowTransition(
                f'Cannot transition to {target.value} without a stored mastery decision.'
            )
    locked_session.current_state = target
    locked_session.save(update_fields=('current_state', 'updated_at'))
    learning_session.current_state = locked_session.current_state
    return learning_session


def get_or_create_demo_session(*, browser_session_key, topic, activity=None):
    return LearningSession.objects.get_or_create(
        browser_session_key=browser_session_key,
        topic=topic,
        activity=activity,
        ended_at__isnull=True,
        active_slot=True,
    )


def mastery_requirements_met(*, original_passed, teach_back_clear, transfer_passed,
                             transfer_unassisted, misconception_repeated):
    """Return whether the shared learning workflow has sufficient mastery evidence."""
    return all((
        original_passed,
        teach_back_clear,
        transfer_passed,
        transfer_unassisted,
    )) and not misconception_repeated


@dataclass(frozen=True)
class MasteryDecision:
    status: str
    reason: str
    recommendation: str


def evaluate_mastery(*, original_passed, teach_back_clear, transfer_passed,
                     transfer_unassisted, repeated_misconception_codes=(),
                     repeated_misconception_recommendations=None):
    repeated_codes = tuple(repeated_misconception_codes)
    if not original_passed:
        return MasteryDecision(
            ConceptMastery.Status.NEEDS_REVIEW,
            'The original exercise has not passed all required tests.',
            'Revise the original exercise and verify it with the isolated runner.',
        )
    if not teach_back_clear:
        return MasteryDecision(
            ConceptMastery.Status.NEEDS_REVIEW,
            'The Teach-Back did not demonstrate clear understanding.',
            'Explain the original error, its cause, and why the correction works.',
        )
    if not transfer_passed:
        return MasteryDecision(
            ConceptMastery.Status.NEEDS_REVIEW,
            'The unassisted Transfer Check did not pass all required tests.',
            'Review the target concept and complete a new corrective exercise.',
        )
    if not transfer_unassisted:
        return MasteryDecision(
            ConceptMastery.Status.NEEDS_REVIEW,
            'The Transfer Check was completed with assistance.',
            'Complete another Transfer Check without AI or hints.',
        )
    if repeated_codes:
        readable_codes = ', '.join(repeated_codes)
        recommendations = dict(repeated_misconception_recommendations or {})
        recommendation = next(
            (
                recommendations.get(code, '').strip()
                for code in repeated_codes
                if recommendations.get(code, '').strip()
            ),
            'Review the confirmed misconception and complete a corrective exercise before retrying.',
        )
        return MasteryDecision(
            ConceptMastery.Status.NEEDS_REVIEW,
            f'A confirmed misconception was repeated in the Transfer Check: {readable_codes}.',
            recommendation,
        )
    return MasteryDecision(
        ConceptMastery.Status.MASTERED,
        'The original exercise passed, the Teach-Back was clear, and the unassisted Transfer Check passed without repeating a confirmed misconception.',
        '',
    )


@transaction.atomic
def record_mastery_decision(*, learning_session, concept, original_passed, teach_back_clear,
                            transfer_passed, transfer_unassisted, repeated_misconception_codes,
                            evidence, repeated_misconception_recommendations=None):
    decision = evaluate_mastery(
        original_passed=original_passed,
        teach_back_clear=teach_back_clear,
        transfer_passed=transfer_passed,
        transfer_unassisted=transfer_unassisted,
        repeated_misconception_codes=repeated_misconception_codes,
        repeated_misconception_recommendations=repeated_misconception_recommendations,
    )
    record = ConceptMastery.objects.create(
        learning_session=learning_session,
        concept=concept,
        status=decision.status,
        reason=decision.reason,
        recommendation=decision.recommendation,
        evidence=evidence,
    )
    return record
