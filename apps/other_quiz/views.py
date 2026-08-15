from django.shortcuts import render, get_object_or_404, redirect
from .models import Subject, Lesson
from .services import (
    evaluate_multiple_choice, 
    evaluate_rubric, 
    generate_and_save_lesson
)
from django.contrib import messages
import uuid

def home(request):
    subjects = Subject.objects.all()
    return render(request, 'other_quiz/home.html', {'subjects': subjects})

def create_subject(request):
    if request.method == "POST":
        title = request.POST.get("title")
        icon = request.POST.get("icon") or "📖"
        description = request.POST.get("description")

        if title:
            sub_id = f"sub_{uuid.uuid4().hex[:8]}"  # Auto-generate unique ID
            Subject.objects.create(
                id=sub_id,
                title=title,
                icon=icon,
                description=description
            )
            
    return redirect('other_quiz:home')

def subject_detail(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    
    if request.method == "POST" and request.FILES.get("document"):
        try:
            generate_and_save_lesson(subject, request.FILES["document"])
            messages.success(request, "🎉 Đã tạo bài học mới thành công!")
        except Exception as e:
            messages.error(request, f"Lỗi tạo bài học: {str(e)}")
        
        return redirect('other_quiz:subject_detail', subject_id=subject.id)

    return render(request, 'other_quiz/subject_detail.html', {'subject': subject})

def lesson_detail(request, subject_id, lesson_id):
    subject = get_object_or_404(Subject, id=subject_id)
    lesson = get_object_or_404(Lesson, id=lesson_id, subject=subject)
    questions = list(lesson.questions.all())

    if request.method == "POST":
        question_id = request.POST.get("question_id")
        action = request.POST.get("action")
        question = next((q for q in questions if str(q.id) == str(question_id)), None)

        if question:
            if action == "submit_mc":
                selected = request.POST.get(f"question_{question_id}")
                question.eval = evaluate_multiple_choice(selected, question.correct_answer)
                question.is_correct = question.eval['is_correct']
                question.save()
                
            elif action == "submit_rubric":
                user_text = request.POST.get("rubric_text", "")
                question.eval = evaluate_rubric(user_text, question.rubric_keywords or [])
                question.is_correct = question.eval['is_passed']
                question.save()

    return render(request, 'other_quiz/lesson_detail.html', {
        'subject': subject,
        'lesson': lesson,
        'questions': questions
    })