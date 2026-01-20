"""App configuration for the main django app."""

from django.apps import AppConfig


class AppConfig(AppConfig):
    """Main application configuration."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'
    verbose_name = 'Main Application'
