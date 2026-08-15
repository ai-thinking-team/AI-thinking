LESSON_GENERATION_PROMPT = """
Bạn là một chuyên gia giáo dục đa ngôn ngữ. Hãy đọc nội dung tài liệu bên dưới và tạo 01 Bài học gồm ĐÚNG 6 CÂU HỎI ÔN TẬP (bao gồm 5 câu Trắc nghiệm và 1 câu Tự luận/Rubric ngắn).

YÊU CẦU BẮT BUỘC:
1. Tạo ĐÚNG 5 câu hỏi dạng Trắc nghiệm ("q_type": "MULTIPLE_CHOICE").
2. Tạo ĐÚNG 1 câu hỏi dạng Tự luận/Rubric ("q_type": "RUBRIC").
3. CHỈ trả về một chuỗi JSON duy nhất, không kèm theo bất kỳ văn bản hay định dạng markdown nào khác ngoài khối JSON.
4. TỰ ĐỘNG BẢO TỒN NGÔN NGỮ: Tạo toàn bộ tiêu đề bài học, nội dung câu hỏi, phương án lựa chọn, đáp án, giải thích và từ khóa bằng CHÍNH NGÔN NGỮ của tài liệu gốc (ví dụ: tài liệu tiếng Nhật tạo bài học tiếng Nhật, tài liệu tiếng Việt tạo bài học tiếng Việt).

CẤU TRÚC JSON BẮT BUỘC:
{{
  "chapter": "Chương / Phần",
  "title": "Tên bài học rút ra từ tài liệu",
  "questions": [
    {{
      "title": "Tiêu đề ngắn câu trắc nghiệm",
      "prompt": "Nội dung câu hỏi trắc nghiệm?",
      "q_type": "MULTIPLE_CHOICE",
      "options": ["A. Phương án 1", "B. Phương án 2", "C. Phương án 3", "D. Phương án 4"],
      "correct_answer": "A. Phương án 1",
      "rubric_keywords": null,
      "explanation": "Giải thích lý do chọn đáp án đúng..."
    }},
    {{
      "title": "Tiêu đề ngắn câu tự luận",
      "prompt": "Nội dung câu hỏi tự luận / ngắn?",
      "q_type": "RUBRIC",
      "options": null,
      "correct_answer": "Câu trả lời chuẩn tham chiếu",
      "rubric_keywords": ["từ khóa 1", "từ khóa 2", "từ khóa 3"],
      "explanation": "Tiêu chí chấm điểm..."
    }}
  ]
}}

NỘI DUNG TÀI LIỆU:
---
{raw_text}
---
"""