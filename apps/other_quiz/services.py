import os
import re
import uuid
from pypdf import PdfReader
import docx
from django.db import transaction

from .models import Subject, Lesson, Question


# --- 1. HÀM CHẤM ĐIỂM ---

def evaluate_multiple_choice(selected_option, correct_option):
    return {
        'is_correct': str(selected_option).strip() == str(correct_option).strip(),
        'selected': selected_option
    }

def evaluate_rubric(user_text, keywords, threshold=0.75):
    if not user_text or not keywords:
        return {'is_passed': False, 'score_percent': 0, 'user_text': user_text or ''}
        
    user_text_lower = user_text.lower()
    # So sánh trực tiếp chuỗi giúp tương thích tốt với tiếng Việt có dấu và tiếng Nhật/Trung
    matched_count = sum(1 for kw in keywords if kw.lower() in user_text_lower)
    total_keywords = len(keywords)
    
    score_percent = (matched_count / total_keywords) if total_keywords > 0 else 0
    
    return {
        'is_passed': score_percent >= threshold,
        'score_percent': round(score_percent * 100),
        'user_text': user_text
    }


# --- 2. HÀM TRÍCH XUẤT VĂN BẢN TỪ FILE ---

def extract_text_from_file(uploaded_file) -> str:
    """Trích xuất chuỗi văn bản từ file (PDF, DOCX, TXT) với kiểm tra kích thước & đa bảng mã."""
    # Giới hạn kích thước file tối đa 10MB
    if uploaded_file.size > 10 * 1024 * 1024:
        raise ValueError("Kích thước file quá lớn (tối đa 10MB).")

    uploaded_file.seek(0)
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    text = ""

    try:
        if ext == ".pdf":
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"

        elif ext == ".docx":
            doc = docx.Document(uploaded_file)
            text = "\n".join([p.text for p in doc.paragraphs if p.text])

        elif ext == ".txt":
            content = uploaded_file.read()
            # Thử decode với nhiều bảng mã phổ biến (UTF-8, Shift-JIS tiếng Nhật, v.v.)
            for encoding in ['utf-8', 'shift_jis', 'euc-jp', 'utf-16']:
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if not text:
                text = content.decode('utf-8', errors='ignore')

    except ValueError:
        raise
    except Exception as e:
        print(f"Lỗi khi đọc file: {e}")
        return ""

    return text.strip()


# --- 3. HÀM GỌI GROQ API & LƯU DATABASE ---

def can_evaluate_open_response(question):
    """Only evaluate an open response when local reference evidence exists."""
    return bool(
        str(getattr(question, 'correct_answer', '') or '').strip()
        or getattr(question, 'rubric_keywords', None)
    )


def generate_and_save_lesson(subject: Subject, uploaded_file) -> Lesson:
    """Create a deterministic local lesson without exporting uploaded material."""
    raw_text = extract_text_from_file(uploaded_file)
    if not raw_text:
        raise ValueError('The uploaded file is empty or contains no readable text.')

    sentences = [
        item.strip()
        for item in re.split(r'(?<=[.!?])\s+|\r?\n', raw_text[:10000])
        if item.strip()
    ]
    if not sentences:
        raise ValueError('No usable lesson content was found.')

    with transaction.atomic():
        lesson = Lesson.objects.create(
            id=f'les_{uuid.uuid4().hex[:8]}',
            subject=subject,
            chapter='Imported material',
            title=os.path.splitext(uploaded_file.name)[0][:200] or 'New lesson',
        )
        for index, sentence in enumerate(sentences[:10], start=1):
            keywords = list(dict.fromkeys(
                word.casefold() for word in re.findall(r'\w{4,}', sentence, flags=re.UNICODE)
            ))[:4]
            Question.objects.create(
                lesson=lesson,
                title=f'Question {index}',
                prompt=f'Explain the key idea in this excerpt: {sentence}',
                q_type='RUBRIC',
                rubric_keywords=keywords,
                explanation=sentence,
            )
    return lesson
