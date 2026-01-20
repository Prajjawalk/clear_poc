"""URL configuration for alert framework."""

from django.urls import path

from alert_framework import api_views, views

app_name = "alert_framework"

urlpatterns = [
    # Dashboard
    path("", views.dashboard_view, name="dashboard"),
    # Detectors
    path("detectors/", views.DetectorListView.as_view(), name="detector_list"),
    path("detectors/<int:pk>/", views.DetectorDetailView.as_view(), name="detector_detail"),
    path("detectors/<int:pk>/edit/", views.DetectorEditView.as_view(), name="detector_edit"),
    path("detectors/<int:pk>/run/", views.DetectorRunView.as_view(), name="detector_run"),
    # Detections
    path("detections/", views.DetectionListView.as_view(), name="detection_list"),
    path("detections/<int:pk>/", views.DetectionDetailView.as_view(), name="detection_detail"),
    path("detections/<int:pk>/action/", views.detection_action_view, name="detection_action"),
    # Alert Templates
    path("templates/", views.AlertTemplateListView.as_view(), name="template_list"),
    path("templates/<int:pk>/", views.AlertTemplateDetailView.as_view(), name="template_detail"),
    # API Endpoints
    path("api/detectors/", api_views.DetectorListAPIView.as_view(), name="api_detector_list"),
    path("api/detectors/<int:detector_id>/", api_views.DetectorDetailAPIView.as_view(), name="api_detector_detail"),
    path("api/detectors/<int:detector_id>/run/", api_views.run_detector_api, name="api_detector_run"),
    path("api/detections/", api_views.DetectionListAPIView.as_view(), name="api_detection_list"),
    path("api/detections/<int:detection_id>/", api_views.DetectionDetailAPIView.as_view(), name="api_detection_detail"),
    path("api/detections/<int:detection_id>/action/", api_views.detection_action_api, name="api_detection_action"),
    path("api/stats/", api_views.SystemStatsAPIView.as_view(), name="api_system_stats"),
]
