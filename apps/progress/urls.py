from django.urls import path

from . import views

app_name = 'progress'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('sessions/<int:session_id>/', views.session_detail, name='session_detail'),
]
