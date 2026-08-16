from django.urls import path

from . import views

app_name = 'coding_quiz'

urlpatterns = [
    path('', views.home, name='home'),
    path('topics/<slug:topic_slug>/', views.topic_exercises, name='topic_exercises'),
    path('exercise/', views.exercise, name='exercise'),
    path('exercises/<slug:slug>/', views.exercise, name='exercise_detail'),
]
