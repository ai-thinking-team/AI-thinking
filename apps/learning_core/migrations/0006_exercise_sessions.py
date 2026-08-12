import django.db.models.deletion
from django.db import migrations, models


def attach_existing_sessions_to_activity(apps, schema_editor):
    LearningSession = apps.get_model('learning_core', 'LearningSession')
    LearningActivity = apps.get_model('learning_core', 'LearningActivity')
    for session in LearningSession.objects.filter(activity__isnull=True).iterator():
        attempt = session.attempts.order_by('created_at', 'pk').first()
        activity = attempt.activity if attempt and attempt.activity_id else None
        if activity is None:
            activity = LearningActivity.objects.filter(
                concept__topic_id=session.topic_id,
                activity_type='coding',
            ).order_by('pk').first()
        if activity:
            session.activity_id = activity.pk
            session.save(update_fields=('activity',))


class Migration(migrations.Migration):
    dependencies = [('learning_core', '0005_coach_interactions')]

    operations = [
        migrations.RemoveConstraint(
            model_name='learningsession',
            name='unique_browser_topic_session',
        ),
        migrations.AddField(
            model_name='learningsession',
            name='activity',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='learning_sessions',
                to='learning_core.learningactivity',
            ),
        ),
        migrations.AddField(
            model_name='learningsession',
            name='ended_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            attach_existing_sessions_to_activity,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='learningsession',
            constraint=models.UniqueConstraint(
                condition=models.Q(activity__isnull=False, ended_at__isnull=True),
                fields=('browser_session_key', 'activity'),
                name='unique_active_browser_activity_session',
            ),
        ),
    ]
