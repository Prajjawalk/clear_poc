"""URL patterns for alerts app."""

from django.urls import path

from . import views
from . import api

app_name = "alerts"

urlpatterns = [
    # Alert views
    path("", views.AlertListView.as_view(), name="alert_list"),
    path("alert/<int:pk>/", views.AlertDetailView.as_view(), name="alert_detail"),
    path("alert/create/", views.AlertCreateView.as_view(), name="alert_create"),
    # Subscription views
    path("subscriptions/", views.SubscriptionListView.as_view(), name="subscription_list"),
    path("subscription/create/", views.SubscriptionCreateView.as_view(), name="subscription_create"),
    path("subscription/<int:pk>/edit/", views.SubscriptionUpdateView.as_view(), name="subscription_edit"),
    path("subscription/<int:pk>/delete/", views.SubscriptionDeleteView.as_view(), name="subscription_delete"),
    # User Alert interactions
    path("alert/<int:alert_id>/rate/", views.rate_alert, name="rate_alert"),
    path("alert/<int:alert_id>/bookmark/", views.toggle_bookmark, name="toggle_bookmark"),
    path("alert/<int:alert_id>/flag/", views.flag_alert, name="flag_alert"),
    path("alert/<int:alert_id>/feedback/", views.add_feedback, name="add_feedback"),
    # Map view
    path("map/", views.AlertMapView.as_view(), name="alert_map"),
    
    # API endpoints (authenticated)
    path("api/alerts/", api.AlertsAPIView.as_view(), name="api_alerts"),
    path("api/alert/<int:alert_id>/", api.AlertDetailAPIView.as_view(), name="api_alert_detail"),
    path("api/shock-types/", api.ShockTypesAPIView.as_view(), name="api_shock_types"),
    path("api/subscriptions/", api.UserSubscriptionsAPIView.as_view(), name="api_subscriptions"),
    path("api/stats/", api.AlertStatsAPIView.as_view(), name="api_stats"),
    
    # Public API endpoints (external integrations)
    path("api/public/alerts/", api.PublicAlertsAPIView.as_view(), name="api_public_alerts"),
    path("api/public/shock-types/", api.PublicShockTypesAPIView.as_view(), name="api_public_shock_types"),
    path("api/public/stats/", api.PublicAlertStatsAPIView.as_view(), name="api_public_stats"),
    
    # Webhook endpoints
    path("webhook/alert/create/", api.webhook_alert_create, name="webhook_alert_create"),
]
