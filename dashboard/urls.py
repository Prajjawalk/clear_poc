"""URL configuration for dashboard app."""

from django.urls import path

from .views import DashboardMapView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardMapView.as_view(), name="dashboard"),
]
