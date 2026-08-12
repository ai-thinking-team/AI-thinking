from django.db import transaction

from apps.learning_core.models import LearningSession, Subject, Topic
from apps.learning_core.state_machine import WorkflowState

DEMO_SUBJECTS = {
    'math': ('Mathematics', [
        ('fractions', 'Fractions', WorkflowState.MASTERED),
        ('linear-equations', 'Linear equations', WorkflowState.MASTERED),
        ('probability-basics', 'Probability basics', WorkflowState.NEEDS_REVIEW),
        ('geometry-angles', 'Geometry angles', WorkflowState.FIRST_ATTEMPT),
        ('word-problems', 'Word problems', WorkflowState.TEACH_BACK),
        ('quadratic-equations', 'Quadratic equations', WorkflowState.TOPIC_SELECTED),
    ]),
    'coding': ('Coding', [
        ('functions', 'Functions', WorkflowState.MASTERED),
        ('recursion', 'Recursion', WorkflowState.NEEDS_REVIEW),
        ('list-comprehensions', 'List comprehensions', WorkflowState.FIRST_ATTEMPT),
        ('dictionaries', 'Dictionaries', WorkflowState.TEACH_BACK),
        ('error-handling', 'Error handling', WorkflowState.TOPIC_SELECTED),
    ]),
    'languages': ('Languages', [
        ('basic-greetings', 'Basic greetings', WorkflowState.MASTERED),
        ('verb-conjugation', 'Verb conjugation', WorkflowState.MASTERED),
        ('adjective-order', 'Adjective order', WorkflowState.NEEDS_REVIEW),
        ('past-tense', 'Past tense', WorkflowState.FIRST_ATTEMPT),
        ('reading-comprehension', 'Reading comprehension', WorkflowState.TEACH_BACK),
        ('idioms', 'Idioms', WorkflowState.TOPIC_SELECTED),
    ]),
    'other': ('Other Subjects', [
        ('ww2-causes', 'World War II causes', WorkflowState.MASTERED),
        ('cell-biology', 'Cell biology', WorkflowState.NEEDS_REVIEW),
        ('supply-and-demand', 'Supply and demand', WorkflowState.FIRST_ATTEMPT),
        ('photosynthesis', 'Photosynthesis', WorkflowState.TEACH_BACK),
        ('french-revolution', 'French Revolution', WorkflowState.TOPIC_SELECTED),
        ("newtons-laws", "Newton's laws", WorkflowState.MASTERED),
    ]),
}


@transaction.atomic
def seed_demo_progress(browser_session_key):
    for slug, (name, topics) in DEMO_SUBJECTS.items():
        subject, _ = Subject.objects.get_or_create(slug=slug, defaults={'name': name})
        for topic_slug, topic_name, state in topics:
            topic, _ = Topic.objects.get_or_create(
                subject=subject, slug=topic_slug, defaults={'name': topic_name},
            )
            LearningSession.objects.update_or_create(
                browser_session_key=browser_session_key,
                topic=topic,
                defaults={'current_state': state},
            )


def clear_demo_progress(browser_session_key):
    LearningSession.objects.filter(browser_session_key=browser_session_key).delete()
