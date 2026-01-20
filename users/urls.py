"""URL patterns for user management."""

from django.urls import path

from . import views

app_name = 'users'

urlpatterns = [
    # User profile and self-service
    path('', views.profile_view, name='profile'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.UserProfileUpdateView.as_view(), name='profile_edit'),
    path('change-password/', views.change_password, name='change_password'),
    path('notification-preferences/', views.notification_preferences, name='notification_preferences'),

    # Email verification
    path('request-verification/', views.request_email_verification, name='request_email_verification'),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),

    # Admin views (staff only)
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/', views.AdminUserListView.as_view(), name='admin_user_list'),
    path('admin/users/create/', views.AdminUserCreateView.as_view(), name='admin_user_create'),
    path('admin/bulk-action/', views.admin_bulk_action, name='admin_bulk_action'),

    # API endpoints
    path('api/toggle-email-notifications/', views.api_toggle_email_notifications, name='api_toggle_email_notifications'),
]