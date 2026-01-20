"""AppConfig for the data_pipeline app."""

from django.apps import AppConfig


class DataPipelineConfig(AppConfig):
    """Configuration for the data_pipeline app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "data_pipeline"
