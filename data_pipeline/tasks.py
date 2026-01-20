"""Celery tasks for data pipeline operations."""

import importlib
import logging
import uuid
from datetime import date
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from task_monitoring.models import TaskExecution, TaskType

from .models import Source, TaskStatistics, Variable

logger = logging.getLogger(__name__)


def create_task_execution(task_id: str, task_type_name: str, source_id: int = None, variable_id: int = None, arg1: int = None) -> TaskExecution:
    """Create a TaskExecution record for monitoring."""
    task_type, _ = TaskType.objects.get_or_create(name=task_type_name)

    # Use update_or_create to handle duplicate task_id cases (e.g., when running synchronously)
    task_execution, created = TaskExecution.objects.update_or_create(
        task_id=task_id, defaults={"task_type": task_type, "status": "started", "started_at": timezone.now(), "source_id": source_id, "variable_id": variable_id, "arg1": arg1}
    )
    return task_execution


def update_task_execution(task_execution: TaskExecution, status: str, result: dict[str, Any] = None, error_message: str = None):
    """Update task execution with result."""
    task_execution.status = status
    task_execution.completed_at = timezone.now()

    if result:
        task_execution.result = result

    if error_message:
        task_execution.error_message = error_message

    task_execution.save()


def get_source_class(source: Source):
    """Dynamically import and instantiate source class."""
    try:
        # Import the source class module
        module_path = f"data_pipeline.sources.{source.class_name.lower()}"
        module = importlib.import_module(module_path)
        source_class = getattr(module, source.class_name)
        return source_class(source)

    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import source class {source.class_name}: {str(e)}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def retrieve_data(self, source_id: int, variable_id: int = None, _skip_task_tracking: bool = False, **kwargs) -> dict[str, Any]:
    """Retrieve raw data from a source for a specific variable or all variables."""
    # Get the source object from the ID
    try:
        source = Source.objects.get(id=source_id)
    except Source.DoesNotExist:
        logger.error(f"Source with ID {source_id} not found")
        raise ValueError(f"Source with ID {source_id} not found")

    # Only create TaskExecution if not called from another task
    task_execution = None
    if not _skip_task_tracking:
        # Generate a unique task ID - use Celery's ID if available, otherwise create a unique one
        task_id = self.request.id if self.request.id else str(uuid.uuid4())
        task_execution = create_task_execution(task_id, "retrieval", source_id, variable_id, source_id)

    try:
        source_instance = get_source_class(source)

        if variable_id:
            # Retrieve data for specific variable
            variable = Variable.objects.get(id=variable_id, source=source)
            variables = [variable]
        else:
            # Retrieve data for all variables of this source
            variables = source.variables.all()

        results = {}
        total_success = 0
        total_variables = len(variables)

        # Check if source supports batch retrieval for all variables
        if not variable_id and hasattr(source_instance, 'get_all_variables'):
            # Use batch method for sources that support it (like ACLED)
            try:
                success = source_instance.get_all_variables(**kwargs)
                # Mark all variables as successful if batch call succeeded
                for variable in variables:
                    results[variable.code] = {"success": success, "variable_id": variable.id}
                    if success:
                        total_success += 1
            except Exception as e:
                logger.error(f"Failed to retrieve data for all variables: {str(e)}")
                # Mark all variables as failed if batch call failed
                for variable in variables:
                    results[variable.code] = {"success": False, "error": str(e), "variable_id": variable.id}
        else:
            # Use individual variable retrieval for other sources or single variables
            for variable in variables:
                try:
                    success = source_instance.get(variable, **kwargs)
                    results[variable.code] = {"success": success, "variable_id": variable.id}
                    if success:
                        total_success += 1

                except Exception as e:
                    logger.error(f"Failed to retrieve data for {variable.code}: {str(e)}")
                    results[variable.code] = {"success": False, "error": str(e), "variable_id": variable.id}

        result_data = {"source_id": source.id, "total_variables": total_variables, "successful_retrievals": total_success, "variables": results}

        status = "success" if total_success > 0 else "failure"

        # If all variables failed, extract error message for TaskExecution
        error_message = None
        if status == "failure" and total_success == 0:
            # Get error from first failed variable
            for var_code, var_result in results.items():
                if not var_result.get("success", True) and var_result.get("error"):
                    error_message = var_result["error"]
                    break

        # Only update task execution if tracking is enabled
        if task_execution:
            update_task_execution(task_execution, status, result_data, error_message)

        return result_data

    except Exception as e:
        logger.error(f"Data retrieval task failed: {str(e)}")
        if task_execution:
            update_task_execution(task_execution, "failure", error_message=str(e))

            # Only retry for network/API errors, not code errors
            if any(keyword in str(e).lower() for keyword in ["connection", "timeout", "network", "http", "api"]):
                raise self.retry(exc=e, countdown=60, max_retries=3)
            else:
                # Code error - don't retry
                raise e


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_data(self, source_id: int, variable_id: int = None, _skip_task_tracking: bool = False, **kwargs) -> dict[str, Any]:
    """Process raw data into standardized format."""
    # Get the source object from the ID
    try:
        source = Source.objects.get(id=source_id)
    except Source.DoesNotExist:
        logger.error(f"Source with ID {source_id} not found")
        raise ValueError(f"Source with ID {source_id} not found")

    # Only create TaskExecution if not called from another task
    task_execution = None
    if not _skip_task_tracking:
        # Generate a unique task ID - use Celery's ID if available, otherwise create a unique one
        task_id = self.request.id if self.request.id else str(uuid.uuid4())
        task_execution = create_task_execution(task_id, "processing", source_id, variable_id, source_id)

    try:
        source_instance = get_source_class(source)

        if variable_id:
            variables = [Variable.objects.get(id=variable_id, source=source)]
        else:
            variables = source.variables.all()

        results = {}
        total_success = 0
        total_variables = len(variables)

        # Check if source supports batch processing for all variables
        if not variable_id and hasattr(source_instance, 'process_all_variables'):
            # Use batch method for sources that support it (like ACLED)
            try:
                success = source_instance.process_all_variables(**kwargs)
                # Mark all variables as successful if batch call succeeded
                for variable in variables:
                    results[variable.code] = {"success": success, "variable_id": variable.id}
                    if success:
                        total_success += 1
            except Exception as e:
                logger.error(f"Failed to process data for all variables: {str(e)}")
                # Mark all variables as failed if batch call failed
                for variable in variables:
                    results[variable.code] = {"success": False, "error": str(e), "variable_id": variable.id}
        else:
            # Use individual variable processing for other sources or single variables
            for variable in variables:
                try:
                    success = source_instance.process(variable, **kwargs)
                    results[variable.code] = {"success": success, "variable_id": variable.id}
                    if success:
                        total_success += 1

                except Exception as e:
                    logger.error(f"Failed to process data for {variable.code}: {str(e)}")
                    results[variable.code] = {"success": False, "error": str(e), "variable_id": variable.id}

        # Send notification about unmatched locations if any processing was successful
        if total_success > 0:
            try:
                source_instance.notify_unmatched_locations_summary()
            except Exception as e:
                logger.warning(f"Failed to send unmatched locations notification: {str(e)}")

        result_data = {"source_id": source.id, "total_variables": total_variables, "successful_processing": total_success, "variables": results}

        status = "success" if total_success > 0 else "failure"

        # Only update task execution if tracking is enabled
        if task_execution:
            update_task_execution(task_execution, status, result_data)

        # Emit signals for successful processing to trigger detectors
        if total_success > 0:
            from .signals import data_processing_completed, variable_data_updated

            # Emit source-level signal
            data_processing_completed.send(
                sender=source.__class__,
                source=source,
                variables_processed=results,
                success_count=total_success
            )

            # Emit variable-level signals for successful variables
            for variable in variables:
                if results[variable.code]["success"]:
                    variable_data_updated.send(
                        sender=variable.__class__,
                        variable=variable,
                        source=source
                    )

        return result_data

    except Exception as e:
        logger.error(f"Data processing task failed: {str(e)}")
        if task_execution:
            update_task_execution(task_execution, "failure", error_message=str(e))

        # Only retry for network/API errors, not code errors
        if any(keyword in str(e).lower() for keyword in ["connection", "timeout", "network", "http", "api"]):
            raise self.retry(exc=e, countdown=60, max_retries=3)
        else:
            # Code error - don't retry
            raise e


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def aggregate_data(self, source_id: int, variable_id: int, target_period: str = None, target_adm_level: int = None, **kwargs) -> dict[str, Any]:
    """Aggregate processed data to different temporal/geographic levels."""
    # Generate a unique task ID - use Celery's ID if available, otherwise create a unique one
    task_id = self.request.id if self.request.id else str(uuid.uuid4())
    task_execution = create_task_execution(task_id, "aggregation", source_id, variable_id, variable_id)

    try:
        source = Source.objects.get(id=source_id)
        variable = Variable.objects.get(id=variable_id, source=source)
        source_instance = get_source_class(source)

        success = source_instance.aggregate(variable, target_period=target_period, target_adm_level=target_adm_level, **kwargs)

        result_data = {"source_id": source_id, "variable_id": variable_id, "target_period": target_period, "target_adm_level": target_adm_level, "success": success}

        status = "success" if success else "failure"
        update_task_execution(task_execution, status, result_data)

        return result_data

    except Exception as e:
        logger.error(f"Data aggregation task failed: {str(e)}")
        update_task_execution(task_execution, "failure", error_message=str(e))

        # Only retry for network/API errors, not code errors
        if any(keyword in str(e).lower() for keyword in ["connection", "timeout", "network", "http", "api"]):
            raise self.retry(exc=e, countdown=60, max_retries=3)
        else:
            # Code error - don't retry
            raise e


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def full_pipeline(self, source_id: int, variable_id: int = None, **kwargs) -> dict[str, Any]:
    """Run full data pipeline: retrieve, process, and optionally aggregate."""
    # Get the source object from the ID
    try:
        source = Source.objects.get(id=source_id)
    except Source.DoesNotExist:
        logger.error(f"Source with ID {source_id} not found")
        raise ValueError(f"Source with ID {source_id} not found")

    # Generate a unique task ID - use Celery's ID if available, otherwise create a unique one
    task_id = self.request.id if self.request.id else str(uuid.uuid4())
    task_execution = create_task_execution(task_id, "full_pipeline", source_id, variable_id, source_id)

    try:
        logger.info(f"Starting full pipeline for source_id={source_id}, variable_id={variable_id}")

        # Step 1: Retrieve data
        logger.info(f"Step 1: Starting data retrieval for source_id={source_id}")
        retrieve_result = retrieve_data(source_id, variable_id, _skip_task_tracking=True, **kwargs)
        logger.info(f"Step 1 completed: {retrieve_result}")

        if retrieve_result["successful_retrievals"] == 0:
            result_data = {"source_id": source.id, "pipeline_step": "retrieval", "success": False, "message": "No data retrieved"}
            logger.warning(f"No data retrieved for source_id={source_id}, variable_id={variable_id}")
            update_task_execution(task_execution, "failure", result_data)
            return result_data

        # Step 2: Process data
        logger.info(f"Step 2: Starting data processing for source_id={source_id}")
        process_result = process_data(source_id, variable_id, _skip_task_tracking=True, **kwargs)
        logger.info(f"Step 2 completed: {process_result}")

        if process_result["successful_processing"] == 0:
            result_data = {"source_id": source.id, "pipeline_step": "processing", "success": False, "message": "No data processed"}
            logger.warning(f"No data processed for source_id={source_id}, variable_id={variable_id}")
            update_task_execution(task_execution, "failure", result_data)
            return result_data

        # Step 3: Optional aggregation
        aggregation_results = []
        if kwargs.get("aggregate", False):
            target_period = kwargs.get("target_period")
            target_adm_level = kwargs.get("target_adm_level")

            if variable_id:
                variables = [Variable.objects.get(id=variable_id)]
            else:
                variables = source.variables.all()

            for variable in variables:
                if target_period or target_adm_level:
                    agg_result = aggregate_data(source.id, variable.id, target_period=target_period, target_adm_level=target_adm_level)
                    aggregation_results.append(agg_result)

        result_data = {
            "source_id": source.id,
            "variable_id": variable_id,
            "success": True,
            "retrieval_results": retrieve_result,
            "processing_results": process_result,
            "aggregation_results": aggregation_results,
        }

        update_task_execution(task_execution, "success", result_data)
        return result_data

    except Exception as e:
        import traceback

        logger.error(f"Full pipeline task failed: {str(e)}")
        logger.error(f"Full pipeline task traceback: {traceback.format_exc()}")
        update_task_execution(task_execution, "failure", error_message=str(e))

        # Only retry for network/API errors, not code errors
        if any(keyword in str(e).lower() for keyword in ["connection", "timeout", "network", "http", "api"]):
            raise self.retry(exc=e, countdown=300, max_retries=2)
        else:
            # Code error - don't retry
            raise e


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def retrieve_all_source_data(self, source_id: int, **kwargs) -> dict[str, Any]:
    """Retrieve raw data for ALL variables from a source in one optimized call."""
    try:
        source = Source.objects.get(id=source_id)
    except Source.DoesNotExist:
        logger.error(f"Source with ID {source_id} not found")
        raise ValueError(f"Source with ID {source_id} not found")

    task_id = self.request.id if self.request.id else str(uuid.uuid4())
    task_execution = create_task_execution(task_id, "source_retrieval", source_id, None, source_id)

    try:
        source_instance = get_source_class(source)
        variables = list(source.variables.all())

        logger.info(f"Starting data retrieval for {source.name} ({len(variables)} variables)")

        # Use the get_all_variables method
        success = source_instance.get_all_variables(**kwargs)

        result_data = {"source_id": source.id, "source_name": source.name, "total_variables": len(variables), "success": success, "method": "optimized_source_level"}

        status = "success" if success else "failure"
        update_task_execution(task_execution, status, result_data)

        logger.info(f"Source-level retrieval for {source.name}: {status}")
        return result_data

    except Exception as e:
        logger.error(f"Source-level retrieval task failed: {str(e)}")
        update_task_execution(task_execution, "failure", error_message=str(e))
        # Only retry for network/API errors, not code errors
        if any(keyword in str(e).lower() for keyword in ["connection", "timeout", "network", "http", "api"]):
            raise self.retry(exc=e, countdown=60, max_retries=3)
        else:
            # Code error - don't retry
            raise e


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_all_source_data(self, source_id: int, **kwargs) -> dict[str, Any]:
    """Process raw data for ALL variables from a source in one optimized call."""
    try:
        source = Source.objects.get(id=source_id)
    except Source.DoesNotExist:
        logger.error(f"Source with ID {source_id} not found")
        raise ValueError(f"Source with ID {source_id} not found")

    task_id = self.request.id if self.request.id else str(uuid.uuid4())
    task_execution = create_task_execution(task_id, "source_processing", source_id, None, source_id)

    try:
        source_instance = get_source_class(source)
        variables = list(source.variables.all())

        logger.info(f"Starting optimized processing for {source.name} ({len(variables)} variables)")

        # Use the optimized process_all_variables method
        success = source_instance.process_all_variables(**kwargs)

        result_data = {"source_id": source.id, "source_name": source.name, "total_variables": len(variables), "success": success, "method": "optimized_source_level"}

        status = "success" if success else "failure"
        update_task_execution(task_execution, status, result_data)

        # Emit signals for successful processing to trigger detectors
        if success:
            from .signals import data_processing_completed, variable_data_updated

            # Create results dict for signal compatibility
            signal_results = {var.code: {"success": True, "variable_id": var.id} for var in variables}

            # Emit source-level signal
            data_processing_completed.send(
                sender=source.__class__,
                source=source,
                variables_processed=signal_results,
                success_count=len(variables)
            )

            # Emit variable-level signals for all variables
            for variable in variables:
                variable_data_updated.send(
                    sender=variable.__class__,
                    variable=variable,
                    source=source
                )

        logger.info(f"Source-level processing for {source.name}: {status}")
        return result_data

    except Exception as e:
        logger.error(f"Source-level processing task failed: {str(e)}")
        update_task_execution(task_execution, "failure", error_message=str(e))
        # Only retry for network/API errors, not code errors
        if any(keyword in str(e).lower() for keyword in ["connection", "timeout", "network", "http", "api"]):
            raise self.retry(exc=e, countdown=60, max_retries=3)
        else:
            # Code error - don't retry
            raise e


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def full_source_pipeline(self, source_id: int, **kwargs) -> dict[str, Any]:
    """Run complete optimized pipeline for all variables in a source."""
    logger.info(f"FULL_SOURCE_PIPELINE: Task started for source_id={source_id}, task_id={self.request.id}")
    try:
        source = Source.objects.get(id=source_id)
    except Source.DoesNotExist:
        logger.error(f"Source with ID {source_id} not found")
        raise ValueError(f"Source with ID {source_id} not found")

    task_id = self.request.id if self.request.id else str(uuid.uuid4())
    task_execution = create_task_execution(task_id, "full_source_pipeline", source_id, None, source_id)

    try:
        source_instance = get_source_class(source)
        variables = list(source.variables.all())

        logger.info(f"Starting full optimized pipeline for {source.name} ({len(variables)} variables)")

        # Step 1: Retrieve all data
        retrieve_success = source_instance.get_all_variables(**kwargs)
        if not retrieve_success:
            raise Exception("Data retrieval failed")

        # Step 2: Process all data
        process_success = source_instance.process_all_variables(**kwargs)
        if not process_success:
            raise Exception("Data processing failed")

        result_data = {
            "source_id": source.id,
            "source_name": source.name,
            "total_variables": len(variables),
            "retrieve_success": retrieve_success,
            "process_success": process_success,
            "overall_success": retrieve_success and process_success,
            "method": "optimized_full_pipeline",
        }

        status = "success" if (retrieve_success and process_success) else "failure"
        update_task_execution(task_execution, status, result_data)

        # Emit signals for successful processing to trigger detectors
        if retrieve_success and process_success:
            from .signals import data_processing_completed, variable_data_updated

            # Create results dict for signal compatibility
            signal_results = {var.code: {"success": True, "variable_id": var.id} for var in variables}

            # Emit source-level signal
            data_processing_completed.send(
                sender=source.__class__,
                source=source,
                variables_processed=signal_results,
                success_count=len(variables)
            )

            # Emit variable-level signals for all variables
            for variable in variables:
                variable_data_updated.send(
                    sender=variable.__class__,
                    variable=variable,
                    source=source
                )

        logger.info(f"Full source pipeline for {source.name}: {status}")
        return result_data

    except Exception as e:
        logger.error(f"Full source pipeline task failed: {str(e)}")
        update_task_execution(task_execution, "failure", error_message=str(e))
        # Only retry for network/API errors, not code errors
        if any(keyword in str(e).lower() for keyword in ["connection", "timeout", "network", "http", "api"]):
            raise self.retry(exc=e, countdown=60, max_retries=3)
        else:
            # Code error - don't retry
            raise e


