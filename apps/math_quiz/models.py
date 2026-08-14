from django.db import models


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
