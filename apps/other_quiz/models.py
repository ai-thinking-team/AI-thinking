from django.db import models


class OtherSubjectQuestion(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = 'MULTIPLE_CHOICE', 'Multiple choice'
        DEFINITION = 'DEFINITION', 'Definition'
        COMPARISON = 'COMPARISON', 'Comparison or classification'
        EVIDENCE = 'EVIDENCE', 'Evidence-based response'

    subject_name = models.CharField(max_length=100)
    prompt = models.TextField()
    question_type = models.CharField(max_length=24, choices=QuestionType.choices)
    reference_answer = models.TextField(blank=True)
    rubric = models.JSONField(default=dict, blank=True)
