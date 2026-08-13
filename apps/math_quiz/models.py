from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .state_machine import WorkflowState


class Unit(models.Model):
    name = models.CharField(max_length=100, unique=True)
    file = models.FileField(upload_to='units/', blank=True, null=True)
    is_demo = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class UnitMaterial(models.Model):
    """Reference material added to an existing Unit after creation (see
    views.add_unit_material) — kept as its own 1-to-many table rather than
    repurposing Unit.file, so the single-file-at-creation field keeps its
    original meaning and existing data is untouched. AI section
    generation reads these too — see services.generate_sections /
    services._unit_material_files."""
    unit = models.ForeignKey(Unit, related_name='materials', on_delete=models.CASCADE)
    file = models.FileField(upload_to='units/materials/')
    content_type = models.CharField(max_length=100, blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('uploaded_at',)

    def __str__(self):
        return self.file.name


class Section(models.Model):
    unit = models.ForeignKey(Unit, related_name='sections', on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.unit.name} - {self.title}'


class ConfidenceCalibration(models.TextChoices):
    """Does the learner's self-reported confidence match the outcome?
    Computed per judged attempt — see mastery.classify_confidence_calibration."""
    UNKNOWN = 'UNKNOWN', 'Unknown'
    WELL_CALIBRATED = 'WELL_CALIBRATED', 'Well calibrated'
    OVERCONFIDENT = 'OVERCONFIDENT', 'Overconfident'
    UNDERCONFIDENT = 'UNDERCONFIDENT', 'Underconfident'


class MasteryState(models.TextChoices):
    NOT_STARTED = 'NOT_STARTED', 'Not started'
    IN_PROGRESS = 'IN_PROGRESS', 'In progress'
    MASTERED = 'MASTERED', 'Mastered'
    NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'


class ConceptMastery(models.Model):
    """The durable learner model for one (section, browser) pair — a
    Section is this app's unit of "concept". Unlike SectionSession, which
    is deleted and recreated every time a learner restarts a section (see
    services.reset_section_session), this persists across resets and
    accumulates evidence over time: how much hinting was needed, whether
    confidence tracks outcomes, suspected misconceptions, and a composite
    mastery_score. mastery_score is informational — it does not drive the
    MASTERED/NEEDS_REVIEW gate, which stays driven by Transfer Check
    outcome (see services.submit_transfer_check)."""
    section = models.ForeignKey(Section, related_name='mastery_records', on_delete=models.CASCADE)
    browser_session_key = models.CharField(max_length=40, db_index=True)

    knowledge_score = models.FloatField(default=0)  # 0-100, first-attempt/revision performance
    transfer_score = models.FloatField(default=0)  # 0-100, Transfer Check performance
    teach_back_score = models.FloatField(null=True, blank=True)  # 0-100; unused until Teach-Back returns (P1)
    hint_dependency = models.FloatField(default=0)  # running average hint level needed
    mastery_score = models.FloatField(default=0)  # 0-100 composite — see mastery.compute_mastery_score
    mastery_state = models.CharField(
        max_length=20, choices=MasteryState.choices, default=MasteryState.NOT_STARTED,
    )

    misconception_type = models.CharField(max_length=100, blank=True, default='')
    misconception_probability = models.FloatField(default=0)  # 0-1, latest estimate
    confidence_calibration = models.CharField(
        max_length=20, choices=ConfidenceCalibration.choices, default=ConfidenceCalibration.UNKNOWN,
    )

    attempt_count = models.PositiveIntegerField(default=0)
    hint_count = models.PositiveIntegerField(default=0)
    successful_transfer_count = models.PositiveIntegerField(default=0)
    failed_transfer_count = models.PositiveIntegerField(default=0)

    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_mastered_at = models.DateTimeField(null=True, blank=True)
    review_due_at = models.DateTimeField(null=True, blank=True)  # groundwork for spaced recheck (P2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('section', 'browser_session_key'),
                name='unique_section_browser_mastery',
            )
        ]


class SectionSession(models.Model):
    section = models.ForeignKey(Section, related_name='sessions', on_delete=models.CASCADE)
    browser_session_key = models.CharField(max_length=40, db_index=True)
    current_state = models.CharField(
        max_length=32,
        choices=WorkflowState.choices,
        default=WorkflowState.FIRST_ATTEMPT,
    )
    first_problem = models.TextField(blank=True, default='')
    transfer_problem = models.TextField(blank=True, default='')
    # Which Teach-Back level (if any) was decided for this round of the
    # section — '' means Level 0 (skipped). Set once, at the moment of
    # leaving VERIFICATION/GUIDED_REVISION — see mastery.decide_teach_back_level.
    TEACH_BACK_LEVEL_CHOICES = (
        ('', 'None'),
        ('SHORT', 'Short'),
        ('TARGETED', 'Targeted'),
    )
    teach_back_level = models.CharField(max_length=10, choices=TEACH_BACK_LEVEL_CHOICES, blank=True, default='')
    # Short machine-readable tag for why that level was chosen (e.g.
    # 'verification_heuristic_clear', 'revision_high_hint') — kept so the
    # reasoning behind teach_back_level can be reconstructed later without a
    # dedicated analytics table.
    teach_back_level_reason = models.CharField(max_length=40, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('section', 'browser_session_key'),
                name='unique_section_browser_session',
            )
        ]


