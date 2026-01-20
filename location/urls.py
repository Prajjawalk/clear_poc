"""URL patterns for location management - both web interface and API endpoints."""

from django.urls import path

from . import views

app_name = 'location'

urlpatterns = [
    # =============================================================================
    # WEB INTERFACE URLS
    # =============================================================================

    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Location management
    path('locations/', views.LocationListView.as_view(), name='location_list'),
    path('locations/<int:pk>/', views.LocationDetailView.as_view(), name='location_detail'),
    path('locations/create/', views.LocationCreateView.as_view(), name='location_create'),
    path('locations/<int:pk>/edit/', views.LocationUpdateView.as_view(), name='location_update'),
    path('locations/<int:pk>/delete/', views.LocationDeleteView.as_view(), name='location_delete'),

    # Gazetteer management
    path('gazetteer/', views.GazetteerListView.as_view(), name='gazetteer_list'),
    path('gazetteer/create/', views.GazetteerCreateView.as_view(), name='gazetteer_create'),
    path('gazetteer/<int:pk>/edit/', views.GazetteerUpdateView.as_view(), name='gazetteer_update'),
    path('gazetteer/<int:pk>/delete/', views.GazetteerDeleteView.as_view(), name='gazetteer_delete'),

    # Location matcher
    path('matcher/', views.location_matcher_view, name='location_matcher'),

    # Location browser with map
    path('browse/', views.location_browser_view, name='location_browser'),

    # Unmatched locations management
    path('unmatched/', views.unmatched_locations_view, name='unmatched_locations'),

    # =============================================================================
    # API ENDPOINTS
    # =============================================================================

    # List locations with filtering/pagination
    path('api/locations/', views.locations_api, name='locations_api'),

    # List administrative levels
    path('api/admin-levels/', views.admin_levels_api, name='admin_levels_api'),

    # Location matching endpoints
    path('api/match/', views.match_location_api, name='match_location_api'),
    path('api/bulk-match/', views.bulk_match_locations_api, name='bulk_match_locations_api'),

    # Location hierarchy
    path('api/locations/<int:location_id>/hierarchy/', views.location_hierarchy_api, name='location_hierarchy_api'),

    # Location browser API endpoints
    path('api/browser/locations/', views.browser_locations_api, name='browser_locations_api'),
    path('api/browser/location/<int:location_id>/', views.browser_location_details_api, name='browser_location_details_api'),

    # Unmatched locations API endpoints
    path('api/unmatched/add-to-gazetteer/', views.add_to_gazetteer_ajax, name='add_to_gazetteer_ajax'),
    path('api/unmatched/delete/', views.delete_unmatched_ajax, name='delete_unmatched_ajax'),

    # AJAX location search for manual matching
    path('api/search/', views.location_search_api, name='location_search_api'),
]
