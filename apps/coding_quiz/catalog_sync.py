from django.db import transaction

from apps.learning_core.models import Concept, LearningActivity, Subject, Topic

from .catalog import CODING_CATALOG
from .models import CodingExercise
from .catalog_validation import database_exercise_payload, validate_catalog


CONCEPT_DEFINITIONS = {
    'loop_values': {
        'topic_slug': 'python-loops', 'topic_name': 'Python loops',
        'topic_description': 'Iterating over lists', 'concept_slug': 'loop-values',
        'concept_name': 'Loop variables',
        'concept_description': 'Use each loop value deliberately.',
    },
    'dictionary_keys': {
        'topic_slug': 'python-collections', 'topic_name': 'Python collections',
        'topic_description': 'Lists and dictionaries', 'concept_slug': 'dictionary-keys',
        'concept_name': 'Dictionary keys',
        'concept_description': 'Map dictionary keys to values and handle missing keys safely.',
    },
    'function_parameters_and_return': {
        'topic_slug': 'python-functions', 'topic_name': 'Python functions',
        'topic_description': 'Parameters, conditions, and return values',
        'concept_slug': 'function-parameters-and-return',
        'concept_name': 'Function parameters and return values',
        'concept_description': 'Use parameters safely and return the intended result.',
    },
    'list_indexing': {
        'topic_slug': 'python-collections', 'topic_name': 'Python collections',
        'topic_description': 'Lists and dictionaries', 'concept_slug': 'list-indexing',
        'concept_name': 'List indexing',
        'concept_description': 'Use zero-based indexes and handle empty-list boundaries.',
    },
}


def _get_or_create_concept(subject, concept_code):
    definition = CONCEPT_DEFINITIONS[concept_code]
    topic, _ = Topic.objects.get_or_create(
        subject=subject,
        slug=definition['topic_slug'],
        defaults={
            'name': definition['topic_name'],
            'description': definition['topic_description'],
        },
    )
    concept, _ = Concept.objects.get_or_create(
        topic=topic,
        slug=definition['concept_slug'],
        defaults={
            'name': definition['concept_name'],
            'description': definition['concept_description'],
        },
    )
    return concept


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
            elif (
                database_exercise_payload(exercise) == item
                and exercise.activity.concept.slug
                == CONCEPT_DEFINITIONS[item['rubric']['concept']]['concept_slug']
            ):
                report['unchanged'].append(item['slug'])
            else:
                report['updated'].append(item['slug'])
        return report
    subject, _ = Subject.objects.get_or_create(
        slug='coding',
        defaults={'name': 'Coding', 'description': 'Beginner Python'},
    )
    report = {'created': [], 'updated': [], 'unchanged': []}
    for item in catalog:
        concept = _get_or_create_concept(subject, item['rubric']['concept'])
        transfer = item['transfer']
        exercise = CodingExercise.objects.filter(slug=item['slug']).select_related(
            'activity', 'transfer_activity'
        ).first()
        transfer_activity = exercise.transfer_activity if exercise else None
        if transfer_activity is None:
            transfer_activity, _ = LearningActivity.objects.get_or_create(
                concept=concept,
                title=transfer['title'],
                defaults={'activity_type': 'coding_transfer', 'prompt': transfer['prompt']},
            )
        transfer_concept_changed = transfer_activity.concept_id != concept.pk
        transfer_activity.concept = concept
        transfer_activity.activity_type = 'coding_transfer'
        transfer_activity.prompt = transfer['prompt']
        transfer_activity.rubric = {
            'concept': item['rubric']['concept'],
            'hidden_test_ids': transfer['test_ids'],
            'action_terms': transfer['action_terms'],
            'unassisted': True,
        }
        activity = exercise.activity if exercise else None
        if activity is None:
            activity, _ = LearningActivity.objects.get_or_create(
                concept=concept,
                title=item['title'],
                defaults={'activity_type': 'coding', 'prompt': item['prompt']},
            )
        activity_concept_changed = activity.concept_id != concept.pk
        activity.concept = concept
        activity.activity_type = 'coding'
        activity.prompt = item['prompt']
        activity.reference_answer = item['rubric']['revision_solution']
        activity.rubric = item['rubric']
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
        elif before == after and not activity_concept_changed and not transfer_concept_changed:
            report['unchanged'].append(item['slug'])
        else:
            report['updated'].append(item['slug'])
    return report
