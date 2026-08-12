import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('learning_core', '0004_teachbackattempt_rubric_evidence'),
    ]

    operations = [
        migrations.CreateModel(
            name='CoachInteraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('interaction_type', models.CharField(choices=[('DIAGNOSTIC', 'Diagnostic question'), ('HINT', 'Hint')], max_length=20)),
                ('source', models.CharField(choices=[('AI', 'AI provider'), ('CURATED_FALLBACK', 'Curated fallback')], max_length=20)),
                ('request_context', models.JSONField(default=dict)),
                ('response', models.JSONField(default=dict)),
                ('failure_code', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('learner_attempt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coach_interactions', to='learning_core.learnerattempt')),
                ('learning_session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coach_interactions', to='learning_core.learningsession')),
            ],
        ),
        migrations.CreateModel(
            name='CoachLearnerResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('response', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('interaction', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='learner_response', to='learning_core.coachinteraction')),
            ],
        ),
    ]
