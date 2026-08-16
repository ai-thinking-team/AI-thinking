from django.urls import path

from . import views

app_name = 'progress'

urlpatterns = [
    # '' is the all-subjects grid; '?subject=<slug>' focuses one subject.
    path('', views.dashboard, name='dashboard'),
    # Namespaced under coding/ because it is the only subject with a
    # per-session drill-down so far — see views.coding_session_detail.
    path('coding/sessions/<int:session_id>/', views.coding_session_detail, name='coding_session_detail'),
    path('dev-tools/', views.dev_tools, name='dev_tools'),
    path('dev-seed/', views.dev_seed, name='dev_seed'),
    path('dev-clear/', views.dev_clear, name='dev_clear'),
]
