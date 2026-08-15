from django.db import models

class Subject(models.Model):
    id = models.CharField(max_length=50, primary_key=True, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=10, default="📖")

    def __str__(self):
        return self.title

class Lesson(models.Model):
    id = models.CharField(max_length=50, primary_key=True, unique=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='lessons')
    chapter = models.CharField(max_length=50)
    title = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.chapter}: {self.title}"

class Question(models.Model):
    QUESTION_TYPES = [
        ('MULTIPLE_CHOICE', 'Trắc nghiệm'),
        ('RUBRIC', 'Trả lời ngắn / Rubric'),
    ]

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='questions')
    title = models.CharField(max_length=200)
    prompt = models.TextField()
    q_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='MULTIPLE_CHOICE')
    options = models.JSONField(blank=True, null=True)
    correct_answer = models.TextField(blank=True, null=True)
    rubric_keywords = models.JSONField(blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.lesson.title} - {self.title}"
