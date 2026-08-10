from django.db import models


class Unit(models.Model):
    name = models.CharField(max_length=100, unique=True)
    file = models.FileField(upload_to='units/', blank=True, null=True)

    def __str__(self):
        return self.name


class Section(models.Model):
    unit = models.ForeignKey(Unit, related_name='sections', on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.unit.name} - {self.title}'


class Attempt(models.Model):
    section = models.ForeignKey(Section, related_name='attempts', on_delete=models.CASCADE)
    problem = models.TextField()
    answer = models.TextField()
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
