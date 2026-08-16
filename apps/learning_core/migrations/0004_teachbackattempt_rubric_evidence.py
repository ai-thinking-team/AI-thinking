from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('learning_core', '0003_mastery_and_misconception_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='teachbackattempt',
            name='follow_up_question',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='teachbackattempt',
            name='rubric_evidence',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
