"""URL patterns for data pipeline web interface and API."""

from django.urls import path

from . import views, api

app_name = 'data_pipeline'

urlpatterns = [
    # Web Interface - Dashboard
    path('', views.dashboard, name='dashboard'),

    # Web Interface - Sources
    path('sources/', views.source_list, name='source_list'),
    path('sources/create/', views.source_create, name='source_create'),
    path('sources/<int:source_id>/', views.source_detail, name='source_detail'),
    path('sources/<int:source_id>/edit/', views.source_edit, name='source_edit'),
    path('sources/<int:source_id>/delete/', views.source_delete, name='source_delete'),

    # Web Interface - Variables
    path('variables/', views.variable_list, name='variable_list'),
    path('variables/create/', views.variable_create, name='variable_create'),
    path('variables/<int:variable_id>/', views.variable_detail, name='variable_detail'),
    path('variables/<int:variable_id>/edit/', views.variable_edit, name='variable_edit'),
    path('variables/<int:variable_id>/delete/', views.variable_delete, name='variable_delete'),

    # Data Removal Actions
    path('sources/<int:source_id>/remove-data/', views.remove_source_data, name='remove_source_data'),
    path('variables/<int:variable_id>/remove-data/', views.remove_variable_data, name='remove_variable_data'),

    # Data Retrieval Actions
    path('variables/<int:variable_id>/retrieve/', views.trigger_variable_retrieval, name='trigger_variable_retrieval'),
    path('sources/<int:source_id>/retrieve/', views.trigger_source_retrieval, name='trigger_source_retrieval'),
    path('sources/<int:source_id>/retrieve-all/', views.trigger_source_retrieval_all, name='trigger_source_retrieval_all'),

    # Data Export Actions
    path('sources/<int:source_id>/export/', views.export_source_data, name='export_source_data'),

    # Map Interface
    path('map/', views.map_view, name='map'),

    # API Endpoints
    path('api/sources/', views.sources_api, name='sources_api'),
    path('api/variables/', views.variables_api, name='variables_api'),
    path('api/data/', views.data_api, name='data_api'),
    path('api/statistics/', views.statistics_api, name='statistics_api'),
    path('api/map-data/', views.map_data_api, name='map_data_api'),
    
    # Location Update API
    path('api/update-locations/', api.update_locations, name='update_locations'),
    path('api/health/', api.health, name='api_health'),
]
