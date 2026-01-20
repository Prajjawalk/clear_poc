"""Alerts app configuration."""

from django.apps import AppConfig


class AlertsConfig(AppConfig):
    """Configuration for alerts Django application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "alerts"
    verbose_name = "Alert System"

    def ready(self):
        """Initialize app and import signal handlers."""
        # Set up cache invalidation signals
        from django.db.models.signals import m2m_changed, post_delete, post_save

        import alerts.signals  # noqa: F401
        from alerts.cache import cache_invalidation_signal_handler
        from alerts.models import Alert, ShockType, Subscription, UserAlert

        # Connect cache invalidation signals
        post_save.connect(cache_invalidation_signal_handler, sender=Alert)
        post_delete.connect(cache_invalidation_signal_handler, sender=Alert)
        m2m_changed.connect(cache_invalidation_signal_handler, sender=Alert.locations.through)

        post_save.connect(cache_invalidation_signal_handler, sender=UserAlert)
        post_delete.connect(cache_invalidation_signal_handler, sender=UserAlert)

        post_save.connect(cache_invalidation_signal_handler, sender=ShockType)
        post_delete.connect(cache_invalidation_signal_handler, sender=ShockType)

        post_save.connect(cache_invalidation_signal_handler, sender=Subscription)
        post_delete.connect(cache_invalidation_signal_handler, sender=Subscription)
