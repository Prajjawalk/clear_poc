"""URL configuration for LLM service."""

from django.urls import path
from . import views

app_name = 'llm_service'

urlpatterns = [
    # Main dashboard
    path('', views.dashboard, name='dashboard'),

    # Web interfaces
    path('test/', views.test_interface, name='test_interface'),
    path('logs/', views.query_logs, name='query_logs'),

    # API endpoints
    path('api/query/', views.LLMQueryView.as_view(), name='api_query'),
    path('api/providers/status/', views.provider_status, name='api_provider_status'),
    path('api/stats/', views.service_stats, name='api_service_stats'),
]