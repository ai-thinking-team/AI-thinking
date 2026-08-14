import json
import os
from django.shortcuts import render, Http404
from .services import evaluate_multiple_choice, evaluate_rubric

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE_PATH = os.path.join(CURRENT_DIR, 'data', 'sample_subjects.json')

def _load_sample_data():
    if not os.path.exists(DATA_FILE_PATH):
        return []
    try:
        with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return []

def home(request):
    subjects = _load_sample_data()
    return render(request, 'other_quiz/home.html', {'subjects': subjects})

def subject_detail(request, subject_id):
    subjects = _load_sample_data()
    subject = next((s for s in subjects if s.get('id') == subject_id), None)
    if not subject:
        raise Http404("Không tìm thấy môn học")
    return render(request, 'other_quiz/subject_detail.html', {'subject': subject})

def create_subject(request):
    return render(request, 'other_quiz/create_subject.html')

def lesson_detail(request, subject_id, lesson_id):
    subjects = _load_sample_data()
    subject = next((s for s in subjects if s.get('id') == subject_id), None)
    if not subject:
        raise Http404("Không tìm thấy môn học")

    lesson = next((l for l in subject.get('lessons', []) if l.get('id') == lesson_id), None)
    if not lesson:
        raise Http404("Không tìm thấy bài học")

    # Xử lý chấm điểm khi Submit
    if request.method == "POST":
        question_id = request.POST.get("question_id")
        action = request.POST.get("action")
        
        # Tìm câu hỏi được nộp
        question = next((q for q in lesson.get('questions', []) if str(q.get('id')) == str(question_id)), None)

        if question:
            if action == "submit_mc":
                selected = request.POST.get(f"question_{question_id}")
                correct = question.get("correct_answer")
                question['eval'] = evaluate_multiple_choice(selected, correct)
                
            elif action == "submit_rubric":
                user_text = request.POST.get("rubric_text", "")
                keywords = question.get("rubric_keywords", [])
                question['eval'] = evaluate_rubric(user_text, keywords)

    return render(request, 'other_quiz/lesson_detail.html', {
        'subject': subject,
        'lesson': lesson
    })