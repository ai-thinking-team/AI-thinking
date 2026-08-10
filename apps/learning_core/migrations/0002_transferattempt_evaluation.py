from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('learning_core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='transferattempt',
            name='evaluation',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
