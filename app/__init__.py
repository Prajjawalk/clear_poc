"""Django tests project package."""

import logging

logger = logging.getLogger(__name__)

from .celery import app as celery_app

logger.info(f"CELERY_INIT: Celery app imported: {celery_app}")
logger.info(f"CELERY_INIT: Celery broker: {celery_app.conf.broker_url}")
logger.info(f"CELERY_INIT: Celery app name: {celery_app.main}")

__all__ = ("celery_app",)
