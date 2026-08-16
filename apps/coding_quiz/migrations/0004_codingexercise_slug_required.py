from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('coding_quiz', '0003_seed_coding_catalog')]
    operations = [
        migrations.AlterField(
            model_name='codingexercise',
            name='slug',
            field=models.SlugField(unique=True),
        ),
    ]
