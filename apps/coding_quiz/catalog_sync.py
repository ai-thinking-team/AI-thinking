from django.db import transaction

from apps.learning_core.models import Concept, LearningActivity, Subject, Topic

from .catalog import CODING_CATALOG
from .models import CodingExercise
from .catalog_validation import database_exercise_payload, validate_catalog


@transaction.atomic
def sync_catalog(*, catalog=CODING_CATALOG, dry_run=False):
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError('\n'.join(errors))
    if dry_run:
        report = {'created': [], 'updated': [], 'unchanged': []}
        for item in catalog:
            exercise = CodingExercise.objects.filter(slug=item['slug']).select_related(
                'activity', 'transfer_activity'
            ).first()
            if exercise is None:
                report['created'].append(item['slug'])
            elif database_exercise_payload(exercise) == item:
                report['unchanged'].append(item['slug'])
            else:
                report['updated'].append(item['slug'])
        return report
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
    report = {'created': [], 'updated': [], 'unchanged': []}
    for item in catalog:
        transfer = item['transfer']
        transfer_activity, _ = LearningActivity.objects.get_or_create(
            concept=concept,
            title=transfer['title'],
            defaults={'activity_type': 'coding_transfer', 'prompt': transfer['prompt']},
        )
        transfer_activity.activity_type = 'coding_transfer'
        transfer_activity.prompt = transfer['prompt']
        transfer_activity.rubric = {
            'concept': item['rubric']['concept'],
            'hidden_test_ids': transfer['test_ids'],
            'action_terms': transfer['action_terms'],
            'unassisted': True,
        }
        activity, _ = LearningActivity.objects.get_or_create(
            concept=concept,
            title=item['title'],
            defaults={'activity_type': 'coding', 'prompt': item['prompt']},
        )
        activity.activity_type = 'coding'
        activity.prompt = item['prompt']
        activity.reference_answer = item['rubric']['revision_solution']
        activity.rubric = item['rubric']
        exercise = CodingExercise.objects.filter(slug=item['slug']).first()
        created = exercise is None
        if exercise is None:
            exercise, created = CodingExercise.objects.get_or_create(
                activity=activity,
                defaults={'slug': item['slug']},
            )
        before = (exercise.slug, exercise.display_order, exercise.starter_code, exercise.public_test_ids, exercise.hidden_test_ids, exercise.transfer_test_ids, exercise.active, exercise.transfer_activity_id)
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
        exercise.active = item['active']
        after = (exercise.slug, exercise.display_order, exercise.starter_code, exercise.public_test_ids, exercise.hidden_test_ids, exercise.transfer_test_ids, exercise.active, transfer_activity.pk)
        if not dry_run:
            transfer_activity.save()
            activity.save()
            exercise.save()
        if created:
            report['created'].append(item['slug'])
        elif before == after:
            report['unchanged'].append(item['slug'])
        else:
            report['updated'].append(item['slug'])
    return report
