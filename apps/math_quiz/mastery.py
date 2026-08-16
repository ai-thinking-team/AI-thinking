"""Scoring and classification for the durable per-concept learner model
(models.ConceptMastery). Kept separate from services.py so the weights and
thresholds below are easy to find and tune in one place — they are
deliberately configurable values, not fixed educational theory.

None of this drives the MASTERED/NEEDS_REVIEW gate (that stays owned by
services.submit_transfer_check, based on Transfer Check outcome). It exists
to make the evidence behind that outcome visible and to inform diagnosis.
"""
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import ConfidenceCalibration
from .state_machine import WorkflowState

# 1-5 self-reported scale. >= this counts as "confident" for calibration
# and for deciding how pointed a diagnosis question should be.
CONFIDENT_THRESHOLD = 4

MASTERY_WEIGHTS = {
    'knowledge': 0.25,        # first-attempt / revision correctness
    'hint_dependency': 0.15,  # inverse — less hinting is better
    'transfer': 0.30,         # Transfer Check performance — weighted highest
    'confidence_calibration': 0.10,
    'teach_back': 0.20,
}

_TEACH_BACK_NOT_YET_ASSESSED = 70  # neutral-ish default; most sections never require it

_CALIBRATION_SCORE = {
    ConfidenceCalibration.WELL_CALIBRATED: 100,
    ConfidenceCalibration.UNKNOWN: 70,
    ConfidenceCalibration.UNDERCONFIDENT: 60,
    ConfidenceCalibration.OVERCONFIDENT: 40,
}


def classify_confidence_calibration(*, is_correct, confidence):
    """Compares self-reported confidence (1-5) against the actual outcome.
    Confidence 3 ("partial understanding") is treated as well-calibrated
    either way — it's a hedge, not a claim."""
    if is_correct:
        return (
            ConfidenceCalibration.UNDERCONFIDENT if confidence <= 2
            else ConfidenceCalibration.WELL_CALIBRATED
        )
    return (
        ConfidenceCalibration.OVERCONFIDENT if confidence >= CONFIDENT_THRESHOLD
        else ConfidenceCalibration.WELL_CALIBRATED
    )


def classify_reasoning_quality_heuristic(*, reasoning, is_correct):
    """Non-AI fallback for how well a stated explanation supports the
    answer. A rough proxy (length + outcome) — evidence, not certainty."""
    length = len(reasoning.strip())
    if length < 5:
        return 'ABSENT'
    if length < 20:
        return 'WEAK'
    return 'STRONG' if is_correct else 'PARTIAL'


def estimate_misconception_probability_heuristic(*, confidence):
    """Non-AI fallback for how likely a wrong answer reflects a genuine
    misconception (quadrant C: wrong + confident) versus still-learning
    uncertainty (quadrant D: wrong + unsure)."""
    return 0.7 if confidence >= CONFIDENT_THRESHOLD else 0.3


# --- Adaptive Teach-Back --------------------------------------------------
# Teach-Back should only be as long/frequent as the evidence warrants — see
# services.submit_verification / submit_revision / submit_teach_back.
# Thresholds below are configurable, same spirit as MASTERY_WEIGHTS.

MAX_TEACH_BACK_ROUNDS = 2  # at most one follow-up question before moving on regardless

# Verification-answer pre-check thresholds. Kept deliberately cheap (no AI
# call) — only an AMBIGUOUS result should trigger an AI judge call.
_VERIFICATION_UNCLEAR_MAX_LENGTH = 8
_VERIFICATION_CLEAR_MIN_LENGTH = 20
_CONCEPT_LANGUAGE_TERMS = ('移項', '両辺', '符号', '方程式')

TEACH_BACK_MISCONCEPTION_THRESHOLD = 0.6
TEACH_BACK_HIGH_HINT_LEVEL = 4
TEACH_BACK_LOW_HINT_LEVEL = 2

_TEACH_BACK_ANSWER_MIN_LENGTH = 10  # below this, an answer is confidently too thin — no AI call needed


def heuristic_verification_signal(*, answer, first_attempt_reasoning_quality):
    """Cheap pre-check before spending an AI call on judging a Verification
    answer. Returns 'CLEAR' or 'UNCLEAR' only when confident without AI;
    'AMBIGUOUS' otherwise, which should fall through to an AI judge call
    (or, if AI isn't configured, to the safer UNCLEAR default) rather than
    guessing CLEAR without real evidence."""
    text = answer.strip()
    if len(text) < _VERIFICATION_UNCLEAR_MAX_LENGTH:
        return 'UNCLEAR'
    if (
        first_attempt_reasoning_quality == 'STRONG'
        and len(text) >= _VERIFICATION_CLEAR_MIN_LENGTH
        and any(term in text for term in _CONCEPT_LANGUAGE_TERMS)
    ):
        return 'CLEAR'
    return 'AMBIGUOUS'


def heuristic_teach_back_signal(*, answer):
    """Cheap pre-check before spending an AI call on judging a Teach-Back
    answer. Only ever returns a confident 'PARTIAL' (clearly too thin to
    show understanding) or 'AMBIGUOUS' — never a confident 'CLEAR' without
    AI, since wrongly skipping the check in the generous direction is the
    costlier mistake."""
    return 'PARTIAL' if len(answer.strip()) < _TEACH_BACK_ANSWER_MIN_LENGTH else 'AMBIGUOUS'


