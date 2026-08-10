from django.urls import path

from . import views

app_name = 'lang_quiz'

urlpatterns = [path('', views.home, name='home')]
