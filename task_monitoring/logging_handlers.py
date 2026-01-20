"""Custom logging handlers for task monitoring."""

import logging
import threading
from typing import Optional

from django.db import transaction


class DatabaseTaskLogHandler(logging.Handler):
    """
    Custom logging handler that saves log records to the database.

    This handler is designed to capture logs from Celery tasks and associate them
    with specific task IDs for monitoring and debugging purposes.
    """

    def __init__(self, level=logging.NOTSET):
        """Initialize the handler."""
        super().__init__(level)
        self._current_task_id = threading.local()

    def set_task_id(self, task_id: str):
        """Set the current task ID for this thread."""
        self._current_task_id.value = task_id

    def clear_task_id(self):
        """Clear the current task ID for this thread."""
        if hasattr(self._current_task_id, 'value'):
            delattr(self._current_task_id, 'value')

    def get_task_id(self) -> Optional[str]:
        """Get the current task ID for this thread."""
        return getattr(self._current_task_id, 'value', None)

    def emit(self, record):
        """
        Emit a log record by saving it to the database.

        Args:
            record: LogRecord instance containing the log information
        """
        try:
            # Get the current task ID
            task_id = self.get_task_id()

            # If no task ID is set, try to extract from record context
            if not task_id:
                # Look for task_id in various places
                task_id = getattr(record, 'task_id', None)
                if not task_id and hasattr(record, 'extra'):
                    task_id = record.extra.get('task_id')
                # Try to get from Celery current task
                if not task_id:
                    try:
                        from celery import current_task
                        if current_task and hasattr(current_task, 'request'):
                            task_id = current_task.request.id
                    except (ImportError, AttributeError):
                        pass

            # Skip if we still don't have a task ID
            if not task_id:
                return

            # Extract extra data from the record
            extra_data = {}

            # Get standard fields that might be useful
            if hasattr(record, 'exc_info') and record.exc_info:
                extra_data['exception'] = self.format(record)

            if hasattr(record, 'stack_info') and record.stack_info:
                extra_data['stack_info'] = record.stack_info

            # Get any custom extra fields
            if hasattr(record, '__dict__'):
                for key, value in record.__dict__.items():
                    if key not in ['name', 'msg', 'args', 'levelname', 'levelno',
                                  'pathname', 'filename', 'module', 'exc_info',
                                  'exc_text', 'stack_info', 'lineno', 'funcName',
                                  'created', 'msecs', 'relativeCreated', 'thread',
                                  'threadName', 'processName', 'process', 'message']:
                        try:
                            # Only include JSON-serializable values
                            import json
                            json.dumps(value)
                            extra_data[key] = value
                        except (TypeError, ValueError):
                            extra_data[key] = str(value)

            # Create the TaskLog entry
            try:
                # Import here to avoid circular import issues
                from .models import TaskLog

                with transaction.atomic():
                    TaskLog.objects.create(
                        task_id=task_id,
                        level=record.levelno,
                        level_name=record.levelname,
                        message=self.format(record),
                        module=record.module if hasattr(record, 'module') else '',
                        function_name=record.funcName if hasattr(record, 'funcName') else '',
                        line_number=record.lineno if hasattr(record, 'lineno') else None,
                        thread=getattr(record, 'threadName', ''),
                        process=getattr(record, 'processName', ''),
                        extra_data=extra_data if extra_data else None,
                    )
            except Exception as e:
                # If database save fails, we don't want to break the logging
                # Silently continue (database might not be available)
                pass

        except Exception:
            # Handle any other exceptions to prevent breaking the logging system
            self.handleError(record)


# Global instance for easy access
database_log_handler = DatabaseTaskLogHandler()


def setup_task_logging(task_id: str):
    """
    Set up logging for a specific task.

    This should be called at the beginning of each Celery task to ensure
    all subsequent logs are associated with the correct task ID.

    Args:
        task_id: The Celery task ID to associate logs with
    """
    # Find all DatabaseTaskLogHandler instances in all loggers
    import logging
    import sys

    root_logger = logging.getLogger()

    # Collect all handlers from root logger and all configured loggers
    handlers_to_set = []

    # Check root logger
    for handler in root_logger.handlers:
        if isinstance(handler, DatabaseTaskLogHandler):
            handlers_to_set.append(handler)

    # Check all configured loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            if isinstance(handler, DatabaseTaskLogHandler):
                if handler not in handlers_to_set:
                    handlers_to_set.append(handler)

    # Set task ID on all found handlers
    for handler in handlers_to_set:
        handler.set_task_id(task_id)

    # Also set on global instance for backwards compatibility
    database_log_handler.set_task_id(task_id)


def cleanup_task_logging():
    """
    Clean up logging for the current task.

    This should be called at the end of each Celery task to prevent
    log leakage between tasks.
    """
    # Find all DatabaseTaskLogHandler instances in all loggers
    import logging
    root_logger = logging.getLogger()

    # Collect all handlers from root logger and all configured loggers
    handlers_to_clear = []

    # Check root logger
    for handler in root_logger.handlers:
        if isinstance(handler, DatabaseTaskLogHandler):
            handlers_to_clear.append(handler)

    # Check all configured loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            if isinstance(handler, DatabaseTaskLogHandler):
                if handler not in handlers_to_clear:
                    handlers_to_clear.append(handler)

    # Clear task ID on all found handlers
    for handler in handlers_to_clear:
        handler.clear_task_id()

    # Also clear global instance for backwards compatibility
    database_log_handler.clear_task_id()


class TaskLoggerContextManager:
    """
    Context manager for task logging setup and cleanup.

    Usage:
        with TaskLoggerContextManager(task_id):
            logger.info("This will be associated with the task")
    """

    def __init__(self, task_id: str):
        """Initialize with task ID."""
        self.task_id = task_id

    def __enter__(self):
        """Set up task logging."""
        setup_task_logging(self.task_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up task logging."""
        cleanup_task_logging()


def get_task_logger(name: str) -> logging.Logger:
    """
    Get a logger configured for task logging.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Add the database handler if not already present
    if database_log_handler not in logger.handlers:
        logger.addHandler(database_log_handler)

    return logger