from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lang_quiz', '0006_myselfstagepack'),
    ]

    operations = [
        migrations.AddField(
            model_name='myselfstagepack',
            name='answer_mode',
            field=models.CharField(default='typing', max_length=20),
        ),
    ]
