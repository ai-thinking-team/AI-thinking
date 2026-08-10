from django.db import models


class LanguageQuestion(models.Model):
    class QuestionType(models.TextChoices):
        VOCABULARY = 'VOCABULARY', 'Vocabulary'
        GRAMMAR = 'GRAMMAR', 'Grammar'
        READING = 'READING', 'Reading comprehension'
        WRITTEN = 'WRITTEN', 'Written answer'

    prompt = models.TextField()
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    reference_answer = models.TextField(blank=True)
    rubric = models.JSONField(default=dict, blank=True)