class UnitDiagnosticSession(models.Model):
    """A short quiz — a few problems drawn from across the course's
    sections — taken once each time a learner enters a course, to gauge
    their current understanding of the subject before they pick a section."""
    unit = models.ForeignKey(Unit, related_name='diagnostic_sessions', on_delete=models.CASCADE)
    browser_session_key = models.CharField(max_length=40, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('unit', 'browser_session_key'),
                name='unique_unit_browser_diagnostic',
            )
        ]


class UnitDiagnosticAnswer(models.Model):
    session = models.ForeignKey(UnitDiagnosticSession, related_name='answers', on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    problem = models.TextField()
    answer = models.TextField(blank=True, default='')
    is_correct = models.BooleanField(null=True, blank=True)
    explanation = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('order',)


class DiagnosticQuizAttempt(models.Model):
    session = models.OneToOneField(SectionSession, related_name='diagnostic_quiz', on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)


class Attempt(models.Model):
    class ReasoningQuality(models.TextChoices):
        STRONG = 'STRONG', 'Strong'
        PARTIAL = 'PARTIAL', 'Partial'
        WEAK = 'WEAK', 'Weak'
        ABSENT = 'ABSENT', 'Absent'

    session = models.ForeignKey(
        SectionSession, related_name='attempts', on_delete=models.CASCADE, null=True, blank=True,
    )
    section = models.ForeignKey(Section, related_name='attempts', on_delete=models.CASCADE)
    problem = models.TextField()
    answer = models.TextField()
    reasoning = models.TextField(blank=True, default='')
    confidence = models.PositiveSmallIntegerField()
    revision_number = models.PositiveIntegerField(default=0)
    is_correct = models.BooleanField(null=True, blank=True)
    explanation = models.TextField(blank=True)
    diagnosis_question = models.TextField(blank=True, default='')
    suspected_misconception = models.CharField(max_length=100, blank=True)
    verification_question = models.TextField(blank=True, default='')
    verification_answer = models.TextField(blank=True, default='')
    # How well `reasoning` (the learner's stated explanation) supports the
    # answer given — evidence of understanding, not proof of it. Never
    # inferred from correctness alone; see mastery.classify_reasoning_quality.
    reasoning_quality = models.CharField(
        max_length=10, choices=ReasoningQuality.choices, blank=True, default='',
    )
    # How likely a genuine misconception (vs. a slip or partial learning)
    # explains a wrong answer — an estimate, not a fact. 0 when not assessed.
    misconception_probability = models.FloatField(default=0)
    class VerificationUnderstanding(models.TextChoices):
        CLEAR = 'CLEAR', 'Clear'
        UNCLEAR = 'UNCLEAR', 'Unclear'

    # Result of judging a Verification-stage answer (quadrant B only) — set
    # by services.submit_verification. Blank for attempts that aren't the
    # verification step.
    verification_understanding = models.CharField(
        max_length=10, choices=VerificationUnderstanding.choices, blank=True, default='',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class HintUsage(models.Model):
    attempt = models.ForeignKey(Attempt, related_name='hints', on_delete=models.CASCADE)
    level = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)


class TeachBackAttempt(models.Model):
    """One round of adaptive Teach-Back. `question` is what was actually
    shown before this answer (the fixed Level 1 prompt, or an AI/demo
    generated Level 2 targeted question); `response` is the learner's
    single short answer to it. `round_number` (0-based) caps how many
    follow-up rounds a section can loop through — see
    services.submit_teach_back and MAX_TEACH_BACK_ROUNDS.

    Older rows created before this adaptive redesign store `response` as a
    JSON-encoded dict of the previous 5-field long-form answer instead of
    plain text — harmless for existing data since nothing renders
    `response` directly (see evaluation/feedback below)."""
    session = models.ForeignKey(SectionSession, related_name='teach_backs', on_delete=models.CASCADE)
    question = models.TextField(blank=True, default='')
    response = models.TextField()
    round_number = models.PositiveIntegerField(default=0)
    evaluation = models.CharField(max_length=40, blank=True)
    feedback = models.TextField(blank=True)
    follow_up_question = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TransferAttempt(models.Model):
    session = models.ForeignKey(SectionSession, related_name='transfer_attempts', on_delete=models.CASCADE)
    problem = models.TextField()
    answer = models.TextField()
    reasoning = models.TextField(blank=True, default='')
    confidence = models.PositiveSmallIntegerField()
    is_correct = models.BooleanField(null=True, blank=True)
    explanation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MathQuestion(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = 'MULTIPLE_CHOICE', 'Multiple choice'
        NUMERIC = 'NUMERIC', 'Numeric'
        WRITTEN = 'WRITTEN', 'Written'

    prompt = models.TextField()
    question_type = models.CharField(max_length=24, choices=QuestionType.choices)
    choices = models.JSONField(default=list, blank=True)
    reference_answer = models.TextField(blank=True)
    reasoning_rubric = models.JSONField(default=dict, blank=True)
