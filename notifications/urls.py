"""URL patterns for notifications app."""

from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    # Notification center and list views
    path('', views.notification_center, name='center'),
    path('list/', views.NotificationListView.as_view(), name='list'),

    # AJAX endpoints for notification management
    path('api/count/', views.api_notification_count, name='api_count'),
    path('api/recent/', views.api_recent_notifications, name='api_recent'),
    path('api/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark_read'),
    path('api/mark-unread/<int:notification_id>/', views.mark_notification_unread, name='mark_unread'),
    path('api/mark-all-read/', views.mark_all_read, name='mark_all_read'),
]