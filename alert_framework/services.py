"""Service layer for alert framework business logic."""

from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count
from django.utils import timezone

from .models import AlertTemplate, Detection, Detector


class AlertStatisticsService:
    """Service for calculating and aggregating alert framework statistics."""

    @staticmethod
    def get_detector_stats() -> dict[str, int]:
        """Get overall detector statistics.

        Returns:
            Dictionary with detector statistics
        """
        return {
            "total": Detector.objects.count(),
            "active": Detector.objects.filter(active=True).count(),
            "recent_runs": Detector.objects.filter(last_run__gte=timezone.now() - timedelta(hours=24)).count(),
            "scheduled": Detector.objects.exclude(schedule__isnull=True).count(),
        }

    @staticmethod
    def get_detection_stats(timeframe_days: int | None = None) -> dict[str, Any]:
        """Get detection statistics with optional timeframe filtering.

        Args:
            timeframe_days: Number of days to look back (None for all time)

        Returns:
            Dictionary with detection statistics
        """
        base_queryset = Detection.objects.all()

        if timeframe_days:
            cutoff = timezone.now() - timedelta(days=timeframe_days)
            base_queryset = base_queryset.filter(detection_timestamp__gte=cutoff)

        today = timezone.now().date()

        return {
            "total": base_queryset.count(),
            "pending": base_queryset.filter(status="pending").count(),
            "processed": base_queryset.filter(status="processed").count(),
            "dismissed": base_queryset.filter(status="dismissed").count(),
            "processed_today": base_queryset.filter(status="processed", processed_at__date=today).count(),
            "dismissed_today": base_queryset.filter(status="dismissed", processed_at__date=today).count(),
            "duplicates": base_queryset.filter(duplicate_of__isnull=False).count(),
            "high_confidence": base_queryset.filter(confidence_score__gte=0.8).count(),
            "average_confidence": base_queryset.filter(confidence_score__isnull=False).aggregate(avg=Avg("confidence_score"))["avg"],
        }

    @staticmethod
    def get_recent_detection_stats() -> dict[str, int]:
        """Get detection statistics for various recent time periods.

        Returns:
            Dictionary with recent detection counts
        """
        now = timezone.now()

        return {
            "last_hour": Detection.objects.filter(detection_timestamp__gte=now - timedelta(hours=1)).count(),
            "last_24h": Detection.objects.filter(detection_timestamp__gte=now - timedelta(hours=24)).count(),
            "last_7d": Detection.objects.filter(detection_timestamp__gte=now - timedelta(days=7)).count(),
            "last_30d": Detection.objects.filter(detection_timestamp__gte=now - timedelta(days=30)).count(),
        }

    @staticmethod
    def get_detector_performance_stats(detector_id: int) -> dict[str, Any]:
        """Get performance statistics for a specific detector.

        Args:
            detector_id: ID of the detector

        Returns:
            Dictionary with detector performance metrics
        """
        try:
            detector = Detector.objects.get(id=detector_id)
        except Detector.DoesNotExist:
            return {}

        detections = detector.detections.all()

        return {
            "run_count": detector.run_count,
            "detection_count": detector.detection_count,
            "average_detections_per_run": detector.average_detections_per_run,
            "success_rate": detector.success_rate,
            "total_detections": detections.count(),
            "pending_detections": detections.filter(status="pending").count(),
            "processed_detections": detections.filter(status="processed").count(),
            "dismissed_detections": detections.filter(status="dismissed").count(),
            "duplicate_detections": detections.filter(duplicate_of__isnull=False).count(),
            "last_run": detector.last_run,
            "time_since_last_run": (timezone.now() - detector.last_run if detector.last_run else None),
        }

    @staticmethod
    def get_template_stats() -> dict[str, int]:
        """Get alert template statistics.

        Returns:
            Dictionary with template statistics
        """
        return {
            "total": AlertTemplate.objects.count(),
            "active": AlertTemplate.objects.filter(active=True).count(),
            "shock_types_covered": AlertTemplate.objects.values("shock_type").distinct().count(),
            "detector_specific": AlertTemplate.objects.exclude(detector_type="").count(),
        }

    @staticmethod
    def get_system_health_metrics() -> dict[str, Any]:
        """Get overall system health metrics.

        Returns:
            Dictionary with system health indicators
        """
        detector_stats = AlertStatisticsService.get_detector_stats()
        detection_stats = AlertStatisticsService.get_detection_stats()

        total_detections = detection_stats["total"]
        pending_detections = detection_stats["pending"]

        return {
            "detectors_with_recent_activity": Detector.objects.filter(last_run__gte=timezone.now() - timedelta(hours=48)).count(),
            "pending_detection_rate": ((pending_detections / max(total_detections, 1)) * 100),
            "high_confidence_rate": ((detection_stats["high_confidence"] / max(total_detections, 1)) * 100),
            "active_detector_rate": ((detector_stats["active"] / max(detector_stats["total"], 1)) * 100),
            "average_processing_time": AlertStatisticsService._calculate_avg_processing_time(),
        }

    @staticmethod
    def _calculate_avg_processing_time():
        """Calculate average processing time for detections.

        Returns:
            Average processing time in seconds or None
        """
        processed_detections = Detection.objects.filter(status="processed", processed_at__isnull=False).exclude(created_at__isnull=True)

        if not processed_detections.exists():
            return None

        # Sample recent detections for performance
        recent_processed = processed_detections.order_by("-processed_at")[:100]

        total_time = timedelta()
        count = 0

        for detection in recent_processed:
            if detection.processing_duration:
                total_time += detection.processing_duration
                count += 1

        if count == 0:
            return None

        avg_time = total_time / count
        return avg_time.total_seconds()

    @staticmethod
    def get_detection_trends(days: int = 7) -> dict[str, Any]:
        """Get detection trend data for the specified number of days.

        Args:
            days: Number of days to include in trends

        Returns:
            Dictionary with trend data
        """
        cutoff = timezone.now() - timedelta(days=days)

        # Daily detection counts - use database-specific date functions
        daily_counts = (
            Detection.objects.filter(detection_timestamp__gte=cutoff).extra(select={"day": "date(detection_timestamp)"}).values("day").annotate(count=Count("id")).order_by("day")
        )

        # Status breakdown over time - use single query with aggregation
        status_breakdown = Detection.objects.filter(created_at__gte=cutoff).values("status").annotate(count=Count("id"))

        # Detector activity - use select_related for detector names
        detector_activity = (
            Detection.objects.filter(detection_timestamp__gte=cutoff).select_related("detector").values("detector__name").annotate(count=Count("id")).order_by("-count")[:10]
        )

        return {
            "daily_counts": list(daily_counts),
            "status_breakdown": list(status_breakdown),
            "top_active_detectors": list(detector_activity),
        }


