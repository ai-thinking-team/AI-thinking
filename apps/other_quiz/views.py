from django.shortcuts import render, get_object_or_404
from .models import Subject, Lesson
from .services import evaluate_multiple_choice, evaluate_rubric

def home(request):
    subjects = Subject.objects.all()
    return render(request, 'other_quiz/home.html', {'subjects': subjects})

def subject_detail(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    return render(request, 'other_quiz/subject_detail.html', {'subject': subject})

def create_subject(request):
    return render(request, 'other_quiz/create_subject.html')

def lesson_detail(request, subject_id, lesson_id):
    subject = get_object_or_404(Subject, id=subject_id)
    lesson = get_object_or_404(Lesson, id=lesson_id, subject=subject)
    
    # Chuyển QuerySet thành list để lưu thuộc tính tạm .eval trên RAM
    questions = list(lesson.questions.all())

    if request.method == "POST":
        question_id = request.POST.get("question_id")
        action = request.POST.get("action")
        
        # Tìm câu hỏi bằng cách so sánh string ID
        question = next((q for q in questions if str(q.id) == str(question_id)), None)

        if question:
            if action == "submit_mc":
                selected = request.POST.get(f"question_{question_id}")
                question.eval = evaluate_multiple_choice(selected, question.correct_answer)
                
            elif action == "submit_rubric":
                user_text = request.POST.get("rubric_text", "")
                question.eval = evaluate_rubric(user_text, question.rubric_keywords or [])

    return render(request, 'other_quiz/lesson_detail.html', {
        'subject': subject,
        'lesson': lesson,
        'questions': questions
    })
