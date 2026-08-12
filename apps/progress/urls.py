from django.urls import path

from . import views

app_name = 'progress'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('dev-tools/', views.dev_tools, name='dev_tools'),
    path('dev-seed/', views.dev_seed, name='dev_seed'),
    path('dev-clear/', views.dev_clear, name='dev_clear'),
]
