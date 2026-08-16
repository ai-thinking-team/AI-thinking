from django.db import migrations
from django.utils.text import slugify


def seed_catalog(apps, schema_editor):
    from apps.coding_quiz.catalog import CODING_CATALOG

    Subject = apps.get_model('learning_core', 'Subject')
    Topic = apps.get_model('learning_core', 'Topic')
    Concept = apps.get_model('learning_core', 'Concept')
    LearningActivity = apps.get_model('learning_core', 'LearningActivity')
    CodingExercise = apps.get_model('coding_quiz', 'CodingExercise')

    subject, _ = Subject.objects.get_or_create(
        slug='coding',
        defaults={'name': 'Coding', 'description': 'Beginner Python'},
    )
    topic, _ = Topic.objects.get_or_create(
        subject=subject,
        slug='python-loops',
        defaults={'name': 'Python loops', 'description': 'Iterating over lists'},
    )
    concept, _ = Concept.objects.get_or_create(
        topic=topic,
        slug='loop-values',
        defaults={'name': 'Loop variables', 'description': 'Use each loop value deliberately.'},
    )

    for item in CODING_CATALOG:
        transfer = item['transfer']
        transfer_activity, _ = LearningActivity.objects.get_or_create(
            concept=concept,
            title=transfer['title'],
            defaults={'activity_type': 'coding_transfer', 'prompt': transfer['prompt']},
        )
        transfer_activity.activity_type = 'coding_transfer'
        transfer_activity.prompt = transfer['prompt']
        transfer_activity.rubric = {
            'concept': 'loop_values',
            'hidden_test_ids': transfer['test_ids'],
            'action_terms': transfer['action_terms'],
            'unassisted': True,
        }
        transfer_activity.save()

        activity, _ = LearningActivity.objects.get_or_create(
            concept=concept,
            title=item['title'],
            defaults={'activity_type': 'coding', 'prompt': item['prompt']},
        )
        activity.activity_type = 'coding'
        activity.prompt = item['prompt']
        activity.reference_answer = item['rubric']['revision_solution']
        activity.rubric = item['rubric']
        activity.save()

        exercise, _ = CodingExercise.objects.get_or_create(activity=activity)
        exercise.slug = item['slug']
        exercise.difficulty = 'beginner'
        exercise.display_order = item['display_order']
        exercise.starter_code = item['starter_code']
        exercise.public_test_description = item['public_test_description']
        exercise.public_test_ids = item['public_test_ids']
        exercise.hidden_test_ids = item['hidden_test_ids']
        exercise.transfer_prompt = transfer['prompt']
        exercise.transfer_test_ids = transfer['test_ids']
        exercise.transfer_activity = transfer_activity
        exercise.active = True
        exercise.save()

    used = set(CodingExercise.objects.exclude(slug__isnull=True).values_list('slug', flat=True))
    for exercise in CodingExercise.objects.filter(slug__isnull=True).select_related('activity'):
        base = slugify(exercise.activity.title) or f'exercise-{exercise.pk}'
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f'{base}-{suffix}'
            suffix += 1
        exercise.slug = candidate
        exercise.save(update_fields=('slug',))
        used.add(candidate)


class Migration(migrations.Migration):
    dependencies = [('coding_quiz', '0002_coding_catalog_schema')]
    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
