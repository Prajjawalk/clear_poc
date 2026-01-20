"""Celery tasks for alert framework detector execution and alert publishing."""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from alert_framework.models import Detection

from celery import shared_task
from django.utils import timezone
from django.utils.module_loading import import_string

from alert_framework.deduplication import duplication_checker

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def run_detector(self, detector_id: int, start_date: str = None, end_date: str = None, **kwargs) -> dict:
    """Execute a detector and process results.

    Args:
        detector_id: ID of detector to run
        start_date: Analysis start date (ISO format)
        end_date: Analysis end date (ISO format)
        **kwargs: Additional detector parameters

    Returns:
        dict: Execution results with statistics
    """
    from alert_framework.models import Detector

    execution_start = timezone.now()
    results = {
        "detector_id": detector_id,
        "task_id": self.request.id,
        "start_time": execution_start.isoformat(),
        "success": False,
        "detections_created": 0,
        "detections_duplicates": 0,
        "error_message": None,
    }

    try:
        # Get detector configuration
        try:
            detector = Detector.objects.get(id=detector_id)
        except Detector.DoesNotExist:
            raise ValueError(f"Detector with ID {detector_id} not found")

        if not detector.active:
            raise ValueError(f"Detector {detector.name} is not active")

        # Parse date parameters
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        else:
            # Default to last 7 days
            start_dt = timezone.now() - timedelta(days=7)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        else:
            end_dt = timezone.now()

        logger.info(
            f"Starting detector execution: {detector.name}",
            extra={"detector_id": detector_id, "start_date": start_dt.isoformat(), "end_date": end_dt.isoformat(), "task_id": self.request.id},
        )

        # Load detector class dynamically
        # Check if class_name already contains the full module path
        if "alert_framework.detectors" in detector.class_name:
            detector_class = import_string(detector.class_name)
        else:
            detector_class = import_string(f"alert_framework.detectors.{detector.class_name}")
        detector_instance = detector_class(detector)

        # Filter out task-specific kwargs that should not be passed to detector
        # triggered_by_source is used for logging/tracking but not needed by detect() method
        detector_kwargs = {k: v for k, v in kwargs.items() if k not in ['triggered_by_source']}

        # Execute detection
        detection_results = detector_instance.detect(start_dt, end_dt, **detector_kwargs)

        # Process detection results
        detections_created = 0
        detections_duplicates = 0

        for detection_data in detection_results:
            detection = _create_detection_from_result(detector, detection_data)
            if detection:
                # Check for duplicates
                if duplication_checker.is_duplicate(detection):
                    detections_duplicates += 1
                else:
                    detections_created += 1

        # Update detector statistics
        detector.last_run = execution_start
        detector.run_count += 1
        detector.detection_count += detections_created
        detector.save(update_fields=["last_run", "run_count", "detection_count"])

        results.update(
            {
                "success": True,
                "detections_created": detections_created,
                "detections_duplicates": detections_duplicates,
                "end_time": timezone.now().isoformat(),
                "duration_seconds": (timezone.now() - execution_start).total_seconds(),
            }
        )

        logger.info(
            f"Detector execution completed: {detector.name}",
            extra={
                "detector_id": detector_id,
                "detections_created": detections_created,
                "detections_duplicates": detections_duplicates,
                "duration_seconds": results["duration_seconds"],
            },
        )

        # Automatically process pending detections to create alerts
        if detections_created > 0:
            logger.info(f"Processing {detections_created} new detections to create alerts")
            try:
                processing_result = process_pending_detections()
                alerts_created = processing_result.get("alerts_created", 0)
                results["alerts_created"] = alerts_created
                logger.info(
                    f"Alert processing completed: {alerts_created} alerts created from pending detections", extra={"detector_id": detector_id, "alerts_created": alerts_created}
                )
            except Exception as e:
                logger.error(f"Failed to process pending detections: {str(e)}")
                results["processing_error"] = str(e)

    except Exception as e:
        import traceback
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        results.update({"success": False, "error_message": error_msg, "end_time": timezone.now().isoformat()})

        logger.error(f"Detector execution failed: {error_msg}\n{error_traceback}", extra={"detector_id": detector_id, "error_message": error_msg, "task_id": self.request.id})

        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying detector execution (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2**self.request.retries))

    return results


