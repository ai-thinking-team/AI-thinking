import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('coding_quiz', '0004_codingexercise_slug_required'),
        ('learning_core', '0007_mysql_compatible_active_session'),
    ]

    operations = [
        migrations.CreateModel(
            name='CodingPlanEvidence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('solution_plan', models.TextField()),
                ('predicted_output', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('activity', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coding_plans', to='learning_core.learningactivity')),
                ('learning_session', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='coding_plan', to='learning_core.learningsession')),
            ],
        ),
    ]
