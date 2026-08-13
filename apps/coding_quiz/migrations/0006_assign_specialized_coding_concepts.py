from django.db import migrations


DEFINITIONS = {
    'loop_values': ('python-loops', 'Python loops', 'Iterating over lists', 'loop-values', 'Loop variables', 'Use each loop value deliberately.'),
    'dictionary_keys': ('python-collections', 'Python collections', 'Lists and dictionaries', 'dictionary-keys', 'Dictionary keys', 'Map dictionary keys to values and handle missing keys safely.'),
    'function_parameters_and_return': ('python-functions', 'Python functions', 'Parameters, conditions, and return values', 'function-parameters-and-return', 'Function parameters and return values', 'Use parameters safely and return the intended result.'),
    'list_indexing': ('python-collections', 'Python collections', 'Lists and dictionaries', 'list-indexing', 'List indexing', 'Use zero-based indexes and handle empty-list boundaries.'),
}


def assign_specialized_concepts(apps, schema_editor):
    Subject = apps.get_model('learning_core', 'Subject')
    Topic = apps.get_model('learning_core', 'Topic')
    Concept = apps.get_model('learning_core', 'Concept')
    LearningSession = apps.get_model('learning_core', 'LearningSession')
    MisconceptionRecord = apps.get_model('learning_core', 'MisconceptionRecord')
    ConceptMastery = apps.get_model('learning_core', 'ConceptMastery')
    CodingExercise = apps.get_model('coding_quiz', 'CodingExercise')

    subject, _ = Subject.objects.get_or_create(
        slug='coding',
        defaults={'name': 'Coding', 'description': 'Beginner Python'},
    )
    for exercise in CodingExercise.objects.select_related('activity', 'transfer_activity'):
        rubric = exercise.activity.rubric if isinstance(exercise.activity.rubric, dict) else {}
        concept_code = rubric.get('concept', 'loop_values')
        definition = DEFINITIONS.get(concept_code, DEFINITIONS['loop_values'])
        topic, _ = Topic.objects.get_or_create(
            subject=subject,
            slug=definition[0],
            defaults={'name': definition[1], 'description': definition[2]},
        )
        concept, _ = Concept.objects.get_or_create(
            topic=topic,
            slug=definition[3],
            defaults={'name': definition[4], 'description': definition[5]},
        )
        exercise.activity.concept = concept
        exercise.activity.save(update_fields=('concept',))
        if exercise.transfer_activity_id:
            exercise.transfer_activity.concept = concept
            exercise.transfer_activity.save(update_fields=('concept',))

        sessions = LearningSession.objects.filter(activity_id=exercise.activity_id)
        for session in sessions:
            session.topic = topic
            session.save(update_fields=('topic',))
            MisconceptionRecord.objects.filter(learning_session=session).update(concept=concept)
            ConceptMastery.objects.filter(learning_session=session).update(concept=concept)


class Migration(migrations.Migration):
    dependencies = [
        ('coding_quiz', '0005_codingplanevidence'),
    ]

    operations = [
        migrations.RunPython(assign_specialized_concepts, migrations.RunPython.noop),
    ]
