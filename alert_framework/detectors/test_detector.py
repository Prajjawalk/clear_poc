"""Test Detector for complete pipeline testing."""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from alert_framework.base_detector import BaseDetector
from data_pipeline.models import VariableData

if TYPE_CHECKING:
    from alert_framework.models import Detection

logger = logging.getLogger(__name__)


class TestDetector(BaseDetector):
    """
    Test detector for integration testing.

    Scans data from the test source and generates alerts
    when specific test conditions are met.
    """

    def __init__(self, detector_config):
        """Initialize test detector."""
        super().__init__(detector_config)
        self.scenario_mappings = {"Conflict Escalation": "Conflict", "Food Crisis": "Food security"}
        # Load configuration immediately
        self._load_config(**detector_config.configuration)

    def detect(self, start_date: datetime, end_date: datetime, **kwargs) -> list[dict]:
        """
        Analyze test data and return detections.

        Args:
            start_date: Analysis window start
            end_date: Analysis window end
            **kwargs: Additional parameters

        Returns:
            List of detection dictionaries
        """
        try:
            self.log_detection("Starting test detection", start_date=start_date.isoformat(), end_date=end_date.isoformat())

            # Load data from test source
            data = self._load_data(start_date, end_date)

            if not data.exists():
                self.log_detection("No test data found in time window")
                return []

            detections = []

            for data_point in data:
                detection = self._analyze_data_point(data_point)
                if detection:
                    detections.append(detection)

            self.log_detection("Test detection complete", detections_found=len(detections), data_points_analyzed=data.count())

            return detections

        except Exception as e:
            self.log_detection(f"Error in test detection: {str(e)}", level="error")
            return []

    def _load_config(self, **config):
        """Load detector configuration."""
        self.test_source_name = config.get("test_source_name", "Test Source")
        self.minimum_confidence = config.get("minimum_confidence", 0.7)
        self.alert_threshold_multiplier = config.get("alert_threshold_multiplier", 1.0)

    def _load_data(self, start_date=None, end_date=None):
        """Load test data from the specified time window."""
        try:
            # Get data from test source
            queryset = VariableData.objects.filter(variable__source__name__icontains="test source").select_related("variable", "variable__source", "gid")

            if start_date:
                queryset = queryset.filter(end_date__gte=start_date.date())
            if end_date:
                queryset = queryset.filter(end_date__lte=end_date.date())

            return queryset.order_by("-end_date")

        except Exception as e:
            self.log_detection(f"Error loading test data: {str(e)}", level="error")
            return VariableData.objects.none()

    def _analyze_data_point(self, data_point: VariableData) -> dict | None:
        """Analyze a single data point for alert conditions."""
        try:
            metadata = data_point.raw_data or {}

            # Check if this should trigger an alert
            should_trigger = metadata.get("should_trigger_alert", False)
            self.log_detection(f"Analyzing data point: should_trigger={should_trigger}, scenario={metadata.get('scenario', 'unknown')}", value=data_point.value)

            if not should_trigger:
                return None

            scenario = metadata.get("scenario")
            if not scenario or scenario not in self.scenario_mappings:
                self.log_detection(f"Scenario validation failed: scenario={scenario}, valid_scenarios={list(self.scenario_mappings.keys())}")
                return None

            self.log_detection(f"Scenario validation passed: {scenario}")

            # Get values from metadata and data point
            threshold = metadata.get("threshold", 0)
            value = data_point.value
            variable = metadata.get("variable", "")

            # Use the confidence_target from test data if available
            # This allows predictable testing of different confidence scenarios
            confidence_target = metadata.get("confidence_target")

            if confidence_target is not None:
                # Use the exact confidence from test data for predictable testing
                confidence = confidence_target
                self.log_detection(f"Using test confidence target: {confidence}")
            else:
                # Fallback to calculated confidence for non-test data
                if variable == "resource_availability":
                    # For resource availability, lower values = higher confidence
                    confidence = max(0.0, min(1.0, (threshold - value) / threshold))
                else:
                    # For other variables, higher values = higher confidence
                    if threshold > 0:
                        ratio = value / threshold
                        confidence = min(1.0, max(0.0, (ratio - 1.0) * 0.5 + 0.5))
                    else:
                        confidence = 0.8  # Default confidence

            self.log_detection(f"Confidence calculation: confidence={confidence:.3f}, minimum={self.minimum_confidence}")

            if confidence < self.minimum_confidence:
                self.log_detection(f"Confidence too low: {confidence:.3f} < {self.minimum_confidence}")
                return None

            shock_type_name = self.scenario_mappings[scenario]

            self.log_detection(f"Detection found for {scenario}", location=data_point.gid.name, value=value, confidence=confidence)

            return {
                "title": f"{shock_type_name} detected in {data_point.gid.name}",
                "detection_timestamp": timezone.now(),
                "locations": [data_point.gid],
                "confidence_score": confidence,
                "shock_type_name": shock_type_name,
                "detection_data": {
                    "scenario": scenario,
                    "trigger_value": value,
                    "threshold": threshold,
                    "variable": variable,
                    "original_text": data_point.text,
                    "source_data_point_id": data_point.id,
                },
            }

        except Exception as e:
            self.log_detection(f"Error analyzing data point {data_point.id}: {str(e)}", level="error")
            return None

    def get_configuration_schema(self) -> dict:
        """Return JSON schema for configuration validation."""
        return {
            "type": "object",
            "properties": {
                "test_source_name": {"type": "string", "description": "Name of the test source", "default": "Test Source"},
                "minimum_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Minimum confidence score for detection", "default": 0.8},
                "alert_threshold_multiplier": {"type": "number", "minimum": 0.1, "maximum": 5.0, "description": "Multiplier for alert thresholds", "default": 1.0},
            },
            "additionalProperties": False,
        }

    def _get_detector_specific_context(self, detection: "Detection") -> dict:
        """Get detector-specific context for template rendering."""
        detection_data = detection.detection_data or {}

        return {
            "test_scenario": detection_data.get("scenario", "Unknown"),
            "trigger_value": detection_data.get("trigger_value", 0),
            "threshold_value": detection_data.get("threshold", 0),
            "test_variable": detection_data.get("variable", "unknown"),
            "original_text": detection_data.get("original_text", ""),
            "is_test_alert": True,
        }

    def _calculate_severity(self, detection: "Detection") -> int:
        """Calculate severity based on test scenario and confidence."""
        detection_data = detection.detection_data or {}
        scenario = detection_data.get("scenario", "")
        confidence = detection.confidence_score or 0.5

        # Base severity by scenario
        base_severity = {
            "Conflict Escalation": 5,  # High severity for conflict
            "Food Crisis": 4,  # High severity for food security
        }.get(scenario, 3)

        # Adjust by confidence
        if confidence >= 0.9:
            return min(5, base_severity + 1)
        elif confidence >= 0.8:
            return base_severity
        else:
            return max(1, base_severity - 1)

    def _calculate_validity_period(self, detection: "Detection") -> datetime:
        """Calculate alert validity for test alerts."""
        # Test alerts are valid for 24 hours
        return timezone.now() + timedelta(hours=24)

    def _get_data_source_reference(self, detection: "Detection") -> str:
        """Get data source reference for test alerts."""
        return "Test Source"
