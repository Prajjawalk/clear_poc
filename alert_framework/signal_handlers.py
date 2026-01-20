"""Signal handlers for alert framework to automatically trigger detectors."""

import logging
from datetime import timedelta

from django.utils import timezone

from .utils import run_task_with_fallback

logger = logging.getLogger(__name__)


def trigger_detectors_for_source(sender, source, variables_processed, success_count, **kwargs):
    """Trigger all active detectors when source data is processed.

    Args:
        sender: Source class that sent the signal
        source: Source instance that completed processing
        variables_processed: Dict of variable processing results
        success_count: Number of successfully processed variables
        **kwargs: Additional signal data
    """
    logger.info(f"Data processing completed for source '{source.name}' ({success_count} variables processed), triggering detectors...")

    try:
        from .models import Detector
        from .tasks import run_detector

        # Find detectors that should run for this source
        # Look for detectors that either:
        # 1. Have the source name in their configuration
        # 2. Are configured to monitor all sources (have auto_trigger_on_data=True)
        active_detectors = Detector.objects.filter(active=True)

        triggered_detectors = []

        for detector in active_detectors:
            should_trigger = False

            # Check if detector configuration mentions this source
            config = detector.configuration or {}

            # Check if source name is explicitly mentioned
            monitored_sources = config.get("monitored_sources", [])
            if source.name in monitored_sources:
                should_trigger = True

            # Check if detector has test_source_name matching this source (for test detector)
            test_source_name = config.get("test_source_name")
            if test_source_name == source.name:
                should_trigger = True

            # Check if detector is configured to auto-trigger on any data
            if config.get("auto_trigger_on_data", False):
                should_trigger = True

            if should_trigger:
                # Trigger detector asynchronously with recent time window
                end_time = timezone.now()
                start_time = end_time - timedelta(hours=1)  # Look at last hour of data

                try:
                    # Use utility function for Celery fallback logic
                    task_result, execution_mode = run_task_with_fallback(
                        run_detector,
                        detector.id,
                        start_date=start_time.isoformat(),
                        end_date=end_time.isoformat(),
                        triggered_by_source=source.id,
                        task_name=f"Detector '{detector.name}'",
                    )

                    task_id = task_result.id if hasattr(task_result, "id") else execution_mode
                    triggered_detectors.append({"detector_id": detector.id, "detector_name": detector.name, "task_id": task_id})

                except Exception as e:
                    logger.error(f"Failed to trigger detector '{detector.name}' for source '{source.name}': {str(e)}")

        logger.info(f"Triggered {len(triggered_detectors)} detectors for source '{source.name}': {[d['detector_name'] for d in triggered_detectors]}")

    except Exception as e:
        logger.error(f"Error in detector triggering for source '{source.name}': {str(e)}")


def trigger_variable_specific_detectors(sender, variable, source, **kwargs):
    """Trigger detectors that monitor specific variables.

    Args:
        sender: Variable class that sent the signal
        variable: Variable instance that was updated
        source: Source instance that owns the variable
        **kwargs: Additional signal data
    """
    logger.debug(f"Variable '{variable.code}' from source '{source.name}' updated, checking for variable-specific detectors...")

    try:
        from .models import Detector
        from .tasks import run_detector

        # Find detectors configured for this specific variable
        active_detectors = Detector.objects.filter(active=True)

        triggered_detectors = []

        for detector in active_detectors:
            config = detector.configuration or {}

            # Check if this variable is explicitly monitored
            monitored_variables = config.get("monitored_variables", [])

            if variable.code in monitored_variables:
                # Trigger detector for this specific variable
                end_time = timezone.now()
                start_time = end_time - timedelta(hours=1)

                try:
                    # Use utility function for Celery fallback logic
                    task_result, execution_mode = run_task_with_fallback(
                        run_detector,
                        detector.id,
                        start_date=start_time.isoformat(),
                        end_date=end_time.isoformat(),
                        triggered_by_variable=variable.id,
                        task_name=f"Detector '{detector.name}' for variable '{variable.code}'",
                    )

                    task_id = task_result.id if hasattr(task_result, "id") else execution_mode
                    triggered_detectors.append({"detector_id": detector.id, "detector_name": detector.name, "variable_code": variable.code, "task_id": task_id})

                except Exception as e:
                    logger.error(f"Failed to trigger detector '{detector.name}' for variable '{variable.code}': {str(e)}")

        if triggered_detectors:
            logger.info(f"Triggered {len(triggered_detectors)} variable-specific detectors for '{variable.code}': {[d['detector_name'] for d in triggered_detectors]}")

    except Exception as e:
        logger.error(f"Error in variable-specific detector triggering: {str(e)}")


def connect_signal_handlers():
    """Connect signal handlers to data pipeline signals.

    This function is called from apps.py to avoid circular import issues.
    """
    try:
        from data_pipeline.signals import data_processing_completed, variable_data_updated

        # Connect the handlers to the signals
        data_processing_completed.connect(trigger_detectors_for_source, dispatch_uid="alert_framework_trigger_detectors_for_source")

        variable_data_updated.connect(trigger_variable_specific_detectors, dispatch_uid="alert_framework_trigger_variable_specific_detectors")

        # logger.info("Alert framework signal handlers connected successfully")

    except ImportError as e:
        logger.warning(f"Could not connect signal handlers: {str(e)}")
