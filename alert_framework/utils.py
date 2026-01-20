"""Utility functions for alert framework."""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def run_task_with_fallback(task_func: Callable, *args, task_name: str = "Task", **kwargs) -> tuple[Any, str]:
    """Run a Celery task asynchronously if workers are available, else synchronously.

    This utility function checks if Celery workers are available and runs the task
    accordingly. It provides a clean fallback mechanism for environments where
    Celery might not be running (e.g., during testing or development).

    Args:
        task_func: The Celery task function (should have .delay() method for async)
        *args: Positional arguments to pass to the task
        task_name: Name of the task for logging purposes
        **kwargs: Keyword arguments to pass to the task

    Returns:
        Tuple of (task_result, execution_mode)
        - task_result: The result of the task execution
        - execution_mode: 'async', 'sync', or 'sync-error' indicating how it was run
    """
    try:
        from celery import current_app

        try:
            # Check if Celery workers are available
            inspect = current_app.control.inspect()
            active_workers = inspect.active()

            if active_workers:
                # Celery workers are running, use async
                task_result = task_func.delay(*args, **kwargs)
                task_id = task_result.id if hasattr(task_result, "id") else "async"
                logger.info(f"{task_name} triggered asynchronously (task_id: {task_id})")
                return task_result, "async"
            else:
                # No workers available, run synchronously
                logger.info(f"Running {task_name} synchronously (no Celery workers)")
                task_result = task_func(*args, **kwargs)
                return task_result, "sync"
        except Exception as e:
            # Celery inspection failed, run synchronously
            logger.info(f"Running {task_name} synchronously (Celery inspection failed: {e})")
            task_result = task_func(*args, **kwargs)
            return task_result, "sync-error"

    except ImportError:
        # Celery not available, run synchronously
        logger.warning(f"Running {task_name} synchronously (Celery not available)")
        task_result = task_func(*args, **kwargs)
        return task_result, "sync"


def parse_detector_class_name(class_name: str) -> str:
    """Extract the detector class name from a full path.

    Args:
        class_name: Full class path or class name

    Returns:
        The class name portion
    """
    if not class_name:
        return "Unknown"
    return class_name.split(".")[-1]


def calculate_time_ago(time_delta) -> str:
    """Convert a timedelta to human-readable "time ago" string.

    Args:
        time_delta: datetime.timedelta object

    Returns:
        Human-readable string like "2 hours ago" or "3 days ago"
    """
    if time_delta.days > 0:
        if time_delta.days == 1:
            return "1 day ago"
        return f"{time_delta.days} days ago"
    elif time_delta.seconds >= 3600:
        hours = time_delta.seconds // 3600
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"
    elif time_delta.seconds >= 60:
        minutes = time_delta.seconds // 60
        if minutes == 1:
            return "1 minute ago"
        return f"{minutes} minutes ago"
    else:
        return "Just now"


def parse_date_filter(date_string: str) -> Any | None:
    """Parse ISO date string with timezone handling.

    Args:
        date_string: ISO format date string

    Returns:
        Parsed datetime object or None if parsing fails
    """
    from datetime import datetime

    if not date_string:
        return None

    try:
        # Handle ISO format with Z timezone
        cleaned = date_string.replace("Z", "+00:00")
        # Handle space-separated timezone format (e.g., "2025-09-23T15:08:39.695109 00:00")
        if " " in cleaned and not cleaned.endswith("+00:00"):
            cleaned = cleaned.replace(" ", "+")
        return datetime.fromisoformat(cleaned)
    except (ValueError, AttributeError):
        logger.warning(f"Failed to parse date: {date_string}")
        return None


def build_detection_filters(request_params: dict) -> dict:
    """Build queryset filters from request parameters.

    Args:
        request_params: Dictionary of request parameters

    Returns:
        Dictionary of filters to apply to queryset
    """
    filters = {}

    # Detector filter
    if detector_id := request_params.get("detector"):
        filters["detector_id"] = detector_id

    # Status filter
    if status := request_params.get("status"):
        filters["status"] = status

    # Shock type filter
    if shock_type := request_params.get("shock_type"):
        filters["shock_type_id"] = shock_type

    # Date range filters
    if start_date := parse_date_filter(request_params.get("start_date")):
        filters["detection_timestamp__gte"] = start_date

    if end_date := parse_date_filter(request_params.get("end_date")):
        filters["detection_timestamp__lte"] = end_date

    # Confidence threshold
    if min_confidence := request_params.get("min_confidence"):
        try:
            threshold = float(min_confidence)
            filters["confidence_score__gte"] = threshold
        except ValueError:
            pass

    return filters


def validate_action_request(request_method: str, required_fields: list, request_data: dict) -> dict | None:
    """Validate an action request has required method and fields.

    Args:
        request_method: HTTP method of the request
        required_fields: List of required field names
        request_data: Request data dictionary

    Returns:
        Error dict if validation fails, None if valid
    """
    if request_method != "POST":
        return {"error": "POST method required", "status": 405}

    for field in required_fields:
        if field not in request_data:
            return {"error": f"{field} parameter required", "status": 400}

    return None
