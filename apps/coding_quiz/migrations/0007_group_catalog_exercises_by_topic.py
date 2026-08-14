from django.db import migrations


def group_catalog_exercises_by_topic(apps, schema_editor):
    from apps.coding_quiz.catalog import CODING_CATALOG
    from apps.coding_quiz.catalog_sync import CONCEPT_DEFINITIONS

    Subject = apps.get_model('learning_core', 'Subject')
    Topic = apps.get_model('learning_core', 'Topic')
    Concept = apps.get_model('learning_core', 'Concept')
    CodingExercise = apps.get_model('coding_quiz', 'CodingExercise')

    subject = Subject.objects.filter(slug='coding').first()
    if subject is None:
        return

    for item in CODING_CATALOG:
        definition = CONCEPT_DEFINITIONS[item['rubric']['concept']]
        topic, _ = Topic.objects.get_or_create(
            subject_id=subject.pk,
            slug=definition['topic_slug'],
            defaults={
                'name': definition['topic_name'],
                'description': definition['topic_description'],
            },
        )
        concept, _ = Concept.objects.get_or_create(
            topic_id=topic.pk,
            slug=definition['concept_slug'],
            defaults={
                'name': definition['concept_name'],
                'description': definition['concept_description'],
            },
        )
        exercise = CodingExercise.objects.filter(slug=item['slug']).select_related(
            'activity', 'transfer_activity'
        ).first()
        if exercise is None:
            continue
        if exercise.activity_id:
            exercise.activity.concept_id = concept.pk
            exercise.activity.save(update_fields=('concept',))
        if exercise.transfer_activity_id:
            exercise.transfer_activity.concept_id = concept.pk
            exercise.transfer_activity.save(update_fields=('concept',))


class Migration(migrations.Migration):
    dependencies = [('coding_quiz', '0006_assign_specialized_coding_concepts')]

    operations = [migrations.RunPython(group_catalog_exercises_by_topic, migrations.RunPython.noop)]
