"""Celery configuration for the NRC EWAS application."""

import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings.core")

app = Celery("nrc_ewas")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Configure task routes
app.conf.task_routes = {
    # Data pipeline tasks
    "data_pipeline.tasks.retrieve_data": {"queue": "data_retrieval"},
    "data_pipeline.tasks.process_data": {"queue": "data_processing"},
    "data_pipeline.tasks.aggregate_data": {"queue": "data_aggregation"},
    "data_pipeline.tasks.full_pipeline": {"queue": "pipeline"},
    "data_pipeline.tasks.full_source_pipeline": {"queue": "pipeline"},
    "data_pipeline.tasks.retrieve_all_source_data": {"queue": "data_retrieval"},
    # Location matching tasks
    "location.tasks.compute_potential_matches": {"queue": "data_processing"},
    "location.tasks.recompute_all_potential_matches": {"queue": "data_processing"},
}

# Configure periodic tasks
app.conf.beat_schedule = {
    "daily-task-statistics": {
        "task": "data_pipeline.tasks.update_task_statistics",
        "schedule": 86400.0,  # 24 hours in seconds
    },
}

app.conf.timezone = "UTC"


# Configure Django logging when worker process starts
from celery.signals import worker_process_init, task_prerun, task_postrun


@worker_process_init.connect
def configure_django_logging(**kwargs):
    """Configure Django logging when each worker process initializes.

    This runs in each forked worker process, not just the main process.
    """
    import logging.config

    # Import the logging configuration directly
    from app.settings.logging import LOGGING

    # Configure logging for this worker process
    logging.config.dictConfig(LOGGING)


# Set up task logging signals
from task_monitoring.logging_handlers import setup_task_logging, cleanup_task_logging


@task_prerun.connect
def setup_logging_on_task_start(sender=None, task_id=None, **kwargs):
    """Set up database logging when a task starts."""
    if task_id:
        setup_task_logging(task_id)


@task_postrun.connect
def cleanup_logging_on_task_end(sender=None, task_id=None, **kwargs):
    """Clean up database logging when a task ends."""
    if task_id:
        cleanup_task_logging()


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f"Request: {self.request!r}")
