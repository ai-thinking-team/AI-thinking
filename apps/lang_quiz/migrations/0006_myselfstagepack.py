import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lang_quiz', '0005_sync_missing_question_choices'),
    ]

    operations = [
        migrations.CreateModel(
            name='MyselfStagePack',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('browser_session_key', models.CharField(db_index=True, max_length=40)),
                ('source_name', models.CharField(max_length=255)),
                ('instruction', models.TextField()),
                ('material_text', models.TextField()),
                ('questions_by_stage', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ('-created_at',)},
        ),
    ]
