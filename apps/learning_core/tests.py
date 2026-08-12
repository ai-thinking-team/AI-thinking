from django.test import SimpleTestCase

from .models import ConceptMastery
from .services import evaluate_mastery
from .state_machine import (
    InvalidWorkflowTransition,
    WorkflowState,
    ai_assistance_allowed,
    hints_allowed,
    validate_transition,
)


class WorkflowStateMachineTests(SimpleTestCase):
    def test_valid_transition_is_accepted(self):
        validate_transition(WorkflowState.TOPIC_SELECTED, WorkflowState.DIAGNOSTIC_QUIZ)

    def test_first_attempt_cannot_skip_to_mastery(self):
        with self.assertRaises(InvalidWorkflowTransition):
            validate_transition(WorkflowState.FIRST_ATTEMPT, WorkflowState.MASTERED)

    def test_ai_and_hints_are_server_gated(self):
        self.assertFalse(ai_assistance_allowed(WorkflowState.TOPIC_SELECTED))
        self.assertFalse(ai_assistance_allowed(WorkflowState.FIRST_ATTEMPT))
        self.assertTrue(ai_assistance_allowed(WorkflowState.DIAGNOSIS))
        self.assertFalse(hints_allowed(WorkflowState.TRANSFER_TASK))

    def test_mastery_requires_unassisted_transfer(self):
        decision = evaluate_mastery(
            original_passed=True,
            teach_back_clear=True,
            transfer_passed=True,
            transfer_unassisted=False,
            repeated_misconception_codes=(),
        )
        self.assertEqual(decision.status, ConceptMastery.Status.NEEDS_REVIEW)

    def test_mastery_rejects_a_repeated_misconception(self):
        decision = evaluate_mastery(
            original_passed=True,
            teach_back_clear=True,
            transfer_passed=True,
            transfer_unassisted=True,
            repeated_misconception_codes=('loop-value-misuse',),
        )
        self.assertEqual(decision.status, ConceptMastery.Status.NEEDS_REVIEW)