@shared_task
def process_pending_detections(max_detections: int = 100) -> dict:
    """Process pending detections and generate alerts.

    Args:
        max_detections: Maximum number of detections to process

    Returns:
        dict: Processing results
    """
    from alert_framework.models import Detection

    results = {"processed": 0, "alerts_created": 0, "errors": 0, "start_time": timezone.now().isoformat()}

    try:
        # Get pending detections
        pending_detections = (
            Detection.objects.filter(
                status="pending",
                duplicate_of__isnull=True,  # Exclude duplicates
            )
            .select_related("detector", "shock_type")
            .prefetch_related("locations")[:max_detections]
        )

        for detection in pending_detections:
            try:
                # Load detector class to generate alert
                # Check if class_name already contains the full module path
                if "alert_framework.detectors" in detection.detector.class_name:
                    detector_class = import_string(detection.detector.class_name)
                else:
                    detector_class_name = f"alert_framework.detectors.{detection.detector.class_name}"
                    detector_class = import_string(detector_class_name)
                detector_instance = detector_class(detection.detector)

                # Generate alert data
                alert_data = detector_instance.generate_alert(detection)

                # Create alert via API call to public interface
                alert_created = _create_alert_via_api(alert_data)

                if alert_created:
                    detection.mark_processed(alert=alert_created)
                    results["alerts_created"] += 1
                else:
                    detection.mark_dismissed()

                results["processed"] += 1

            except Exception as e:
                logger.error(f"Failed to process detection {detection.id}: {str(e)}", extra={"detection_id": detection.id})
                results["errors"] += 1

        results["end_time"] = timezone.now().isoformat()

        logger.info("Detection processing completed", extra={"processed": results["processed"], "alerts_created": results["alerts_created"], "errors": results["errors"]})

    except Exception as e:
        results.update({"error": str(e), "end_time": timezone.now().isoformat()})
        logger.error(f"Detection processing task failed: {str(e)}")

    return results


def _create_detection_from_result(detector, detection_data: dict) -> Optional["Detection"]:
    """Create Detection model instance from detector result.

    Args:
        detector: Detector model instance
        detection_data: Detection data from detector

    Returns:
        Detection instance or None if creation failed
    """
    try:
        from alert_framework.models import Detection
        from alerts.models import ShockType
        from location.models import Location

        # Get shock type
        shock_type = None
        shock_type_name = detection_data.get("shock_type_name")
        if shock_type_name:
            try:
                shock_type = ShockType.objects.get(name=shock_type_name)
            except ShockType.DoesNotExist:
                logger.warning(f"Shock type '{shock_type_name}' not found")

        # Create detection
        detection = Detection.objects.create(
            detector=detector,
            title=detection_data.get("title", f"Detection from {detector.name}"),
            detection_timestamp=detection_data["detection_timestamp"],
            confidence_score=detection_data.get("confidence_score"),
            shock_type=shock_type,
            detection_data=detection_data.get("detection_data", {}),
        )

        # Add locations
        location_ids = detection_data.get("locations", [])
        if location_ids:
            # Handle both Location objects and IDs
            locations = []
            for loc in location_ids:
                if isinstance(loc, int):
                    try:
                        locations.append(Location.objects.get(id=loc))
                    except Location.DoesNotExist:
                        logger.warning(f"Location ID {loc} not found")
                else:
                    locations.append(loc)

            detection.locations.add(*locations)

        return detection

    except Exception as e:
        logger.error(f"Failed to create detection: {str(e)}")
        return None


def _create_alert_via_api(alert_data: dict) -> Any:
    """Create alert via public interface API.

    Args:
        alert_data: Alert data dictionary

    Returns:
        Created alert object or None if failed
    """
    from alerts.models import Alert
    from data_pipeline.models import Source

    try:
        # Get or create the data source
        data_source_name = alert_data.get("data_source", "Test Source")
        try:
            data_source = Source.objects.get(name=data_source_name)
        except Source.DoesNotExist:
            # Create a default test source if it doesn't exist
            data_source = Source.objects.create(name=data_source_name, type="api", class_name="TestSource", description="Test source for integration testing", is_active=True)

        # Create the alert directly (in production, this might go through an API)
        alert = Alert.objects.create(
            title=alert_data.get("title", "Alert"),
            text=alert_data.get("text", ""),
            shock_type_id=alert_data.get("shock_type") if alert_data.get("shock_type") else None,
            shock_date=alert_data.get("shock_date", timezone.now().date()),
            severity=alert_data.get("severity", 3),
            data_source=data_source,
            valid_from=alert_data.get("valid_from", timezone.now()),
            valid_until=alert_data.get("valid_until", timezone.now() + timedelta(days=7)),
            go_no_go=True,  # Auto-approve for test
            go_no_go_date=timezone.now(),  # Mark approval time
        )

        # Add locations if provided
        location_ids = alert_data.get("locations", [])
        if location_ids:
            alert.locations.add(*location_ids)

        logger.info(f"Alert created: {alert.title}", extra={"alert_id": alert.id})
        return alert

    except Exception as e:
        logger.error(f"Alert API creation failed: {str(e)}")
        return None


