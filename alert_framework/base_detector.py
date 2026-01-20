"""Abstract base class for detector implementations."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from django.db import models
from django.utils import timezone

from data_pipeline.models import VariableData
from location.models import Location

if TYPE_CHECKING:
    from alert_framework.models import AlertTemplate, Detection


class BaseDetector(ABC):
    """Abstract base class for all detection implementations."""

    def __init__(self, detector_config):
        """Initialize detector with configuration.

        Args:
            detector_config: Detector model instance with configuration
        """
        self.config = detector_config
        self.logger = logging.getLogger(f"alert_framework.detector.{self.__class__.__name__}")
        self.execution_context = {}

    @abstractmethod
    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict]:
        """
        Analyze data within time window and return detections.

        Args:
            start_date: Analysis window start
            end_date: Analysis window end
            **kwargs: Additional parameters

        Returns:
            List of detection dictionaries with required fields:
            - detection_timestamp: When the detected event occurred
            - locations: List of location IDs or Location instances
            - confidence_score: Optional confidence (0-1)
            - shock_type_name: Name of shock type for categorization
            - detection_data: Additional detector-specific data
        """
        pass

    @abstractmethod
    def _load_config(self, **config):
        """Initialize the detector with proper configuration, parameters may vary."""
        pass

    @abstractmethod
    def _load_data(self, start_date=None, end_date=None):
        """Load the data from source."""
        pass

    @abstractmethod
    def get_configuration_schema(self) -> dict:
        """Return JSON schema for configuration validation."""
        pass

    def validate_configuration(self, config: dict) -> bool:
        """Validate configuration against schema.

        Args:
            config: Configuration dictionary to validate

        Returns:
            bool: True if configuration is valid
        """
        try:
            import jsonschema

            schema = self.get_configuration_schema()
            jsonschema.validate(config, schema)
            return True
        except ImportError:
            self.logger.warning("jsonschema not available, skipping validation")
            return True
        except Exception as e:
            self.logger.error(f"Configuration validation failed: {str(e)}")
            return False

    def generate_alert(self, detection: "Detection") -> dict:
        """
        Generate alert data from detection.

        Args:
            detection: Detection model instance

        Returns:
            Dictionary with alert fields for API creation
        """
        # Get alert template for this shock type
        template = self.get_alert_template(detection)
        if not template:
            # Fallback to default alert generation
            return self._generate_default_alert(detection)

        # Render template with detection data
        context_data = self._build_template_context(detection)
        rendered = template.render(context_data)

        return {
            "title": rendered["title"],
            "text": rendered["text"],
            "shock_type": detection.shock_type.id if detection.shock_type else None,
            "shock_date": detection.detection_timestamp.date(),
            "locations": [loc.id for loc in detection.locations.all()],
            "severity": self._calculate_severity(detection),
            "data_source": self._get_data_source_reference(detection),
            "valid_from": timezone.now(),
            "valid_until": self._calculate_validity_period(detection),
        }

    def get_alert_template(self, detection: "Detection") -> Optional["AlertTemplate"]:
        """Get appropriate alert template for detection.

        Args:
            detection: Detection instance

        Returns:
            AlertTemplate instance or None
        """
        from alert_framework.models import AlertTemplate

        if not detection.shock_type:
            return None

        try:
            # Get detector class name for matching
            detector_class_name = self.__class__.__name__

            # First try to find template matching both shock_type and detector_type
            template = AlertTemplate.objects.filter(
                shock_type=detection.shock_type,
                active=True,
                detector_type=detector_class_name
            ).first()

            if template:
                return template

            # Fall back to template with no specific detector_type (empty or blank)
            template = AlertTemplate.objects.filter(
                shock_type=detection.shock_type,
                active=True,
                detector_type__in=['', None]
            ).first()

            return template
        except Exception as e:
            self.logger.error(f"Failed to get alert template: {str(e)}")
            return None

    def _generate_default_alert(self, detection: "Detection") -> dict:
        """Generate default alert when no template is available."""
        location_names = [loc.name for loc in detection.locations.all()]
        location_text = ", ".join(location_names) if location_names else "Unknown location"

        shock_type_name = detection.shock_type.name if detection.shock_type else "Alert"

        title = f"{shock_type_name} detected in {location_text}"
        text = f"A {shock_type_name.lower()} condition has been detected in {location_text} on {detection.detection_timestamp.strftime('%Y-%m-%d')}."

        if detection.confidence_score:
            text += f" Detection confidence: {detection.confidence_score:.1%}"

        # Add detector information
        text += f"\n\nDetected by: {detection.detector.name}"

        # Add detection data if available
        if detection.detection_data:
            # Extract headline if present (for BERT and scoring detectors)
            headline = detection.detection_data.get('headline')
            if headline:
                text += f"\n\nSource: {headline[:200]}"

        return {
            "title": title,
            "text": text,
            "shock_type": detection.shock_type.id if detection.shock_type else None,
            "shock_date": detection.detection_timestamp.date(),
            "locations": [loc.id for loc in detection.locations.all()],
            "severity": self._calculate_severity(detection),
            "data_source": self._get_data_source_reference(detection),
            "valid_from": timezone.now(),
            "valid_until": self._calculate_validity_period(detection),
        }

    def _build_template_context(self, detection: "Detection") -> dict:
        """Build context dictionary for template rendering."""
        locations = list(detection.locations.all())

        context = {
            "detection": detection,
            "detector_name": detection.detector.name,
            "detection_timestamp": detection.detection_timestamp,
            "confidence_score": detection.confidence_score,
            "locations": locations,
            "location_names": [loc.name for loc in locations],
            "primary_location": locations[0] if locations else None,
            # Add 'location' for template compatibility
            "location": locations[0] if locations else None,
            "shock_type": detection.shock_type.name if detection.shock_type else None,
            "detection_data": detection.detection_data,
        }

        # Add detector-specific context
        context.update(self._get_detector_specific_context(detection))

        return context

    def _get_detector_specific_context(self, detection: "Detection") -> dict:
        """Get detector-specific context for template rendering.

        Override this method to add detector-specific template variables.

        Args:
            detection: Detection instance

        Returns:
            Dictionary of additional context variables
        """
        return {}

    def _calculate_severity(self, detection: "Detection") -> int:
        """Calculate severity level (1-5) for detection.

        Override this method to implement detector-specific severity calculation.

        Args:
            detection: Detection instance

        Returns:
            int: Severity level between 1 and 5
        """
        if detection.confidence_score:
            # Map confidence to severity (higher confidence = higher severity)
            if detection.confidence_score >= 0.8:
                return 4
            elif detection.confidence_score >= 0.6:
                return 3
            elif detection.confidence_score >= 0.4:
                return 2
            else:
                return 1
        return 3  # Default medium severity

    def _get_data_source_reference(self, detection: "Detection") -> str | None:
        """Get data source reference for alert attribution.

        Override this method to provide specific data source information.

        Args:
            detection: Detection instance

        Returns:
            String identifying the data source
        """
        return detection.detector.name

    def _calculate_validity_period(self, detection: "Detection") -> datetime:
        """Calculate alert validity end time.

        Override this method to implement detector-specific validity periods.

        Args:
            detection: Detection instance

        Returns:
            datetime: When the alert should expire
        """
        from datetime import timedelta

        return timezone.now() + timedelta(days=7)  # Default 7-day validity

    # Utility methods for data access and analysis

    def get_variable_data(self, variable_code: str, start_date: datetime = None, end_date: datetime = None, locations: list | None = None, admin_level: int | None = None) -> models.QuerySet:
        """Retrieve variable data within time window.

        Args:
            variable_code: Variable code to retrieve
            start_date: Data window start (optional - if None, no start date filter)
            end_date: Data window end (optional - if None, no end date filter)
            locations: Optional list of location IDs to filter
            admin_level: Optional administrative level filter

        Returns:
            QuerySet of VariableData records, ordered by start_date descending (most recent first) when no date filter
        """
        try:
            queryset = VariableData.objects.filter(variable__code=variable_code).select_related("variable", "gid", "adm_level")

            # Apply date filters only if provided
            if start_date is not None and end_date is not None:
                queryset = queryset.filter(start_date__lte=end_date, end_date__gte=start_date)
            elif start_date is not None:
                queryset = queryset.filter(end_date__gte=start_date)
            elif end_date is not None:
                queryset = queryset.filter(start_date__lte=end_date)

            if locations:
                # Handle both Location objects and IDs
                location_ids = []
                for loc in locations:
                    if isinstance(loc, Location):
                        location_ids.append(loc.id)
                    else:
                        location_ids.append(loc)
                queryset = queryset.filter(gid_id__in=location_ids)

            if admin_level is not None:
                queryset = queryset.filter(adm_level__code=str(admin_level))

            # Order by start_date descending (most recent first) when no date filter,
            # ascending when date filter is applied for chronological analysis
            if start_date is None and end_date is None:
                return queryset.order_by("-start_date")
            else:
                return queryset.order_by("start_date")

        except Exception as e:
            self.logger.error(f"Failed to retrieve variable data for {variable_code}: {str(e)}")
            return VariableData.objects.none()

    def get_locations_by_admin_level(self, admin_level: int) -> models.QuerySet:
        """Get all locations at specified administrative level.

        Args:
            admin_level: Administrative level (0, 1, 2, etc.)

        Returns:
            QuerySet of Location objects
        """
        try:
            return Location.objects.filter(admin_level__level=admin_level).order_by("name")
        except Exception as e:
            self.logger.error(f"Failed to get locations for admin level {admin_level}: {str(e)}")
            return Location.objects.none()

    def log_detection(self, message: str, level: str = "info", **kwargs):
        """Structured logging for detection events.

        Args:
            message: Log message
            level: Log level (info, warning, error)
            **kwargs: Additional structured data
        """
        extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message} | {extra_info}" if extra_info else message

        log_method = getattr(self.logger, level, self.logger.info)
        log_method(full_message)

    def set_execution_context(self, **context):
        """Set execution context for this detector run.

        Args:
            **context: Context variables to store
        """
        self.execution_context.update(context)

    def get_execution_context(self, key: str, default=None):
        """Get execution context value.

        Args:
            key: Context key to retrieve
            default: Default value if key not found

        Returns:
            Context value or default
        """
        return self.execution_context.get(key, default)
