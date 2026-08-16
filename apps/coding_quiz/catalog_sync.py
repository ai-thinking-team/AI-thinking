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
    'conditionals': {
        'topic_slug': 'python-conditionals', 'topic_name': 'Python conditionals',
        'topic_description': 'Choosing behavior from conditions', 'concept_slug': 'if-else',
        'concept_name': 'If-else branches',
        'concept_description': 'Use ordered conditions to select the correct branch.',
    },
    'function_basics': {
        'topic_slug': 'python-functions', 'topic_name': 'Python functions',
        'topic_description': 'Parameters, conditions, and return values', 'concept_slug': 'function-basics',
        'concept_name': 'Function basics',
        'concept_description': 'Use parameters to calculate and return a result.',
    },
    'list_1d_operations': {
        'topic_slug': 'python-lists', 'topic_name': 'Python lists',
        'topic_description': 'One-dimensional and two-dimensional list processing',
        'concept_slug': 'one-dimensional-lists',
        'concept_name': 'One-dimensional lists',
        'concept_description': 'Traverse list elements and build totals or counts.',
    },
    'list_2d_traversal': {
        'topic_slug': 'python-lists', 'topic_name': 'Python lists',
        'topic_description': 'One-dimensional and two-dimensional list processing',
        'concept_slug': 'two-dimensional-lists',
        'concept_name': 'Two-dimensional lists',
        'concept_description': 'Use rows and nested loops to process every value.',
    },
    'string_operations': {
        'topic_slug': 'python-strings', 'topic_name': 'Python strings',
        'topic_description': 'Character sequences and text transformations', 'concept_slug': 'string-operations',
        'concept_name': 'String operations',
        'concept_description': 'Transform and inspect ordered character sequences.',
    },
    'recursion': {
        'topic_slug': 'python-recursion', 'topic_name': 'Python recursion',
        'topic_description': 'Base cases and smaller recursive calls', 'concept_slug': 'recursion',
        'concept_name': 'Recursion',
        'concept_description': 'Stop at a base case and solve the problem with a smaller call.',
    },
    'binary_search': {
        'topic_slug': 'dsa-searching', 'topic_name': 'DSA: Searching',
        'topic_description': 'Search algorithms and ordered-data invariants', 'concept_slug': 'binary-search',
        'concept_name': 'Binary search',
        'concept_description': 'Use sorted input and moving boundaries to discard half a range.',
    },
    'stack': {
        'topic_slug': 'dsa-linear-structures', 'topic_name': 'DSA: Linear structures',
        'topic_description': 'Stacks and queues', 'concept_slug': 'stack',
        'concept_name': 'Stack',
        'concept_description': 'Use last-in-first-out order to manage nested work.',
    },
    'queue': {
        'topic_slug': 'dsa-linear-structures', 'topic_name': 'DSA: Linear structures',
        'topic_description': 'Stacks and queues', 'concept_slug': 'queue',
        'concept_name': 'Queue',
        'concept_description': 'Use first-in-first-out order to process waiting work.',
    },
    'sorting': {
        'topic_slug': 'dsa-sorting', 'topic_name': 'DSA: Sorting',
        'topic_description': 'Ordering data with explicit invariants', 'concept_slug': 'sorting',
        'concept_name': 'Sorting',
        'concept_description': 'Maintain a sorted result while selecting values from the remainder.',
    },
    'hash_maps': {
        'topic_slug': 'dsa-hash-maps', 'topic_name': 'DSA: Hash maps',
        'topic_description': 'Fast key-based lookup', 'concept_slug': 'hash-maps',
        'concept_name': 'Hash maps',
        'concept_description': 'Store and retrieve values by key to avoid repeated scans.',
    },
    'graphs': {
        'topic_slug': 'dsa-graphs', 'topic_name': 'DSA: Graphs',
        'topic_description': 'Nodes, edges, and traversal', 'concept_slug': 'graph-traversal',
        'concept_name': 'Graph traversal',
        'concept_description': 'Explore neighbor links while tracking visited nodes.',
    },
    'dynamic_programming': {
        'topic_slug': 'dsa-dynamic-programming', 'topic_name': 'DSA: Dynamic programming',
        'topic_description': 'Base cases and reusable subproblem states', 'concept_slug': 'dynamic-programming',
        'concept_name': 'Dynamic programming',
        'concept_description': 'Build a solution from stored results for smaller states.',
    },
    'set_operations': {
        'topic_slug': 'python-sets', 'topic_name': 'Python sets',
        'topic_description': 'Unique values and set relationships', 'concept_slug': 'set-operations',
        'concept_name': 'Set operations',
        'concept_description': 'Use sets for uniqueness and membership relationships.',
    },
    'list_comprehensions': {
        'topic_slug': 'python-comprehensions', 'topic_name': 'Python comprehensions',
        'topic_description': 'Build collections with compact expressions', 'concept_slug': 'list-comprehensions',
        'concept_name': 'List comprehensions',
        'concept_description': 'Transform and filter values while building a new list.',
    },
    'exception_handling': {
        'topic_slug': 'python-exceptions', 'topic_name': 'Python exception handling',
        'topic_description': 'Safe recovery from invalid operations', 'concept_slug': 'exception-handling',
        'concept_name': 'Exception handling',
        'concept_description': 'Handle expected failures with a focused try-except block.',
    },
    'numeric_algorithms': {
        'topic_slug': 'python-numeric-algorithms', 'topic_name': 'Python numeric algorithms',
        'topic_description': 'Number properties and arithmetic algorithms', 'concept_slug': 'numeric-algorithms',
        'concept_name': 'Numeric algorithms',
        'concept_description': 'Use arithmetic invariants to solve number problems.',
    },
    'two_pointers': {
        'topic_slug': 'dsa-two-pointers', 'topic_name': 'DSA: Two pointers',
        'topic_description': 'Coordinate two indexes through ordered data', 'concept_slug': 'two-pointers',
        'concept_name': 'Two pointers',
        'concept_description': 'Move two pointers according to a comparison invariant.',
    },
    'sliding_window': {
        'topic_slug': 'dsa-sliding-window', 'topic_name': 'DSA: Sliding window',
        'topic_description': 'Maintain a moving contiguous range', 'concept_slug': 'sliding-window',
        'concept_name': 'Sliding window',
        'concept_description': 'Update a window state as its boundaries move.',
    },
    'greedy_algorithms': {
        'topic_slug': 'dsa-greedy', 'topic_name': 'DSA: Greedy algorithms',
        'topic_description': 'Choose a locally best next step', 'concept_slug': 'greedy-algorithms',
        'concept_name': 'Greedy algorithms',
        'concept_description': 'Make a justified local choice while preserving a solution invariant.',
    },
    'backtracking': {
        'topic_slug': 'dsa-backtracking', 'topic_name': 'DSA: Backtracking',
        'topic_description': 'Explore choices and undo partial work', 'concept_slug': 'backtracking',
        'concept_name': 'Backtracking',
        'concept_description': 'Explore candidate choices recursively and backtrack safely.',
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