@shared_task(bind=True, max_retries=3)
def publish_alert(self, detection_id: int, template_id: int, target_apis: list | None = None, language: str = "en") -> dict:
    """Publish a detection as an alert to external systems.

    Args:
        detection_id: ID of detection to publish
        template_id: ID of template to use for formatting
        target_apis: List of API names to publish to (None = all configured)
        language: Language for alert content

    Returns:
        dict: Publication results
    """
    from alert_framework.api_client import PublicAlertInterface
    from alert_framework.models import AlertTemplate, Detection, PublishedAlert

    results = {
        "detection_id": detection_id,
        "template_id": template_id,
        "task_id": self.request.id,
        "start_time": timezone.now().isoformat(),
        "success": False,
        "published_alerts": [],
        "failed_apis": [],
        "error_message": None,
    }

    try:
        # Get detection and template
        detection = Detection.objects.select_related("detector").prefetch_related("locations").get(id=detection_id)
        template = AlertTemplate.objects.get(id=template_id)

        # Initialize public alert interface
        alert_interface = PublicAlertInterface()

        # Publish alert
        publication_results = alert_interface.publish_alert(detection=detection, template=template, target_apis=target_apis, language=language)

        # Process results and create PublishedAlert records
        for api_name, result in publication_results.items():
            try:
                published_alert = PublishedAlert.objects.create(
                    detection=detection,
                    template=template,
                    api_name=api_name,
                    language=language,
                    status="pending",
                )

                if result["success"]:
                    published_alert.mark_published(external_id=result.get("external_id", ""), response_data=result.get("response", {}))
                    results["published_alerts"].append({"api_name": api_name, "external_id": result.get("external_id"), "status": "published"})
                else:
                    published_alert.mark_failed(result.get("error", "Unknown error"))
                    results["failed_apis"].append({"api_name": api_name, "error": result.get("error")})

            except Exception as e:
                logger.error(f"Failed to create PublishedAlert record for {api_name}: {e}")
                results["failed_apis"].append({"api_name": api_name, "error": str(e)})

        # Determine overall success
        results["success"] = len(results["published_alerts"]) > 0
        results["end_time"] = timezone.now().isoformat()

        logger.info(
            f"Alert publication completed for detection {detection_id}",
            extra={
                "detection_id": detection_id,
                "published_count": len(results["published_alerts"]),
                "failed_count": len(results["failed_apis"]),
            },
        )

    except Exception as e:
        error_msg = str(e)
        results.update({"success": False, "error_message": error_msg, "end_time": timezone.now().isoformat()})

        logger.error(
            "Alert publication failed",
            extra={"detection_id": detection_id, "error_message": error_msg, "task_id": self.request.id},
        )

        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying alert publication (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2**self.request.retries))

    return results


@shared_task(bind=True, max_retries=2)
def update_published_alert(self, published_alert_id: int) -> dict:
    """Update a published alert in external systems.

    Args:
        published_alert_id: ID of PublishedAlert to update

    Returns:
        dict: Update results
    """
    from alert_framework.api_client import PublicAlertInterface
    from alert_framework.models import PublishedAlert

    results = {
        "published_alert_id": published_alert_id,
        "task_id": self.request.id,
        "start_time": timezone.now().isoformat(),
        "success": False,
        "error_message": None,
    }

    try:
        # Get published alert
        published_alert = PublishedAlert.objects.select_related("detection__detector", "template").prefetch_related("detection__locations").get(id=published_alert_id)

        if not published_alert.external_id:
            raise ValueError("Published alert has no external ID")

        # Initialize alert interface
        alert_interface = PublicAlertInterface()

        # Update alert
        external_ids = {published_alert.api_name: published_alert.external_id}
        update_results = alert_interface.update_alert(
            detection=published_alert.detection,
            template=published_alert.template,
            external_ids=external_ids,
            language=published_alert.language,
        )

        # Process result
        result = update_results.get(published_alert.api_name, {})
        if result.get("success"):
            published_alert.mark_updated(result.get("response", {}))
            results["success"] = True
        else:
            published_alert.mark_failed(result.get("error", "Update failed"))
            results["error_message"] = result.get("error", "Update failed")

        results["end_time"] = timezone.now().isoformat()

        logger.info(
            f"Alert update completed for published alert {published_alert_id}",
            extra={"published_alert_id": published_alert_id, "success": results["success"]},
        )

    except Exception as e:
        error_msg = str(e)
        results.update({"success": False, "error_message": error_msg, "end_time": timezone.now().isoformat()})

        logger.error(
            "Alert update failed",
            extra={"published_alert_id": published_alert_id, "error_message": error_msg, "task_id": self.request.id},
        )

        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying alert update (attempt {self.request.retries + 1})")
            raise self.retry(countdown=30 * (2**self.request.retries))

    return results


