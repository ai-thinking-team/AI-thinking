from django.urls import path

from . import views

app_name = 'lang_quiz'

urlpatterns = [
    path('', views.home, name='home'),
    path('exercise/', views.exercise, name='exercise'),
    path('setup/<str:section>/', views.material_setup, name='material_setup'),
    path('start/<str:section>/', views.start_quiz, name='start_quiz'),
    path('start/course/<slug:course_slug>/', views.start_course, name='start_course'),
    path('start/material/<str:section>/', views.start_material_quiz, name='start_material_quiz'),
    path('quiz/<uuid:run_id>/', views.quiz_run, name='quiz_run'),
]
