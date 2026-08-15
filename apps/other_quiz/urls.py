from django.urls import path
from . import views

app_name = 'other_quiz'

urlpatterns = [
    path('', views.home, name='home'),
    path('subject/<str:subject_id>/', views.subject_detail, name='subject_detail'),
    path('subject/<str:subject_id>/lesson/<str:lesson_id>/', views.lesson_detail, name='lesson_detail'),
    path('create-subject/', views.create_subject, name='create_subject'),
]
