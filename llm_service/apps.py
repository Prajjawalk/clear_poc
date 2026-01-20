"""LLM Service Django app configuration."""

from django.apps import AppConfig


class LlmServiceConfig(AppConfig):
    """Configuration for the LLM service application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "llm_service"
    verbose_name = "LLM Query Service"

    def ready(self):
        """Initialize the LLM service when Django starts."""
        # Import signal handlers if needed
        pass