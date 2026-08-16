from django.contrib import admin
from django.utils.html import format_html

from .models import CodingExercise, CodingPlanEvidence
from .catalog_validation import validate_database_exercise


@admin.register(CodingExercise)
class CodingExerciseAdmin(admin.ModelAdmin):
    list_display = ('activity', 'slug', 'difficulty', 'display_order', 'active', 'catalog_status')
    list_filter = ('active', 'difficulty', 'language')
    search_fields = ('activity__title', 'slug', 'activity__prompt')
    ordering = ('display_order', 'pk')

    @admin.display(description='Catalog validation')
    def catalog_status(self, obj):
        errors = validate_database_exercise(obj)
        if errors:
            return format_html('<span style="color:#b00020">Invalid ({} issue{})</span>', len(errors), '' if len(errors) == 1 else 's')
        return format_html('<span style="color:#087f23">Valid</span>')


@admin.register(CodingPlanEvidence)
class CodingPlanEvidenceAdmin(admin.ModelAdmin):
    list_display = ('learning_session', 'activity', 'created_at')
    search_fields = ('solution_plan', 'predicted_output')
    readonly_fields = ('learning_session', 'activity', 'solution_plan', 'predicted_output', 'created_at')
