from django.apps import AppConfig


class AlertFrameworkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alert_framework"

    def ready(self):
        """Initialize app and connect signal handlers."""
        from .signal_handlers import connect_signal_handlers

        connect_signal_handlers()
