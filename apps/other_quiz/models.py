from django.db import models

class Subject(models.Model):
    id = models.CharField(max_length=50, primary_key=True, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=10, default="📖")

    def __str__(self):
        return self.title

    @property
    def progress_percent(self) -> int:
        """Calculates total progress percentage for all lessons in this subject."""
        lessons = self.lessons.all()
        total_questions = sum(l.questions.count() for l in lessons)
        if total_questions == 0:
            return 0
        correct_questions = sum(l.questions.filter(is_correct=True).count() for l in lessons)
        return round((correct_questions / total_questions) * 100)

class Lesson(models.Model):
    id = models.CharField(max_length=50, primary_key=True, unique=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='lessons')
    chapter = models.CharField(max_length=50)
    title = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.chapter}: {self.title}"

    @property
    def progress_percent(self):
        total = self.questions.count()
        if total == 0: return 0
        return round((self.questions.filter(is_correct=True).count() / total) * 100)

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
    is_correct = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.lesson.title} - {self.title}"
