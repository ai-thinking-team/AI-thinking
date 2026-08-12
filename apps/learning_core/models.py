from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .state_machine import WorkflowState


class Subject(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Topic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=150)
    slug = models.SlugField()
    description = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('subject', 'slug'), name='unique_subject_topic')]

    def __str__(self):
        return f'{self.subject}: {self.name}'


class Concept(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='concepts')
    name = models.CharField(max_length=150)
    slug = models.SlugField()
    description = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('topic', 'slug'), name='unique_topic_concept')]

    def __str__(self):
        return self.name


class LearningActivity(models.Model):
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name='activities')
    title = models.CharField(max_length=200)
    activity_type = models.CharField(max_length=50)
    prompt = models.TextField()
    reference_answer = models.TextField(blank=True)
    rubric = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.title


class LearningSession(models.Model):
    browser_session_key = models.CharField(max_length=40, db_index=True)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='learning_sessions')
    activity = models.ForeignKey(
        LearningActivity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='learning_sessions',
    )
    current_state = models.CharField(
        max_length=32,
        choices=WorkflowState.choices,
        default=WorkflowState.TOPIC_SELECTED,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    active_slot = models.BooleanField(default=True, null=True, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('browser_session_key', 'activity', 'active_slot'),
                name='unique_active_browser_activity_session',
            )
        ]


class LearnerAttempt(models.Model):
    learning_session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name='attempts')
    activity = models.ForeignKey(
        LearningActivity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attempts',
    )
    answer = models.TextField()
    reasoning = models.TextField()
    confidence = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    revision_number = models.PositiveIntegerField(default=0)
    evaluation = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class HintUsage(models.Model):
    learner_attempt = models.ForeignKey(LearnerAttempt, on_delete=models.CASCADE, related_name='hint_usage')
    level = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)


class CoachInteraction(models.Model):
    class InteractionType(models.TextChoices):
        DIAGNOSTIC = 'DIAGNOSTIC', 'Diagnostic question'
        HINT = 'HINT', 'Hint'

    class Source(models.TextChoices):
        AI = 'AI', 'AI provider'
        CURATED_FALLBACK = 'CURATED_FALLBACK', 'Curated fallback'

    learning_session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='coach_interactions',
    )
    learner_attempt = models.ForeignKey(
        LearnerAttempt,
        on_delete=models.CASCADE,
        related_name='coach_interactions',
    )
    interaction_type = models.CharField(max_length=20, choices=InteractionType.choices)
    source = models.CharField(max_length=20, choices=Source.choices)
    request_context = models.JSONField(default=dict)
    response = models.JSONField(default=dict)
    failure_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CoachLearnerResponse(models.Model):
    interaction = models.OneToOneField(
        CoachInteraction,
        on_delete=models.CASCADE,
        related_name='learner_response',
    )
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class MisconceptionRecord(models.Model):
    class Status(models.TextChoices):
        HYPOTHESIS = 'HYPOTHESIS', 'Unconfirmed hypothesis'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        DISMISSED = 'DISMISSED', 'Dismissed'
        RESOLVED = 'RESOLVED', 'Resolved'
        REPEATED = 'REPEATED', 'Repeated in transfer check'

    learning_session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='misconceptions',
    )
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name='misconception_records')
    code = models.SlugField()
    evidence = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.HYPOTHESIS)
    supersedes = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='follow_up_records',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class TeachBackAttempt(models.Model):
    learning_session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='teach_back_attempts',
    )
    response = models.TextField()
    evaluation = models.CharField(max_length=40, blank=True)
    feedback = models.TextField(blank=True)
    follow_up_question = models.TextField(blank=True)
    rubric_evidence = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TransferAttempt(models.Model):
    learning_session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='transfer_attempts',
    )
    activity = models.ForeignKey(
        LearningActivity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_attempts',
    )
    response = models.TextField()
    reasoning = models.TextField()
    confidence = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    used_assistance = models.BooleanField(default=False)
    passed = models.BooleanField(default=False)
    evaluation = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ConceptMastery(models.Model):
    class Status(models.TextChoices):
        MASTERED = 'MASTERED', 'Mastered'
        NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'

    learning_session = models.ForeignKey(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='mastery_records',
    )
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name='mastery_records')
    status = models.CharField(max_length=20, choices=Status.choices)
    reason = models.TextField()
    recommendation = models.TextField(blank=True)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
