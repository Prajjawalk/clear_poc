"""PassThrough detector that returns all datapoints from input."""

from datetime import datetime, time
from typing import Any

from django.utils import timezone

from alert_framework.base_detector import BaseDetector


class PassThroughDetector(BaseDetector):
    """Detector that returns all input datapoints without any filtering or processing."""

    def __init__(self, detector_config):
        """Initialize PassThrough detector.

        Args:
            detector_config: Detector model instance with configuration
        """
        super().__init__(detector_config)
        self._load_config()

    def _load_config(self, **config):  # config kept for interface compatibility
        """Initialize the detector configuration."""
        # Get configuration from the detector model
        config_dict = self.config.configuration or {}
        config_dict.update(config)

        # PassThrough detector configuration
        self.variable_code = config_dict.get("variable_code", None)
        self.admin_level = config_dict.get("admin_level", None)
        self.filters = config_dict.get("filters", [])

        # Validate filters format
        if self.filters and not isinstance(self.filters, list):
            self.logger.error("Filters must be a list of dictionaries")
            self.filters = []

    def _load_data(self, start_date=None, end_date=None):
        """Load data from the configured data source.

        Args:
            start_date: Start date for data retrieval
            end_date: End date for data retrieval

        Returns:
            QuerySet of VariableData records
        """
        if not self.variable_code:
            self.logger.warning("No variable_code configured for PassThroughDetector")
            return None

        return self.get_variable_data(
            variable_code=self.variable_code,
            start_date=start_date,
            end_date=end_date,
            admin_level=self.admin_level,
        )

    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict[str, Any]]:  # kwargs kept for interface compatibility
        """Return all datapoints from input without any processing.

        Args:
            start_date: Analysis window start
            end_date: Analysis window end
            **kwargs: Additional parameters (ignored)

        Returns:
            List of detection dictionaries for all input datapoints
        """
        self.log_detection(
            "Starting PassThrough detection",
            start_date=start_date,
            end_date=end_date,
            variable_code=self.variable_code,
        )

        # Load data for the specified time window
        data = self._load_data(start_date=start_date, end_date=end_date)

        if not data:
            self.log_detection("No data found for PassThrough detection", level="warning")
            return []

        detections = []
        data_count = data.count()

        self.log_detection(f"Processing {data_count} datapoints for PassThrough detection")

        for record in data:
            # Apply filters if configured
            if self.filters and not self._passes_filters(record):
                continue

            # Create detection for datapoints that pass filters
            locations = []
            if record.gid:
                locations = [{"id": record.gid.id, "name": record.gid.name}]

            # Convert date to timezone-aware datetime if needed
            detection_timestamp = record.start_date
            if isinstance(detection_timestamp, datetime):
                if timezone.is_naive(detection_timestamp):
                    detection_timestamp = timezone.make_aware(detection_timestamp)
            else:
                # Convert date to datetime at midnight in the current timezone
                detection_timestamp = timezone.make_aware(datetime.combine(detection_timestamp, time.min))

            detection = {
                "detection_timestamp": detection_timestamp,
                "locations": locations,
                "confidence_score": 1.0,  # Full confidence since we return everything
                "shock_type_name": "passthrough",
                "detection_data": {
                    "variable_code": record.variable.code,
                    "variable_name": record.variable.name,
                    "original_value": record.value,
                    "start_date": record.start_date.isoformat() if record.start_date else None,
                    "end_date": record.end_date.isoformat() if record.end_date else None,
                    "location_name": record.gid.name if record.gid else None,
                    "admin_level": record.adm_level.code if record.adm_level else None,
                    "detector_type": "passthrough",
                    "applied_filters": self.filters if self.filters else None,
                },
            }
            detections.append(detection)

        self.log_detection(
            "PassThrough detection completed",
            total_detections=len(detections),
            data_points_processed=data_count,
            filters_applied=len(self.filters) if self.filters else 0,
        )

        return detections

    def _passes_filters(self, record) -> bool:
        """Check if a record passes all configured filters.

        Args:
            record: VariableData record to check

        Returns:
            bool: True if record passes all filters, False otherwise
        """
        if not self.filters:
            return True

        for filter_config in self.filters:
            if not isinstance(filter_config, dict):
                self.logger.warning(f"Invalid filter format: {filter_config}")
                continue

            variable_name = filter_config.get("variable_name")
            filter_value = filter_config.get("value")

            if not variable_name or filter_value is None:
                self.logger.warning(f"Invalid filter config: {filter_config}")
                continue

            # Check if this record matches the filter
            if record.variable.name == variable_name:
                if str(record.value) != str(filter_value):
                    return False

        return True

    def get_configuration_schema(self) -> dict[str, Any]:
        """Return JSON schema for PassThrough detector configuration.

        Returns:
            Dictionary containing the JSON schema
        """
        return {
            "type": "object",
            "properties": {
                "variable_code": {"type": "string", "description": "Code of the variable to process", "minLength": 1},
                "admin_level": {"type": ["integer", "null"], "description": "Administrative level filter (optional)", "minimum": 0},
                "filters": {
                    "type": "array",
                    "description": "List of variable filters to apply",
                    "items": {
                        "type": "object",
                        "properties": {
                            "variable_name": {"type": "string", "description": "Name of the variable to filter on", "minLength": 1},
                            "value": {"type": ["string", "number", "boolean"], "description": "Value to match for the filter"},
                        },
                        "required": ["variable_name", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["variable_code"],
            "additionalProperties": False,
            "title": "PassThrough Detector Configuration",
            "description": "Configuration for PassThrough detector that returns datapoints, optionally filtered by variable values",
        }

    def _calculate_severity(self, detection) -> int:  # detection kept for interface compatibility
        """Calculate severity for PassThrough detections.

        Args:
            detection: Detection instance

        Returns:
            int: Always returns 1 (lowest severity) since all data is passed through
        """
        return 1

    def _get_detector_specific_context(self, detection) -> dict[str, Any]:
        """Get PassThrough-specific context for template rendering.

        Args:
            detection: Detection instance

        Returns:
            Dictionary of additional context variables
        """
        return {
            "detector_type": "passthrough",
            "is_passthrough": True,
            "original_value": detection.detection_data.get("original_value"),
            "variable_code": detection.detection_data.get("variable_code"),
            "variable_name": detection.detection_data.get("variable_name"),
        }
