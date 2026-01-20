"""Django admin configuration for notification models."""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import InternalNotification, NotificationPreference


@admin.register(InternalNotification)
class InternalNotificationAdmin(admin.ModelAdmin):
    """Admin interface for internal notifications."""

    list_display = [
        'user',
        'title_short',
        'type',
        'priority',
        'read',
        'created_at',
        'get_alert_link'
    ]
    list_filter = [
        'type',
        'priority',
        'read',
        'created_at',
        'expires_at'
    ]
    search_fields = [
        'user__username',
        'user__email',
        'title',
        'message',
        'alert__title'
    ]
    readonly_fields = [
        'created_at',
        'read_at',
        'is_expired'
    ]
    date_hierarchy = 'created_at'

    fieldsets = [
        ('Notification Details', {
            'fields': [
                'user',
                'type',
                'priority',
                'title',
                'message'
            ]
        }),
        ('Related Objects', {
            'fields': ['alert']
        }),
        ('Action', {
            'fields': [
                'action_url',
                'action_text'
            ]
        }),
        ('Status', {
            'fields': [
                'read',
                'read_at',
                'expires_at',
                'is_expired'
            ]
        }),
        ('Metadata', {
            'fields': ['created_at'],
            'classes': ['collapse']
        }),
    ]

    actions = [
        'mark_as_read',
        'mark_as_unread',
        'delete_expired'
    ]

    def title_short(self, obj):
        """Return truncated title for list display."""
        return obj.title[:50] + '...' if len(obj.title) > 50 else obj.title
    title_short.short_description = 'Title'

    def get_alert_link(self, obj):
        """Create link to related alert if exists."""
        if obj.alert:
            return format_html(
                '<a href="/admin/alerts/alert/{}/change/">Alert #{}</a>',
                obj.alert.id,
                obj.alert.id
            )
        return '-'
    get_alert_link.short_description = 'Alert'

    def mark_as_read(self, request, queryset):
        """Bulk mark notifications as read."""
        count = 0
        for notification in queryset:
            if not notification.read:
                notification.mark_as_read()
                count += 1
        self.message_user(request, f'Marked {count} notifications as read.')
    mark_as_read.short_description = 'Mark selected notifications as read'

    def mark_as_unread(self, request, queryset):
        """Bulk mark notifications as unread."""
        count = queryset.update(read=False, read_at=None)
        self.message_user(request, f'Marked {count} notifications as unread.')
    mark_as_unread.short_description = 'Mark selected notifications as unread'

    def delete_expired(self, request, queryset):
        """Delete expired notifications."""
        expired = queryset.filter(expires_at__lt=timezone.now())
        count = expired.count()
        expired.delete()
        self.message_user(request, f'Deleted {count} expired notifications.')
    delete_expired.short_description = 'Delete expired notifications'

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related('user', 'alert')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Admin interface for notification preferences."""

    list_display = [
        'user',
        'internal_enabled',
        'alert_notifications',
        'system_notifications',
        'quiet_hours_enabled',
        'updated_at'
    ]
    list_filter = [
        'internal_enabled',
        'alert_notifications',
        'system_notifications',
        'quiet_hours_enabled',
        'show_desktop_notifications',
        'play_sound'
    ]
    search_fields = [
        'user__username',
        'user__email',
        'user__first_name',
        'user__last_name'
    ]
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = [
        ('User', {
            'fields': ['user']
        }),
        ('Channel Preferences', {
            'fields': ['internal_enabled']
        }),
        ('Notification Types', {
            'fields': [
                'alert_notifications',
                'system_notifications',
                'update_notifications',
                'feedback_notifications'
            ]
        }),
        ('Display Options', {
            'fields': [
                'show_desktop_notifications',
                'play_sound'
            ]
        }),
        ('Quiet Hours', {
            'fields': [
                'quiet_hours_enabled',
                'quiet_hours_start',
                'quiet_hours_end'
            ]
        }),
        ('Metadata', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related('user')

    actions = [
        'enable_all_notifications',
        'disable_all_notifications',
        'reset_to_defaults'
    ]

    def enable_all_notifications(self, request, queryset):
        """Enable all notification types."""
        count = queryset.update(
            internal_enabled=True,
            alert_notifications=True,
            system_notifications=True,
            update_notifications=True,
            feedback_notifications=True
        )
        self.message_user(request, f'Enabled all notifications for {count} users.')
    enable_all_notifications.short_description = 'Enable all notifications'

    def disable_all_notifications(self, request, queryset):
        """Disable all notification types."""
        count = queryset.update(
            internal_enabled=False,
            alert_notifications=False,
            system_notifications=False,
            update_notifications=False,
            feedback_notifications=False
        )
        self.message_user(request, f'Disabled all notifications for {count} users.')
    disable_all_notifications.short_description = 'Disable all notifications'

    def reset_to_defaults(self, request, queryset):
        """Reset preferences to default values."""
        count = queryset.update(
            internal_enabled=True,
            alert_notifications=True,
            system_notifications=True,
            update_notifications=True,
            feedback_notifications=True,
            show_desktop_notifications=False,
            play_sound=False,
            quiet_hours_enabled=False
        )
        self.message_user(request, f'Reset preferences to defaults for {count} users.')
    reset_to_defaults.short_description = 'Reset to default preferences'