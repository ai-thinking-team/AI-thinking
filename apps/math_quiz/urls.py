from django.urls import path

from . import views

app_name = 'math_quiz'

urlpatterns = [
    path('', views.home, name='home'),
    path('new/', views.new, name='new'),
    path('add-unit/', views.add_unit, name='add_unit'),
    path('delete-unit/<int:unit_id>/', views.delete_unit, name='delete_unit'),
    path('unit/<int:unit_id>/', views.unit_detail, name='unit_detail'),
    path('section/<int:section_id>/', views.section_quiz, name='section_quiz'),
    path('submit-answer/', views.submit_answer, name='submit_answer'),
]
