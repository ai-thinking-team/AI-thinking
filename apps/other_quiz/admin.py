from django.contrib import admin
from .models import Subject, Lesson, Question

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'icon')

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('id', 'chapter', 'title', 'subject')
    list_filter = ('subject',)

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'q_type')
    list_filter = ('q_type', 'lesson__subject')
