"""Threshold detector that compares variable values against configurable thresholds."""

from datetime import datetime, time
from typing import Any

from django.utils import timezone

from alert_framework.base_detector import BaseDetector


class ThresholdDetector(BaseDetector):
    """Detector that triggers when variable values cross configurable thresholds.

    Supports comparison operators: gt, lt, gte, lte, eq, ne
    """

    OPERATORS = {
        "gt": lambda val, threshold: val > threshold,
        "lt": lambda val, threshold: val < threshold,
        "gte": lambda val, threshold: val >= threshold,
        "lte": lambda val, threshold: val <= threshold,
        "eq": lambda val, threshold: val == threshold,
        "ne": lambda val, threshold: val != threshold,
    }

    OPERATOR_NAMES = {
        "gt": "greater than",
        "lt": "less than",
        "gte": "greater than or equal to",
        "lte": "less than or equal to",
        "eq": "equal to",
        "ne": "not equal to",
    }

    def __init__(self, detector_config):
        """Initialize Threshold detector.

        Args:
            detector_config: Detector model instance with configuration
        """
        super().__init__(detector_config)
        self._load_config()

    def _load_config(self, **config):
        """Initialize the detector configuration."""
        # Get configuration from the detector model
        config_dict = self.config.configuration or {}
        config_dict.update(config)

        # Required parameters
        self.variable_code = config_dict.get("variable_code")
        self.threshold_value = config_dict.get("threshold_value")
        self.operator = config_dict.get("operator", "gt")

        # Optional parameters
        self.admin_level = config_dict.get("admin_level", None)
        self.use_dynamic_confidence = config_dict.get("use_dynamic_confidence", True)
        self.confidence_score = config_dict.get("confidence_score", 1.0)  # Used only if dynamic is False
        self.use_latest_data = config_dict.get("use_latest_data", False)  # Ignore date range and use latest data

        # Validate operator
        if self.operator not in self.OPERATORS:
            self.logger.error(
                f"Invalid operator: {self.operator}. Must be one of: {', '.join(self.OPERATORS.keys())}"
            )
            self.operator = "gt"

        # Validate and convert threshold value to numeric
        if self.threshold_value is not None:
            try:
                self.threshold_value = float(self.threshold_value)
            except (TypeError, ValueError):
                self.logger.error(f"Invalid threshold_value: {self.threshold_value}. Must be numeric.")
                self.threshold_value = None

        # Validate and convert admin_level to int if provided
        if self.admin_level is not None:
            try:
                self.admin_level = int(self.admin_level)
            except (TypeError, ValueError):
                self.logger.error(f"Invalid admin_level: {self.admin_level}. Must be an integer.")
                self.admin_level = None

    def _load_data(self, start_date=None, end_date=None):
        """Load data from the configured data source.

        Args:
            start_date: Start date for data retrieval (ignored if use_latest_data is True)
            end_date: End date for data retrieval (ignored if use_latest_data is True)

        Returns:
            QuerySet of VariableData records
        """
        if not self.variable_code:
            self.logger.warning("No variable_code configured for ThresholdDetector")
            return None

        # If use_latest_data is enabled, ignore date range and get the most recent data
        if self.use_latest_data:
            return self.get_variable_data(
                variable_code=self.variable_code,
                start_date=None,
                end_date=None,
                admin_level=self.admin_level,
            )
        else:
            return self.get_variable_data(
                variable_code=self.variable_code,
                start_date=start_date,
                end_date=end_date,
                admin_level=self.admin_level,
            )

    def _calculate_dynamic_confidence(self, value: float, threshold: float, operator: str) -> float:
        """Calculate confidence score based on relative difference from threshold.

        Args:
            value: Actual value
            threshold: Threshold value
            operator: Comparison operator

        Returns:
            float: Confidence score between 0 and 1
        """
        # For equality checks, use binary confidence (1.0 if matches, not used otherwise)
        if operator in ["eq", "ne"]:
            return 1.0

        # Calculate relative difference
        if threshold == 0:
            # Avoid division by zero - use absolute difference
            if value == 0:
                relative_diff = 0.0
            else:
                # When threshold is 0, any non-zero value is significant
                relative_diff = min(abs(value), 1.0)
        else:
            relative_diff = abs(value - threshold) / abs(threshold)

        # Confidence increases with distance from threshold
        # Use a sigmoid-like function to map relative difference to confidence
        # - Small differences (just crossing threshold): lower confidence
        # - Large differences (far from threshold): higher confidence

        # Cap relative difference at 1.0 (100% difference) for confidence calculation
        capped_diff = min(relative_diff, 1.0)

        # Map to confidence: 0% diff = 0.5 confidence, 100% diff = 1.0 confidence
        # This gives a range of [0.5, 1.0] for crossing the threshold
        confidence = 0.5 + (capped_diff * 0.5)

        return round(confidence, 3)

    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict[str, Any]]:
        """Detect datapoints that cross the configured threshold.

        Args:
            start_date: Analysis window start
            end_date: Analysis window end
            **kwargs: Additional parameters (ignored)

        Returns:
            List of detection dictionaries for datapoints crossing the threshold
        """
        # Ensure threshold_value is float (defensive programming)
        if self.threshold_value is not None and not isinstance(self.threshold_value, (int, float)):
            try:
                self.threshold_value = float(self.threshold_value)
            except (TypeError, ValueError):
                self.log_detection(
                    f"Invalid threshold_value type: {type(self.threshold_value).__name__}",
                    level="error"
                )
                return []

        self.log_detection(
            "Starting Threshold detection",
            start_date=start_date if not self.use_latest_data else "LATEST",
            end_date=end_date if not self.use_latest_data else "LATEST",
            variable_code=self.variable_code,
            operator=self.operator,
            threshold_value=self.threshold_value,
            use_latest_data=self.use_latest_data
        )

        # Validate configuration
        if self.threshold_value is None:
            self.log_detection("No threshold_value configured", level="error")
            return []

        # Load data for the specified time window
        data = self._load_data(start_date=start_date, end_date=end_date)

        if not data:
            self.log_detection("No data found for Threshold detection", level="warning")
            return []

        detections = []
        data_count = data.count()

        self.log_detection(f"Processing {data_count} datapoints for Threshold detection")

        # Get the comparison function
        comparison_func = self.OPERATORS[self.operator]

        for record in data:
            # Try to convert value to numeric
            try:
                numeric_value = float(record.value)
            except (TypeError, ValueError):
                self.logger.warning(
                    f"Skipping non-numeric value for {record.variable.code}: {record.value}"
                )
                continue

            # Check if value crosses threshold
            if comparison_func(numeric_value, self.threshold_value):
                # Calculate confidence score
                if self.use_dynamic_confidence:
                    confidence = self._calculate_dynamic_confidence(
                        numeric_value, self.threshold_value, self.operator
                    )
                else:
                    confidence = self.confidence_score

                # Create detection
                locations = []
                if record.gid:
                    locations = [record.gid.id]  # Pass just the ID, not a dict

                # Convert date to timezone-aware datetime if needed
                detection_timestamp = record.start_date
                if isinstance(detection_timestamp, datetime):
                    if timezone.is_naive(detection_timestamp):
                        detection_timestamp = timezone.make_aware(detection_timestamp)
                else:
                    # Convert date to datetime at midnight in the current timezone
                    detection_timestamp = timezone.make_aware(
                        datetime.combine(detection_timestamp, time.min)
                    )

                # Generate a unique title including location name and value
                location_name = record.gid.name if record.gid else "Unknown"
                # Round value to avoid floating point precision in title
                rounded_value = int(round(numeric_value))
                detection_title = f"{record.variable.name}: {rounded_value} in {location_name}"

                detection = {
                    "title": detection_title,
                    "detection_timestamp": detection_timestamp,
                    "locations": locations,
                    "confidence_score": confidence,
                    "shock_type_name": "Natural disasters",  # Use existing shock type for floods
                    "detection_data": {
                        "variable_code": record.variable.code,
                        "variable_name": record.variable.name,
                        "value": numeric_value,
                        "threshold_value": self.threshold_value,
                        "operator": self.operator,
                        "operator_name": self.OPERATOR_NAMES[self.operator],
                        "start_date": record.start_date.isoformat() if record.start_date else None,
                        "end_date": record.end_date.isoformat() if record.end_date else None,
                        "location_name": record.gid.name if record.gid else None,
                        "admin_level": record.adm_level.code if record.adm_level else None,
                        "detector_type": "threshold",
                    },
                }
                detections.append(detection)

        self.log_detection(
            "Threshold detection completed",
            total_detections=len(detections),
            data_points_processed=data_count,
        )

        return detections

    def get_configuration_schema(self) -> dict[str, Any]:
        """Return JSON schema for Threshold detector configuration.

        Returns:
            Dictionary containing the JSON schema
        """
        return {
            "type": "object",
            "properties": {
                "variable_code": {
                    "type": "string",
                    "description": "Code of the variable to monitor",
                    "minLength": 1,
                },
                "threshold_value": {
                    "type": "number",
                    "description": "Threshold value for comparison",
                },
                "operator": {
                    "type": "string",
                    "description": "Comparison operator",
                    "enum": ["gt", "lt", "gte", "lte", "eq", "ne"],
                    "default": "gt",
                },
                "admin_level": {
                    "type": ["integer", "null"],
                    "description": "Administrative level filter (optional)",
                    "minimum": 0,
                },
                "use_dynamic_confidence": {
                    "type": "boolean",
                    "description": "Calculate confidence based on relative difference from threshold (default: true)",
                    "default": True,
                },
                "confidence_score": {
                    "type": "number",
                    "description": "Fixed confidence score when use_dynamic_confidence is false (0-1)",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 1.0,
                },
                "use_latest_data": {
                    "type": "boolean",
                    "description": "Ignore date range and always check the most recently fetched data (default: false)",
                    "default": False,
                },
            },
            "required": ["variable_code", "threshold_value"],
            "additionalProperties": False,
            "title": "Threshold Detector Configuration",
            "description": "Configuration for Threshold detector that triggers when values cross specified thresholds using comparison operators (gt, lt, gte, lte, eq, ne). Can be configured to check latest data regardless of date range.",
        }

    def _calculate_severity(self, detection) -> int:
        """Calculate severity based on how far the value exceeds the threshold.

        Args:
            detection: Detection instance

        Returns:
            int: Severity level between 1 and 5
        """
        value = detection.detection_data.get("value")
        threshold = detection.detection_data.get("threshold_value")
        operator = detection.detection_data.get("operator")

        if value is None or threshold is None:
            return 3  # Default medium severity

        # For equality checks, use default severity
        if operator in ["eq", "ne"]:
            return 3

        # Calculate relative difference
        if threshold == 0:
            # Avoid division by zero
            diff_percent = abs(value - threshold) * 100
        else:
            diff_percent = abs((value - threshold) / threshold) * 100

        # Map percentage difference to severity
        if diff_percent >= 100:
            return 5  # Critical: 100%+ difference
        elif diff_percent >= 50:
            return 4  # High: 50-100% difference
        elif diff_percent >= 20:
            return 3  # Medium: 20-50% difference
        elif diff_percent >= 10:
            return 2  # Low: 10-20% difference
        else:
            return 1  # Minimal: <10% difference

    def _get_detector_specific_context(self, detection) -> dict[str, Any]:
        """Get Threshold-specific context for template rendering.

        Args:
            detection: Detection instance

        Returns:
            Dictionary of additional context variables
        """
        return {
            "detector_type": "threshold",
            "is_threshold": True,
            "value": detection.detection_data.get("value"),
            "threshold_value": detection.detection_data.get("threshold_value"),
            "operator": detection.detection_data.get("operator"),
            "operator_name": detection.detection_data.get("operator_name"),
            "variable_code": detection.detection_data.get("variable_code"),
            "variable_name": detection.detection_data.get("variable_name"),
        }
