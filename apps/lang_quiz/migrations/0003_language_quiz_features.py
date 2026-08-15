import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lang_quiz', '0002_languagequestion_activity_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LanguageQuizRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('browser_session_key', models.CharField(db_index=True, max_length=40)),
                ('section', models.CharField(choices=[('vocabulary', 'Vocabulary'), ('reading', 'Reading'), ('grammar', 'Grammar'), ('myself', 'Myself'), ('missing', 'Missing'), ('diagnostic', 'Diagnostic test')], max_length=20)),
                ('mode', models.CharField(blank=True, max_length=20)),
                ('course_slug', models.SlugField(blank=True)),
                ('source_name', models.CharField(blank=True, max_length=255)),
                ('instruction', models.TextField(blank=True)),
                ('questions', models.JSONField(default=list)),
                ('current_index', models.PositiveSmallIntegerField(default=0)),
                ('correct_count', models.PositiveSmallIntegerField(default=0)),
                ('finished', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ('-created_at',)},
        ),
        migrations.CreateModel(
            name='MissingLanguageQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('browser_session_key', models.CharField(db_index=True, max_length=40)),
                ('fingerprint', models.CharField(max_length=64)),
                ('section', models.CharField(max_length=20)),
                ('prompt', models.TextField()),
                ('reference_answer', models.TextField()),
                ('explanation', models.TextField(blank=True)),
                ('next_step', models.TextField(blank=True)),
                ('hints', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ('-updated_at',)},
        ),
        migrations.CreateModel(
            name='LanguageCourseProgress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('browser_session_key', models.CharField(db_index=True, max_length=40)),
                ('course_slug', models.SlugField()),
                ('correct_question_keys', models.JSONField(default=list)),
                ('score_percent', models.PositiveSmallIntegerField(default=0)),
                ('completed', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name='missinglanguagequestion',
            constraint=models.UniqueConstraint(fields=('browser_session_key', 'fingerprint'), name='unique_missing_language_question'),
        ),
        migrations.AddConstraint(
            model_name='languagecourseprogress',
            constraint=models.UniqueConstraint(fields=('browser_session_key', 'course_slug'), name='unique_language_course_progress'),
        ),
    ]
