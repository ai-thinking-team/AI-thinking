from django.core.exceptions import ValidationError
from django.db import models

from apps.learning_core.models import LearningActivity, LearningSession


class CodingPlanEvidence(models.Model):
    learning_session = models.OneToOneField(
        LearningSession,
        on_delete=models.CASCADE,
        related_name='coding_plan',
    )
    activity = models.ForeignKey(
        LearningActivity,
        on_delete=models.SET_NULL,
        null=True,
        related_name='coding_plans',
    )
    solution_plan = models.TextField()
    predicted_output = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Plan for session {self.learning_session_id}'


class CodingExercise(models.Model):
    activity = models.OneToOneField(
        LearningActivity,
        on_delete=models.CASCADE,
        related_name='coding_exercise',
    )
    slug = models.SlugField(unique=True)
    language = models.CharField(max_length=20, default='python', editable=False)
    difficulty = models.CharField(max_length=20, default='beginner')
    display_order = models.PositiveIntegerField(default=0)
    starter_code = models.TextField(blank=True)
    public_test_description = models.TextField(blank=True)
    public_test_ids = models.JSONField(default=list, blank=True)
    hidden_test_ids = models.JSONField(default=list, blank=True)
    transfer_prompt = models.TextField(blank=True)
    transfer_test_ids = models.JSONField(default=list, blank=True)
    transfer_activity = models.ForeignKey(
        LearningActivity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_coding_exercises',
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ('display_order', 'pk')

    def clean(self):
        super().clean()
        if not self.active:
            return
        if not self.activity_id:
            raise ValidationError({'active': 'An active exercise must reference a learning activity.'})
        from .catalog_validation import validate_database_exercise
        errors = validate_database_exercise(self)
        if errors:
            raise ValidationError({'active': errors})

    def __str__(self):
        return self.activity.title
