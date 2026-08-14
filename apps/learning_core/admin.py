from django.contrib import admin

from .models import (
    Concept,
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
admin.site.register((LearnerAttempt, HintUsage, MisconceptionRecord, TeachBackAttempt, TransferAttempt))
