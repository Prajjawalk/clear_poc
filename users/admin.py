"""Django admin configuration for user management."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    """Inline admin for UserProfile."""

    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'

    fieldsets = [
        ('Email Preferences', {
            'fields': ['email_notifications_enabled', 'email_verified', 'email_verification_sent_at']
        }),
        ('User Preferences', {
            'fields': ['preferred_language', 'timezone']
        }),
        ('Security', {
            'fields': ['last_login_ip'],
            'classes': ['collapse']
        }),
        ('Metadata', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    readonly_fields = ['created_at', 'updated_at', 'email_verification_sent_at']


class CustomUserAdmin(UserAdmin):
    """Extended UserAdmin with profile information."""

    inlines = (UserProfileInline,)
    list_display = UserAdmin.list_display + ('get_email_enabled', 'get_email_verified', 'get_last_login_ip')
    list_filter = UserAdmin.list_filter + ('profile__email_notifications_enabled', 'profile__email_verified')

    def get_email_enabled(self, obj):
        """Show if email notifications are enabled."""
        return obj.profile.email_notifications_enabled if hasattr(obj, 'profile') else False
    get_email_enabled.boolean = True
    get_email_enabled.short_description = 'Email Notifications'

    def get_email_verified(self, obj):
        """Show if email is verified."""
        return obj.profile.email_verified if hasattr(obj, 'profile') else False
    get_email_verified.boolean = True
    get_email_verified.short_description = 'Email Verified'

    def get_last_login_ip(self, obj):
        """Show last login IP."""
        return obj.profile.last_login_ip if hasattr(obj, 'profile') else None
    get_last_login_ip.short_description = 'Last IP'


# Re-register UserAdmin with our custom version
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Standalone admin for UserProfile."""

    list_display = ['user', 'email_notifications_enabled', 'email_verified', 'preferred_language', 'created_at']
    list_filter = ['email_notifications_enabled', 'email_verified', 'preferred_language', 'timezone']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at', 'email_verification_sent_at']

    fieldsets = [
        ('User', {
            'fields': ['user']
        }),
        ('Email Preferences', {
            'fields': [
                'email_notifications_enabled',
                'email_verified',
                'email_verification_token',
                'email_verification_sent_at'
            ]
        }),
        ('User Preferences', {
            'fields': ['preferred_language', 'timezone']
        }),
        ('Security', {
            'fields': ['last_login_ip']
        }),
        ('Metadata', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related('user')

    actions = ['enable_email_notifications', 'disable_email_notifications', 'mark_email_verified']

    def enable_email_notifications(self, request, queryset):
        """Bulk enable email notifications."""
        count = queryset.update(email_notifications_enabled=True)
        self.message_user(request, f'Enabled email notifications for {count} users.')
    enable_email_notifications.short_description = 'Enable email notifications'

    def disable_email_notifications(self, request, queryset):
        """Bulk disable email notifications."""
        count = queryset.update(email_notifications_enabled=False)
        self.message_user(request, f'Disabled email notifications for {count} users.')
    disable_email_notifications.short_description = 'Disable email notifications'

    def mark_email_verified(self, request, queryset):
        """Bulk mark emails as verified."""
        count = queryset.update(email_verified=True)
        self.message_user(request, f'Marked {count} emails as verified.')
    mark_email_verified.short_description = 'Mark email as verified'