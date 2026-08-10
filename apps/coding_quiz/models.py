from django.db import models

from apps.learning_core.models import LearningActivity


class CodingExercise(models.Model):
    activity = models.OneToOneField(
        LearningActivity,
        on_delete=models.CASCADE,
        related_name='coding_exercise',
    )
    language = models.CharField(max_length=20, default='python', editable=False)
    starter_code = models.TextField(blank=True)
    public_test_description = models.TextField(blank=True)
    hidden_test_ids = models.JSONField(default=list, blank=True)
    transfer_prompt = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.activity.title