@shared_task(bind=True, max_retries=2)
def cancel_published_alert(self, published_alert_id: int, reason: str = "Alert cancelled") -> dict:
    """Cancel a published alert in external systems.

    Args:
        published_alert_id: ID of PublishedAlert to cancel
        reason: Reason for cancellation

    Returns:
        dict: Cancellation results
    """
    from alert_framework.api_client import PublicAlertInterface
    from alert_framework.models import PublishedAlert

    results = {
        "published_alert_id": published_alert_id,
        "task_id": self.request.id,
        "start_time": timezone.now().isoformat(),
        "success": False,
        "error_message": None,
    }

    try:
        # Get published alert
        published_alert = PublishedAlert.objects.get(id=published_alert_id)

        if not published_alert.external_id:
            raise ValueError("Published alert has no external ID")

        # Initialize alert interface
        alert_interface = PublicAlertInterface()

        # Cancel alert
        external_ids = {published_alert.api_name: published_alert.external_id}
        cancel_results = alert_interface.cancel_alert(external_ids=external_ids, reason=reason)

        # Process result
        result = cancel_results.get(published_alert.api_name, {})
        if result.get("success"):
            published_alert.mark_cancelled(reason)
            results["success"] = True
        else:
            results["error_message"] = result.get("error", "Cancellation failed")

        results["end_time"] = timezone.now().isoformat()

        logger.info(
            f"Alert cancellation completed for published alert {published_alert_id}",
            extra={"published_alert_id": published_alert_id, "success": results["success"]},
        )

    except Exception as e:
        error_msg = str(e)
        results.update({"success": False, "error_message": error_msg, "end_time": timezone.now().isoformat()})

        logger.error(
            "Alert cancellation failed",
            extra={"published_alert_id": published_alert_id, "error_message": error_msg, "task_id": self.request.id},
        )

        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying alert cancellation (attempt {self.request.retries + 1})")
            raise self.retry(countdown=30 * (2**self.request.retries))

    return results


@shared_task
def monitor_published_alerts() -> dict:
    """Monitor status of published alerts and sync with external systems.

    Returns:
        dict: Monitoring results
    """
    from alert_framework.api_client import PublicAlertInterface
    from alert_framework.models import PublishedAlert

    results = {
        "start_time": timezone.now().isoformat(),
        "checked_alerts": 0,
        "status_updates": 0,
        "errors": 0,
        "api_health": {},
    }

    try:
        # Initialize alert interface
        alert_interface = PublicAlertInterface()

        # Check API health
        results["api_health"] = alert_interface.check_api_health()

        # Get published alerts to monitor (published in last 24 hours)
        cutoff_time = timezone.now() - timedelta(hours=24)
        published_alerts = PublishedAlert.objects.filter(status="published", published_at__gte=cutoff_time).exclude(external_id="")

        for published_alert in published_alerts:
            try:
                client = alert_interface.clients.get(published_alert.api_name)
                if client:
                    status_info = client.get_alert_status(published_alert.external_id)

                    # Update metadata with latest status
                    published_alert.publication_metadata.update({"last_status_check": status_info})
                    published_alert.save()

                    results["status_updates"] += 1

                results["checked_alerts"] += 1

            except Exception as e:
                logger.error(f"Failed to check status for alert {published_alert.id}: {e}")
                results["errors"] += 1

        results["end_time"] = timezone.now().isoformat()

        logger.info(
            "Alert monitoring completed",
            extra={
                "checked_alerts": results["checked_alerts"],
                "status_updates": results["status_updates"],
                "errors": results["errors"],
            },
        )

    except Exception as e:
        results.update({"error": str(e), "end_time": timezone.now().isoformat()})
        logger.error(f"Alert monitoring failed: {str(e)}")

    return results