def decide_teach_back_level(*, hint_level_used, misconception_probability, reasoning_quality):
    """Adaptive Teach-Back level for the Guided Revision recovery path
    (quadrant C/D, after a successful revision). Returns (level, reason)
    where level is 'NONE' (skip straight to Transfer — minor slip, quickly
    self-corrected), 'SHORT', or 'TARGETED' (likely misconception or heavy
    hint dependence); reason is a short machine-readable tag recording
    which condition fired, for SectionSession.teach_back_level_reason."""
    if misconception_probability >= TEACH_BACK_MISCONCEPTION_THRESHOLD:
        return 'TARGETED', 'revision_high_misconception'
    if hint_level_used >= TEACH_BACK_HIGH_HINT_LEVEL:
        return 'TARGETED', 'revision_high_hint'
    if hint_level_used <= TEACH_BACK_LOW_HINT_LEVEL and reasoning_quality in ('STRONG', 'PARTIAL'):
        return 'NONE', 'revision_low_risk'
    return 'SHORT', 'revision_moderate'


def compute_mastery_score(*, concept_mastery):
    """0-100 composite from the signals already stored on ConceptMastery.
    Informational only — see module docstring."""
    hint_component = max(0.0, 100 - (concept_mastery.hint_dependency * 20))
    calibration_component = _CALIBRATION_SCORE.get(concept_mastery.confidence_calibration, 70)
    teach_back_component = (
        concept_mastery.teach_back_score if concept_mastery.teach_back_score is not None
        else _TEACH_BACK_NOT_YET_ASSESSED
    )
    components = {
        'knowledge': concept_mastery.knowledge_score,
        'hint_dependency': hint_component,
        'transfer': concept_mastery.transfer_score,
        'confidence_calibration': calibration_component,
        'teach_back': teach_back_component,
    }
    total_weight = sum(MASTERY_WEIGHTS.values())
    score = sum(components[key] * weight for key, weight in MASTERY_WEIGHTS.items())
    return round(score / total_weight, 1) if total_weight else 0.0


def build_evidence_list(*, session, concept_mastery):
    """Bullet points for the outcome screen: what supports Mastered, or
    what points at Needs Review. Built from data the learner already
    produced (Attempt/HintUsage/TransferAttempt), not restated as a verdict."""
    first_attempt = session.attempts.filter(revision_number=0).first()
    latest_attempt = session.attempts.order_by('-revision_number', '-created_at').first()
    transfer_attempt = session.transfer_attempts.order_by('-created_at').first()
    teach_back = session.teach_backs.order_by('-created_at').first()
    hint_count = concept_mastery.hint_count if concept_mastery else 0
    calibration = concept_mastery.confidence_calibration if concept_mastery else ConfidenceCalibration.UNKNOWN

    if session.current_state == WorkflowState.MASTERED:
        evidence = []
        if first_attempt and first_attempt.is_correct:
            evidence.append('初回の問題に、修正なしで正しく解答できました。')
        elif latest_attempt and latest_attempt.is_correct:
            if hint_count:
                evidence.append(f'ヒントを使いながらも（レベル{hint_count}まで）、最終的に自分で正しい解答にたどり着きました。')
            else:
                evidence.append('修正を重ねて、自分で正しい解答にたどり着きました。')
        if first_attempt and first_attempt.reasoning.strip():
            evidence.append('自分の考え方を言葉で説明できました。')
        if teach_back and teach_back.evaluation == 'CLEAR_UNDERSTANDING':
            evidence.append('Teach-Backで、間違いの原因と直し方を自分の言葉で説明できました。')
        if transfer_attempt and transfer_attempt.is_correct:
            evidence.append('別の形式の応用問題（Transfer Check）にも、AIの助けなしで正しく適用できました。')
        if calibration == ConfidenceCalibration.WELL_CALIBRATED:
            evidence.append('自己評価した理解度と、実際の結果がよく一致していました。')
        return evidence or ['この問題を最後まで完了しました。']

    reasons = []
    if transfer_attempt and not transfer_attempt.is_correct:
        reasons.append('応用問題（Transfer Check）でつまずきました。')
    if hint_count >= 4:
        reasons.append(f'ヒントをレベル{hint_count}まで必要としました。')
    if calibration == ConfidenceCalibration.OVERCONFIDENT:
        reasons.append('自信度と実際の結果に少しズレがありました。')
    return reasons or ['もう一度復習すると、理解がより安定しそうです。']


def classify_section_status(*, section_state, concept_mastery):
    """(label, tone) for a section's status pill on the course page.
    Richer than the raw workflow state where the learner model has
    something useful to say — but still just one label at a time, to keep
    the section list scannable rather than cluttered."""
    if section_state == WorkflowState.MASTERED:
        if (
            concept_mastery and concept_mastery.review_due_at
            and concept_mastery.review_due_at <= timezone.now()
        ):
            return _('再確認の時期です'), 'warning'
        return _('Mastered'), 'success'
    if section_state == WorkflowState.NEEDS_REVIEW:
        return _('要復習'), 'warning'
    if section_state:
        if concept_mastery and concept_mastery.confidence_calibration == ConfidenceCalibration.OVERCONFIDENT:
            return _('自信過剰かもしれません'), 'muted'
        if concept_mastery and concept_mastery.confidence_calibration == ConfidenceCalibration.UNDERCONFIDENT:
            return _('自信不足かもしれません'), 'muted'
        return _('理解途中'), 'muted'
    return _('未着手'), 'muted'