class DetectorConfigurationService:
    """Service for managing detector configurations."""

    @staticmethod
    def get_configuration_summary(detector) -> str:
        """Get a human-readable summary of detector configuration.

        Args:
            detector: Detector instance

        Returns:
            Configuration summary string
        """
        if not detector.configuration:
            return "No configuration"

        config = detector.configuration
        summary_parts = []

        # Common configuration parameters
        if "threshold_multiplier" in config:
            summary_parts.append(f"threshold×{config['threshold_multiplier']}")

        if "baseline_days" in config:
            summary_parts.append(f"baseline {config['baseline_days']}d")

        if "minimum_events" in config:
            summary_parts.append(f"min {config['minimum_events']} events")

        if "minimum_displaced" in config:
            summary_parts.append(f"min {config['minimum_displaced']} displaced")

        if "monitored_sources" in config:
            sources = config["monitored_sources"]
            if isinstance(sources, list) and sources:
                summary_parts.append(f"monitors {len(sources)} sources")

        if "monitored_variables" in config:
            variables = config["monitored_variables"]
            if isinstance(variables, list) and variables:
                summary_parts.append(f"monitors {len(variables)} variables")

        # Limit to 3 most important items
        return ", ".join(summary_parts[:3]) if summary_parts else "Default configuration"