@shared_task
def update_task_statistics():
    """Update daily task execution statistics."""
    today = date.today()

    # Get all task executions for today
    executions = TaskExecution.objects.filter(created_at__date=today).select_related("task_type")

    # Count tasks by type
    task_counts = {"check_updates_count": 0, "download_data_count": 0, "process_data_count": 0, "full_pipeline_count": 0, "reprocess_data_count": 0}

    success_count = 0
    failure_count = 0
    retry_count = 0
    durations = []

    for execution in executions:
        # Count by task type
        task_type = execution.task_type.name.lower()
        if "retrieval" in task_type or "download" in task_type:
            task_counts["download_data_count"] += 1
        elif "processing" in task_type or "process" in task_type:
            task_counts["process_data_count"] += 1
        elif "pipeline" in task_type:
            task_counts["full_pipeline_count"] += 1
        elif "reprocess" in task_type:
            task_counts["reprocess_data_count"] += 1
        elif "check" in task_type or "update" in task_type:
            task_counts["check_updates_count"] += 1

        # Count by status
        if execution.status == "success":
            success_count += 1
        elif execution.status == "failure":
            failure_count += 1
        elif execution.status == "retry":
            retry_count += 1

        # Collect duration
        if execution.duration_seconds:
            durations.append(execution.duration_seconds)

    # Calculate averages
    avg_duration = sum(durations) / len(durations) if durations else None
    max_duration = max(durations) if durations else None

    # Update or create statistics record
    with transaction.atomic():
        stats, _ = TaskStatistics.objects.update_or_create(
            date=today,
            defaults={
                **task_counts,
                "success_count": success_count,
                "failure_count": failure_count,
                "retry_count": retry_count,
                "avg_duration_seconds": avg_duration,
                "max_duration_seconds": max_duration,
            },
        )

    logger.info(f"Updated task statistics for {today}: {stats.total_tasks} total tasks")
    return {"date": today.isoformat(), "total_tasks": stats.total_tasks, "success_rate": stats.success_rate}


@shared_task
def cleanup_old_task_executions(days_to_keep: int = 30):
    """Clean up old task execution records."""
    cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)

    deleted_count, _ = TaskExecution.objects.filter(created_at__lt=cutoff_date).delete()

    logger.info(f"Cleaned up {deleted_count} task execution records older than {days_to_keep} days")
    return {"deleted_count": deleted_count, "cutoff_date": cutoff_date.isoformat()}
