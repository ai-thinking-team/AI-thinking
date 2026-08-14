from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('learning_core', '0001_initial'),
        ('lang_quiz', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='languagequestion',
            name='activity',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='language_question', to='learning_core.learningactivity'),
        ),
        migrations.AddField(
            model_name='languagequestion',
            name='active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='languagequestion',
            name='transfer_prompt',
            field=models.TextField(blank=True),
        ),
    ]
