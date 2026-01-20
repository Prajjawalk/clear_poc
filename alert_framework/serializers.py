"""Serializers for alert framework API responses."""

from typing import Any

from django.utils import timezone


class DetectorSerializer:
    """Serializer for Detector model API responses."""

    @staticmethod
    def to_dict(detector, include_stats: bool = False, include_config: bool = True) -> dict[str, Any]:
        """Convert Detector instance to dictionary for API response.

        Args:
            detector: Detector model instance
            include_stats: Include detection statistics
            include_config: Include configuration data

        Returns:
            Dictionary representation of detector
        """
        data = {
            "id": detector.id,
            "name": detector.name,
            "description": detector.description,
            "class_name": detector.class_name,
            "active": detector.active,
            "last_run": detector.last_run.isoformat() if detector.last_run else None,
            "created_at": detector.created_at.isoformat(),
        }

        if include_config:
            data["configuration"] = detector.configuration

        if include_stats:
            # Calculate statistics using aggregation for better performance
            from django.db.models import Count, Q

            stats_qs = detector.detections.aggregate(
                total_detections=Count("id"),
                pending_detections=Count("id", filter=Q(status="pending")),
                processed_detections=Count("id", filter=Q(status="processed")),
                dismissed_detections=Count("id", filter=Q(status="dismissed")),
                recent_detections=Count("id", filter=Q(detection_timestamp__gte=timezone.now() - timezone.timedelta(days=7))),
            )

            data["statistics"] = {
                "total_detections": stats_qs["total_detections"],
                "pending_detections": stats_qs["pending_detections"],
                "processed_detections": stats_qs["processed_detections"],
                "dismissed_detections": stats_qs["dismissed_detections"],
                "recent_detections": stats_qs["recent_detections"],
                "run_count": detector.run_count,
                "detection_count": detector.detection_count,
                "success_rate": detector.success_rate,
                "average_detections_per_run": detector.average_detections_per_run,
            }

        return data


class DetectionSerializer:
    """Serializer for Detection model API responses."""

    @staticmethod
    def to_dict(detection, include_locations: bool = True, include_detector: bool = True) -> dict[str, Any]:
        """Convert Detection instance to dictionary for API response.

        Args:
            detection: Detection model instance
            include_locations: Include location details
            include_detector: Include detector information

        Returns:
            Dictionary representation of detection
        """
        data = {
            "id": detection.id,
            "title": detection.title,
            "detection_timestamp": detection.detection_timestamp.isoformat(),
            "status": detection.status,
            "confidence_score": detection.confidence_score,
            "created_at": detection.created_at.isoformat(),
            "processed_at": detection.processed_at.isoformat() if detection.processed_at else None,
            "detection_data": detection.detection_data,
        }

        if include_detector and detection.detector:
            data["detector"] = {
                "id": detection.detector.id,
                "name": detection.detector.name,
                "description": detection.detector.description,
            }

        if include_locations:
            data["locations"] = [LocationSerializer.to_dict(location) for location in detection.locations.all()]
        else:
            data["locations"] = []

        if detection.shock_type:
            data["shock_type"] = {
                "id": detection.shock_type.id,
                "name": detection.shock_type.name,
            }

        if detection.duplicate_of:
            data["duplicate_of"] = detection.duplicate_of.id

        return data

    @staticmethod
    def to_summary_dict(detection) -> dict[str, Any]:
        """Convert Detection to summary dictionary (minimal fields).

        Args:
            detection: Detection model instance

        Returns:
            Summary dictionary representation
        """
        return {
            "id": detection.id,
            "detection_timestamp": detection.detection_timestamp.isoformat(),
            "status": detection.status,
            "confidence_score": detection.confidence_score,
            "location_count": detection.locations.count(),
        }


class LocationSerializer:
    """Serializer for Location model in detection context."""

    @staticmethod
    def to_dict(location) -> dict[str, Any]:
        """Convert Location instance to dictionary.

        Args:
            location: Location model instance

        Returns:
            Dictionary representation of location
        """
        data = {
            "id": location.id,
            "name": location.name,
        }

        # Add Arabic name if available
        if hasattr(location, "name_ar"):
            data["name_ar"] = location.name_ar

        # Add admin level if available
        try:
            if location.admin_level:
                data["admin_level"] = {
                    "id": location.admin_level.id,
                    "name": location.admin_level.name,
                    "code": location.admin_level.code,
                    "level": int(location.admin_level.code),  # Convert code to int for level
                }
            else:
                data["admin_level"] = None
        except Exception:  # Handle case where admin_level relation doesn't exist
            data["admin_level"] = None

        # Add coordinates if available
        if hasattr(location, "latitude") and hasattr(location, "longitude"):
            if location.latitude and location.longitude:
                data["coordinates"] = {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                }

        return data


class AlertTemplateSerializer:
    """Serializer for AlertTemplate model API responses."""

    @staticmethod
    def to_dict(template) -> dict[str, Any]:
        """Convert AlertTemplate instance to dictionary.

        Args:
            template: AlertTemplate model instance

        Returns:
            Dictionary representation of template
        """
        return {
            "id": template.id,
            "name": template.name,
            "shock_type": {
                "id": template.shock_type.id,
                "name": template.shock_type.name,
            }
            if template.shock_type
            else None,
            "title": template.title,
            "text": template.text,
            "variables": template.variables,
            "active": template.active,
            "detector_type": template.detector_type,
            "created_at": template.created_at.isoformat(),
            "updated_at": template.updated_at.isoformat(),
        }


class PaginationSerializer:
    """Serializer for pagination metadata."""

    @staticmethod
    def to_dict(page_obj, paginator) -> dict[str, Any]:
        """Convert pagination objects to dictionary.

        Args:
            page_obj: Django Page object
            paginator: Django Paginator object

        Returns:
            Dictionary with pagination metadata
        """
        return {
            "page": page_obj.number,
            "total_pages": paginator.num_pages,
            "per_page": paginator.per_page,
            "total_count": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        }
