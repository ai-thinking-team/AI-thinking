from django.db import migrations


def create_sample_data(apps, schema_editor):
    Subject = apps.get_model('other_quiz', 'Subject')
    Lesson = apps.get_model('other_quiz', 'Lesson')
    Question = apps.get_model('other_quiz', 'Question')

    # 1. Tạo môn học mẫu
    subject = Subject.objects.create(
        id="sub_triet_hoc",
        title="Triết học Mác - Lênin",
        icon="📖",
        description="Lý luận về quy luật vận động chung nhất của tự nhiên, xã hội và tư duy."
    )

    # 2. Tạo bài học mẫu
    lesson = Lesson.objects.create(
        id="les_01",
        subject=subject,
        chapter="Chương 1",
        title="Vật chất và Ý thức"
    )

    # 3. Tạo câu hỏi trắc nghiệm (q1)
    Question.objects.create(
        lesson=lesson,
        title="Phương diện triết học của vật chất",
        prompt="Theo V.I.Lênin, định nghĩa vật chất được xác định thông qua phương pháp nào?",
        q_type="MULTIPLE_CHOICE",
        options=[
            "A. Định nghĩa thông qua sự đối lập với ý thức",
            "B. Quy về các nguyên tử và hạt cơ bản",
            "C. Liệt kê toàn bộ các dạng vật chất cụ thể",
            "D. Đồng nhất vật chất với khối lượng"
        ],
        correct_answer="A. Định nghĩa thông qua sự đối lập với ý thức",
        explanation="Lênin định nghĩa vật chất bằng cách đặt nó trong sự đối lập với ý thức: Vật chất là thực tại khách quan được đem lại cho con người trong cảm giác.",
        is_correct=False
    )

    # 4. Tạo câu hỏi trả lời ngắn / Rubric (q2)
    Question.objects.create(
        lesson=lesson,
        title="Bản chất của Ý thức",
        prompt="Nêu bản chất của ý thức theo quan điểm của chủ nghĩa duy vật biện chứng.",
        q_type="RUBRIC",
        correct_answer="Ý thức là sự phản ánh năng động, sáng tạo thế giới khách quan vào bộ óc con người; là hình ảnh chủ quan của thế giới khách quan.",
        rubric_keywords=["phản ánh", "sáng tạo", "thế giới khách quan", "bộ óc", "hình ảnh chủ quan"],
        explanation="Ý thức không phải là sự phản ánh thụ động, bê nguyên xi mà là quá trình thu nhận, chọn lọc và sáng tạo thông tin.",
        is_correct=False
    )


def reverse_sample_data(apps, schema_editor):
    Subject = apps.get_model('other_quiz', 'Subject')
    Subject.objects.filter(id="sub_triet_hoc").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('other_quiz', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_sample_data, reverse_sample_data),
    ]