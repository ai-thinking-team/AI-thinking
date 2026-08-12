import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('coding_quiz', '0001_initial'),
        ('learning_core', '0006_exercise_sessions'),
    ]

    operations = [
        migrations.AddField(
            model_name='codingexercise',
            name='difficulty',
            field=models.CharField(default='beginner', max_length=20),
        ),
        migrations.AddField(
            model_name='codingexercise',
            name='display_order',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='codingexercise',
            name='public_test_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='codingexercise',
            name='slug',
            field=models.SlugField(null=True, unique=True),
        ),
        migrations.AddField(
            model_name='codingexercise',
            name='transfer_activity',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='source_coding_exercises',
                to='learning_core.learningactivity',
            ),
        ),
        migrations.AddField(
            model_name='codingexercise',
            name='transfer_test_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterModelOptions(
            name='codingexercise',
            options={'ordering': ('display_order', 'pk')},
        ),
    ]
