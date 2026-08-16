from django.db import migrations, models


def release_ended_session_slots(apps, schema_editor):
    LearningSession = apps.get_model('learning_core', 'LearningSession')
    LearningSession.objects.filter(ended_at__isnull=False).update(active_slot=None)


class Migration(migrations.Migration):
    dependencies = [('learning_core', '0006_exercise_sessions')]

    operations = [
        migrations.RemoveConstraint(
            model_name='learningsession',
            name='unique_active_browser_activity_session',
        ),
        migrations.AddField(
            model_name='learningsession',
            name='active_slot',
            field=models.BooleanField(default=True, editable=False, null=True),
        ),
        migrations.RunPython(
            release_ended_session_slots,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='learningsession',
            constraint=models.UniqueConstraint(
                fields=('browser_session_key', 'activity', 'active_slot'),
                name='unique_active_browser_activity_session',
            ),
        ),
    ]
