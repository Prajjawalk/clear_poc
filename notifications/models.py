"""Internal notification system models."""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class InternalNotification(models.Model):
    """Internal notification for in-app delivery."""

    NOTIFICATION_TYPES = [
        ('alert', 'New Alert'),
        ('system', 'System Message'),
        ('update', 'Alert Update'),
        ('feedback', 'Feedback Response'),
        ('subscription', 'Subscription Update'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="User who will receive this notification"
    )

    type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default='alert',
        help_text="Type of notification"
    )

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_LEVELS,
        default='normal',
        help_text="Priority level of the notification"
    )

    title = models.CharField(
        max_length=255,
        help_text="Notification title"
    )

    message = models.TextField(
        help_text="Notification message content"
    )

    # Related objects
    alert = models.ForeignKey(
        'alerts.Alert',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text="Related alert if applicable"
    )

    # Tracking
    read = models.BooleanField(
        default=False,
        help_text="Whether the notification has been read"
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was read"
    )

    # Action URL
    action_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL for action button if applicable"
    )
    action_text = models.CharField(
        max_length=100,
        blank=True,
        help_text="Text for action button if applicable"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this notification expires and can be auto-deleted"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'read']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['type', 'priority']),
        ]
        verbose_name = 'Internal Notification'
        verbose_name_plural = 'Internal Notifications'

    def __str__(self):
        return f"{self.user.username}: {self.title}"

    def mark_as_read(self):
        """Mark notification as read."""
        if not self.read:
            self.read = True
            self.read_at = timezone.now()
            self.save(update_fields=['read', 'read_at'])

    @property
    def is_expired(self):
        """Check if notification has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    @classmethod
    def unread_count(cls, user):
        """Get count of unread notifications for a user."""
        return cls.objects.filter(user=user, read=False).count()

    @classmethod
    def create_alert_notification(cls, user, alert):
        """Create a notification for a new alert."""
        return cls.objects.create(
            user=user,
            type='alert',
            priority='high' if alert.severity >= 4 else 'normal',
            title=f"New Alert: {alert.title}",
            message=f"A new {alert.shock_type.name} alert has been issued for your subscribed locations.",
            alert=alert,
            action_url=f"/alerts/alert/{alert.id}/",
            action_text="View Alert"
        )


class NotificationPreference(models.Model):
    """User preferences for notification channels and types."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )

    # Channel preferences
    internal_enabled = models.BooleanField(
        default=True,
        help_text="Receive in-app notifications"
    )

    # Type preferences
    alert_notifications = models.BooleanField(
        default=True,
        help_text="Receive notifications for new alerts"
    )
    system_notifications = models.BooleanField(
        default=True,
        help_text="Receive system notifications"
    )
    update_notifications = models.BooleanField(
        default=True,
        help_text="Receive alert update notifications"
    )
    feedback_notifications = models.BooleanField(
        default=True,
        help_text="Receive feedback response notifications"
    )

    # Display preferences
    show_desktop_notifications = models.BooleanField(
        default=False,
        help_text="Show browser desktop notifications"
    )
    play_sound = models.BooleanField(
        default=False,
        help_text="Play sound for urgent notifications"
    )

    # Quiet hours
    quiet_hours_enabled = models.BooleanField(
        default=False,
        help_text="Enable quiet hours for non-urgent notifications"
    )
    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        help_text="Start time for quiet hours"
    )
    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        help_text="End time for quiet hours"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'

    def __str__(self):
        return f"{self.user.username} Notification Preferences"

    def should_receive_notification(self, notification_type):
        """Check if user should receive a specific notification type."""
        if not self.internal_enabled:
            return False

        type_map = {
            'alert': self.alert_notifications,
            'system': self.system_notifications,
            'update': self.update_notifications,
            'feedback': self.feedback_notifications,
        }

        return type_map.get(notification_type, True)