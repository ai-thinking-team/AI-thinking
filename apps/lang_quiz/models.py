from django.db import models
import uuid

from apps.learning_core.models import LearningActivity


class LanguageQuestion(models.Model):
    class QuestionType(models.TextChoices):
        VOCABULARY = 'VOCABULARY', 'Vocabulary'
        GRAMMAR = 'GRAMMAR', 'Grammar'
        READING = 'READING', 'Reading comprehension'
        WRITTEN = 'WRITTEN', 'Written answer'

    activity = models.OneToOneField(
        LearningActivity,
        on_delete=models.CASCADE,
        related_name='language_question',
        null=True,
        blank=True,
    )
    prompt = models.TextField()
    title_ja = models.CharField(max_length=255, blank=True)  # Japanese title for UI headings
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    reference_answer = models.TextField(blank=True)
    rubric = models.JSONField(default=dict, blank=True)
    transfer_prompt = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        if self.activity:
            return self.activity.title
        return f'{self.question_type}: {self.prompt[:30]}'


class LanguageQuizRun(models.Model):
    """A fresh, anonymous ten-question run stored for one browser session."""

    class Section(models.TextChoices):
        VOCABULARY = 'vocabulary', 'Vocabulary'
        READING = 'reading', 'Reading'
        GRAMMAR = 'grammar', 'Grammar'
        MYSELF = 'myself', 'Myself'
        MISSING = 'missing', 'Missing'
        DIAGNOSTIC = 'diagnostic', 'Diagnostic test'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    browser_session_key = models.CharField(max_length=40, db_index=True)
    section = models.CharField(max_length=20, choices=Section.choices)
    mode = models.CharField(max_length=20, blank=True)
    course_slug = models.SlugField(blank=True)
    source_name = models.CharField(max_length=255, blank=True)
    instruction = models.TextField(blank=True)
    questions = models.JSONField(default=list)
    current_index = models.PositiveSmallIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField(default=0)
    finished = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)


class MyselfStagePack(models.Model):
    """A reusable five-stage course generated from one uploaded material set."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    browser_session_key = models.CharField(max_length=40, db_index=True)
    source_name = models.CharField(max_length=255)
    instruction = models.TextField()
    material_text = models.TextField()
    answer_mode = models.CharField(max_length=20, default='typing')
    questions_by_stage = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)


class MissingLanguageQuestion(models.Model):
    """Questions a browser got wrong; a later correct answer removes them."""

    browser_session_key = models.CharField(max_length=40, db_index=True)
    fingerprint = models.CharField(max_length=64)
    section = models.CharField(max_length=20)
    prompt = models.TextField()
    reference_answer = models.TextField()
    explanation = models.TextField(blank=True)
    next_step = models.TextField(blank=True)
    hints = models.JSONField(default=list)
    choices = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('browser_session_key', 'fingerprint'),
                name='unique_missing_language_question',
            )
        ]
        ordering = ('-updated_at',)


class LanguageCourseProgress(models.Model):
    browser_session_key = models.CharField(max_length=40, db_index=True)
    course_slug = models.SlugField()
    correct_question_keys = models.JSONField(default=list)
    score_percent = models.PositiveSmallIntegerField(default=0)
    completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('browser_session_key', 'course_slug'),
                name='unique_language_course_progress',
            )
        ]
