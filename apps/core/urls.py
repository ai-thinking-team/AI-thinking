from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('subjects/', views.subject_selection, name='subject_selection'),
]
