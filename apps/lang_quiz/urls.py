from django.urls import path

from . import views

app_name = 'lang_quiz'

urlpatterns = [
    path('', views.home, name='home'),
    path('exercise/', views.exercise, name='exercise'),
    path('setup/<str:section>/', views.material_setup, name='material_setup'),
    path('start/vocabulary/<str:answer_mode>/', views.start_vocabulary, name='start_vocabulary'),
    path('start/<str:section>/', views.start_quiz, name='start_quiz'),
    path('start/course/<slug:course_slug>/', views.start_course, name='start_course'),
    path('start/stage/<slug:stage_slug>/', views.start_stage, name='start_stage'),
    path('myself/stages/<uuid:pack_id>/', views.myself_stage_pack, name='myself_stage_pack'),
    path('myself/stages/<uuid:pack_id>/delete/', views.delete_myself_stage_pack, name='delete_myself_stage_pack'),
    path('myself/stages/<uuid:pack_id>/<int:stage_number>/', views.start_myself_stage, name='start_myself_stage'),
    path('start/material/<str:section>/', views.start_material_quiz, name='start_material_quiz'),
    path('quiz/<uuid:run_id>/', views.quiz_run, name='quiz_run'),
]
