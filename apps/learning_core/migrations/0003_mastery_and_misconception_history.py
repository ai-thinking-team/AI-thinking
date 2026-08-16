import django.db.models.deletion
from django.db import migrations, models


def migrate_misconception_statuses(apps, schema_editor):
    MisconceptionRecord = apps.get_model('learning_core', 'MisconceptionRecord')
    for record in MisconceptionRecord.objects.all().iterator():
        if record.resolved_at:
            record.status = 'RESOLVED'
        elif record.confirmed:
            record.status = 'CONFIRMED'
        else:
            record.status = 'HYPOTHESIS'
        record.save(update_fields=('status',))


class Migration(migrations.Migration):
    dependencies = [
        ('learning_core', '0002_transferattempt_evaluation'),
    ]

    operations = [
        migrations.AddField(
            model_name='misconceptionrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('HYPOTHESIS', 'Unconfirmed hypothesis'),
                    ('CONFIRMED', 'Confirmed'),
                    ('DISMISSED', 'Dismissed'),
                    ('RESOLVED', 'Resolved'),
                    ('REPEATED', 'Repeated in transfer check'),
                ],
                default='HYPOTHESIS',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='misconceptionrecord',
            name='supersedes',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='follow_up_records',
                to='learning_core.misconceptionrecord',
            ),
        ),
        migrations.CreateModel(
            name='ConceptMastery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('MASTERED', 'Mastered'), ('NEEDS_REVIEW', 'Needs review')], max_length=20)),
                ('reason', models.TextField()),
                ('recommendation', models.TextField(blank=True)),
                ('evidence', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('concept', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mastery_records', to='learning_core.concept')),
                ('learning_session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mastery_records', to='learning_core.learningsession')),
            ],
        ),
        migrations.RunPython(migrate_misconception_statuses, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='misconceptionrecord',
            name='confirmed',
        ),
        migrations.RemoveField(
            model_name='misconceptionrecord',
            name='resolved_at',
        ),
    ]
