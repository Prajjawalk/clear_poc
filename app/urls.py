"""
URL configuration for django tests project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))

"""

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from .settings import ENV, TESTING
from .views import APIDocumentationView, HealthcheckView, HomeView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/login/", auth_views.LoginView.as_view(), name="login"),
    path("auth/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("healthcheck/", HealthcheckView.as_view(), name="healthcheck"),
    path("api/", APIDocumentationView.as_view(), name="api_documentation"),
    path("translation/", include("translation.urls")),
    path("location/", include("location.urls")),
    path("tasks/", include("task_monitoring.urls")),
    path("pipeline/", include("data_pipeline.urls")),
    path("alerts/", include("alerts.urls")),
    path("alert_framework/", include("alert_framework.urls")),
    path("llm/", include("llm_service.urls")),
    path("users/", include("users.urls")),
    path("notifications/", include("notifications.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("", HomeView.as_view(), name="home"),
]

if ENV == "DEV" and not TESTING:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()

# Serve static and media files during development and testing
if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    # This serves files from STATICFILES_DIRS using the staticfiles app
    urlpatterns += staticfiles_urlpatterns()

    # Serve media files during development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
