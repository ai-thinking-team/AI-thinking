from django.contrib import admin

from .models import (
    Concept,
    ConceptMastery,
    CoachInteraction,
    CoachLearnerResponse,
    HintUsage,
    LearnerAttempt,
    LearningActivity,
    LearningSession,
    MisconceptionRecord,
    Subject,
    TeachBackAttempt,
    Topic,
    TransferAttempt,
)

admin.site.register((Subject, Topic, Concept, LearningActivity, LearningSession))
admin.site.register((
    LearnerAttempt,
    HintUsage,
    CoachInteraction,
    CoachLearnerResponse,
    MisconceptionRecord,
    TeachBackAttempt,
    TransferAttempt,
    ConceptMastery,
))
