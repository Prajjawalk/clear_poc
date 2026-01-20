"""Tests for detector implementations."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from django.test import TestCase
from django.utils import timezone

from alert_framework.base_detector import BaseDetector
from alert_framework.detectors.passthrough_detector import PassThroughDetector
from alert_framework.detectors.test_detector import TestDetector
from alert_framework.detectors.zscore_detector import ZScoreDetector
from alert_framework.models import Detector
from alerts.models import ShockType
from data_pipeline.models import Source, Variable, VariableData
from location.models import AdmLevel, Location


class BaseDetectorTest(TestCase):
    """Test cases for BaseDetector abstract class."""

    def test_abstract_methods(self):
        """Test that BaseDetector cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            BaseDetector({})

    def test_concrete_implementation(self):
        """Test that concrete detector can be instantiated."""

        class TestDetectorConcrete(BaseDetector):
            def detect(self, start_date, end_date, **kwargs):
                return []

            def get_configuration_schema(self):
                return {}

            def _load_config(self, **config):
                pass

            def _load_data(self, start_date=None, end_date=None):
                pass

        detector = TestDetectorConcrete({})
        self.assertIsInstance(detector, BaseDetector)
        self.assertEqual(detector.detect(timezone.now(), timezone.now()), [])
        self.assertEqual(detector.get_configuration_schema(), {})


class PassThroughDetectorTest(TestCase):
    """Test cases for PassThroughDetector."""

    def setUp(self):
        """Set up test data."""
        # Create shock type
        self.shock_type = ShockType.objects.create(name="Passthrough")

        # Create source and variable
        self.source = Source.objects.create(
            name="Test Source",
            type="api",
            class_name="test.TestSource"
        )
        self.variable = Variable.objects.create(
            code="test_var",
            name="Test Variable",
            source=self.source,
            type="quantitative",
            period="day",
            adm_level=1
        )

        # Create location structure
        self.admin_level = AdmLevel.objects.create(name="State", code="1")
        self.location = Location.objects.create(
            name="Test Location",
            geo_id="SD_001",
            admin_level=self.admin_level
        )

        # Create detector configuration
        self.detector_config = Detector.objects.create(
            name="Test PassThrough Detector",
            class_name="alert_framework.detectors.passthrough_detector.PassThroughDetector",
            active=True,
            configuration={
                "variable_code": "test_var",
                "admin_level": 1,
                "filters": []
            }
        )

        # Create test data
        self.test_date = datetime(2024, 1, 15).date()
        self.variable_data = VariableData.objects.create(
            variable=self.variable,
            gid=self.location,
            adm_level=self.admin_level,
            start_date=self.test_date,
            end_date=self.test_date,
            value=100.5
        )

        # Initialize detector
        self.detector = PassThroughDetector(self.detector_config)

    def test_initialization(self):
        """Test detector initialization."""
        self.assertEqual(self.detector.variable_code, "test_var")
        self.assertEqual(self.detector.admin_level, 1)
        self.assertEqual(self.detector.filters, [])

    def test_detect_with_data(self):
        """Test detection with available data."""
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        detections = self.detector.detect(start_date, end_date)

        self.assertEqual(len(detections), 1)
        detection = detections[0]

        # Verify detection structure
        self.assertIn("detection_timestamp", detection)
        self.assertIn("locations", detection)
        self.assertIn("confidence_score", detection)
        self.assertIn("shock_type_name", detection)
        self.assertIn("detection_data", detection)

        # Verify detection values
        self.assertEqual(detection["confidence_score"], 1.0)
        self.assertEqual(detection["shock_type_name"], "passthrough")

    def test_get_configuration_schema(self):
        """Test configuration schema generation."""
        schema = self.detector.get_configuration_schema()

        self.assertIsInstance(schema, dict)
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        self.assertIn("required", schema)

        # Check required fields
        self.assertIn("variable_code", schema["required"])

    def test_passes_filters_with_matching_filter(self):
        """Test filter passing with matching filter."""
        self.detector.filters = [
            {"variable_name": "Test Variable", "value": "100.5"}
        ]

        result = self.detector._passes_filters(self.variable_data)
        self.assertTrue(result)

    def test_passes_filters_with_non_matching_filter(self):
        """Test filter failing with non-matching filter."""
        self.detector.filters = [
            {"variable_name": "Test Variable", "value": "200.0"}
        ]

        result = self.detector._passes_filters(self.variable_data)
        self.assertFalse(result)


class ZScoreDetectorTest(TestCase):
    """Test cases for ZScoreDetector."""

    def setUp(self):
        """Set up test data."""
        # Create shock type
        self.shock_type = ShockType.objects.create(name="Anomaly")

        # Create source and variable
        self.source = Source.objects.create(
            name="Test Source",
            type="api",
            class_name="test.TestSource"
        )
        self.variable = Variable.objects.create(
            code="displacement_count",
            name="Displacement Count",
            source=self.source,
            type="quantitative",
            period="day",
            adm_level=2
        )

        # Create location structure
        self.admin_level = AdmLevel.objects.create(name="Locality", code="2")
        self.location = Location.objects.create(
            name="Test Location",
            geo_id="SD_001",
            admin_level=self.admin_level
        )

        # Create detector configuration
        self.detector_config = Detector.objects.create(
            name="Test ZScore Detector",
            class_name="alert_framework.detectors.zscore_detector.ZScoreDetector",
            active=True,
            configuration={
                "variable_code": "displacement_count",
                "zscore_threshold_1": 1.5,
                "zscore_threshold_2": 2.0,
                "zscore_threshold_3": 2.5,
                "zscore_threshold_4": 3.0,
                "window_size": 30,
                "min_baseline_periods": 7,
                "freq": "1D",
                "min_std": 0.1,
                "admin_level": 2,
                "aggregation_func": "mean",
                "min_alert_level": 1
            }
        )

        # Initialize detector
        self.detector = ZScoreDetector(self.detector_config)

    def test_initialization(self):
        """Test detector initialization."""
        self.assertEqual(self.detector.zscore_threshold_1, 1.5)
        self.assertEqual(self.detector.zscore_threshold_2, 2.0)
        self.assertEqual(self.detector.zscore_threshold_3, 2.5)
        self.assertEqual(self.detector.zscore_threshold_4, 3.0)
        self.assertEqual(self.detector.window_size, 30)
        self.assertEqual(self.detector.min_baseline_periods, 7)
        self.assertEqual(self.detector.freq, "1D")
        self.assertEqual(self.detector.min_std, 0.1)
        self.assertEqual(self.detector.variable_code, "displacement_count")
        self.assertEqual(self.detector.admin_level, 2)
        self.assertEqual(self.detector.aggregation_func, "mean")
        self.assertEqual(self.detector.min_alert_level, 1)

    def test_load_data_missing_dates(self):
        """Test data loading with missing date parameters."""
        with self.assertRaises(ValueError) as context:
            self.detector._load_data()

        self.assertIn("start_date and end_date are required", str(context.exception))

        with self.assertRaises(ValueError) as context:
            self.detector._load_data(start_date=datetime(2024, 1, 1))

        self.assertIn("start_date and end_date are required", str(context.exception))

    def test_queryset_to_dataframe(self):
        """Test conversion of Django QuerySet to pandas DataFrame."""
        # Create test data
        base_date = datetime(2024, 1, 1)
        test_data = []

        for i in range(5):
            record = Mock()
            record.start_date = base_date + timedelta(days=i)
            record.end_date = base_date + timedelta(days=i)
            record.gid_id = self.location.id
            record.value = 100 + i * 10
            test_data.append(record)

        # Mock queryset
        mock_queryset = Mock()
        mock_queryset.__iter__ = Mock(return_value=iter(test_data))

        df = self.detector._queryset_to_dataframe(mock_queryset)

        # Verify DataFrame structure
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 5)
        self.assertIn("date", df.columns)
        self.assertIn("unit_id", df.columns)
        self.assertIn("value", df.columns)

        # Verify data types
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["date"]))
        self.assertTrue(pd.api.types.is_numeric_dtype(df["value"]))

        # Verify values
        expected_values = [100, 110, 120, 130, 140]
        self.assertListEqual(df["value"].tolist(), expected_values)

    def test_calculate_zscore_and_alerts(self):
        """Test Z-score calculation and alert generation."""
        # Create test DataFrame with baseline and anomaly
        dates = pd.date_range("2024-01-01", periods=40, freq="D")
        values = [10] * 30 + [50, 60, 70, 80, 90, 100, 110, 120, 130, 140]  # Anomalous spike

        df = pd.DataFrame({
            "date": dates,
            "unit_id": [1] * 40,
            "value": values
        })

        result_df = self.detector._calculate_zscore_and_alerts(df)

        # Verify new columns exist
        expected_columns = [
            "baseline_mean", "baseline_std", "baseline_periods", "zscore",
            "zscore_abs", "alert_level", "alert_level_name", "has_alert",
            "sufficient_baseline", "threshold_exceeded"
        ]
        for col in expected_columns:
            self.assertIn(col, result_df.columns)

        # Verify alert levels for anomalous values
        anomalous_period = result_df.tail(10)  # Last 10 days with high values

        # Should have alerts in the anomalous period
        alerts = anomalous_period[anomalous_period["alert_level"] > 0]
        self.assertTrue(len(alerts) > 0, "Should detect alerts in anomalous period")

        # Verify alert level progression
        highest_alert = result_df["alert_level"].max()
        self.assertGreaterEqual(highest_alert, 1, "Should have at least level 1 alerts")

    def test_generate_multilevel_alerts(self):
        """Test multi-level alert generation based on z-score thresholds."""
        # Create test DataFrame with known z-scores
        df = pd.DataFrame({
            "zscore_abs": [0.5, 1.0, 1.6, 2.1, 2.6, 3.1, 4.0],
            "baseline_periods": [10] * 7  # Sufficient baseline
        })

        result_df = self.detector._generate_multilevel_alerts(df)

        # Verify alert levels
        expected_levels = [0, 0, 1, 2, 3, 4, 4]  # Based on thresholds
        self.assertListEqual(result_df["alert_level"].tolist(), expected_levels)

        # Verify alert level names
        expected_names = ["No Alert", "No Alert", "Low", "Medium", "High", "Critical", "Critical"]
        self.assertListEqual(result_df["alert_level_name"].tolist(), expected_names)

    def test_map_displacement_reason_to_shock_type(self):
        """Test mapping of displacement reasons to shock types."""
        # Test conflict mapping
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("Conflict"), 1)
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("conflict"), 1)
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("Conflict; Natural disaster"), 1)

        # Test natural disaster mapping
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("Natural disaster"), 2)
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("natural disaster"), 2)

        # Test economic reasons mapping
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("Economic reasons"), 4)
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("economic reasons"), 4)

        # Test unknown/default mapping
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type(""), 1)
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("Unknown reason"), 1)
        self.assertEqual(self.detector._map_displacement_reason_to_shock_type("No reason for displacement reported"), 1)

    def test_get_configuration_schema(self):
        """Test configuration schema generation."""
        schema = self.detector.get_configuration_schema()

        self.assertIsInstance(schema, dict)
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        self.assertIn("required", schema)

        # Check required fields
        self.assertIn("variable_code", schema["required"])

        # Check properties structure
        properties = schema["properties"]
        expected_properties = [
            "variable_code", "zscore_threshold_1", "zscore_threshold_2",
            "zscore_threshold_3", "zscore_threshold_4", "window_size",
            "min_baseline_periods", "freq", "min_std", "admin_level",
            "min_alert_level", "aggregation_func"
        ]
        for prop in expected_properties:
            self.assertIn(prop, properties)

    def test_calculate_severity(self):
        """Test severity calculation based on alert level."""
        mock_detection = Mock()

        # Test all alert levels
        test_cases = [
            (0, 1),  # No Alert -> Severity 1
            (1, 2),  # Low -> Severity 2
            (2, 3),  # Medium -> Severity 3
            (3, 4),  # High -> Severity 4
            (4, 5),  # Critical -> Severity 5
        ]

        for alert_level, expected_severity in test_cases:
            mock_detection.detection_data = {"alert_level": alert_level}
            severity = self.detector._calculate_severity(mock_detection)
            self.assertEqual(severity, expected_severity,
                           f"Alert level {alert_level} should map to severity {expected_severity}")


class TestDetectorTest(TestCase):
    """Test cases for TestDetector."""

    def setUp(self):
        """Set up test data."""
        # Create test source and variable
        self.source = Source.objects.create(
            name="Test Source",
            type="api",
            class_name="test.TestSource"
        )
        self.variable = Variable.objects.create(
            code="test_scenario",
            name="Test Scenario",
            source=self.source,
            type="textual",
            period="event",
            adm_level=1
        )

        # Create location
        self.admin_level = AdmLevel.objects.create(name="State", code="1")
        self.location = Location.objects.create(
            name="Test Location",
            geo_id="SD_001",
            admin_level=self.admin_level
        )

        # Create detector configuration
        self.detector_config = Detector.objects.create(
            name="Test Detector",
            class_name="alert_framework.detectors.test_detector.TestDetector",
            active=True,
            configuration={
                "test_source_name": "Test Source",
                "minimum_confidence": 0.7,
                "alert_threshold_multiplier": 1.0
            }
        )

        # Initialize detector
        self.detector = TestDetector(self.detector_config)

    def test_initialization(self):
        """Test detector initialization."""
        self.assertEqual(self.detector.test_source_name, "Test Source")
        self.assertEqual(self.detector.minimum_confidence, 0.7)
        self.assertEqual(self.detector.alert_threshold_multiplier, 1.0)

    def test_scenario_mappings(self):
        """Test scenario to shock type mappings."""
        expected_mappings = {
            "Conflict Escalation": "Conflict",
            "Food Crisis": "Food security"
        }
        self.assertEqual(self.detector.scenario_mappings, expected_mappings)

    def test_detect_no_data(self):
        """Test detection when no data is available."""
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        detections = self.detector.detect(start_date, end_date)
        self.assertEqual(len(detections), 0)

    def test_detect_with_triggering_data(self):
        """Test detection with data that should trigger alerts."""
        # Create test data that should trigger an alert
        VariableData.objects.create(
            variable=self.variable,
            gid=self.location,
            adm_level=self.admin_level,
            start_date=datetime(2024, 1, 15).date(),
            end_date=datetime(2024, 1, 15).date(),
            value=100,
            raw_data={
                "should_trigger_alert": True,
                "scenario": "Conflict Escalation",
                "threshold": 50,
                "variable": "conflict_events",
                "confidence_target": 0.85
            }
        )

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        detections = self.detector.detect(start_date, end_date)

        self.assertEqual(len(detections), 1)
        detection = detections[0]

        # Verify detection structure
        self.assertIn("title", detection)
        self.assertIn("detection_timestamp", detection)
        self.assertIn("locations", detection)
        self.assertIn("confidence_score", detection)
        self.assertIn("shock_type_name", detection)
        self.assertIn("detection_data", detection)

        # Verify detection values
        self.assertEqual(detection["confidence_score"], 0.85)
        self.assertEqual(detection["shock_type_name"], "Conflict")
        self.assertIn("Conflict detected", detection["title"])

    def test_analyze_data_point_insufficient_confidence(self):
        """Test that data points with insufficient confidence are rejected."""
        # Create test data with low confidence
        data_point = VariableData.objects.create(
            variable=self.variable,
            gid=self.location,
            adm_level=self.admin_level,
            start_date=datetime(2024, 1, 15).date(),
            end_date=datetime(2024, 1, 15).date(),
            value=100,
            raw_data={
                "should_trigger_alert": True,
                "scenario": "Conflict Escalation",
                "threshold": 50,
                "variable": "conflict_events",
                "confidence_target": 0.5  # Below minimum_confidence (0.7)
            }
        )

        detection = self.detector._analyze_data_point(data_point)
        self.assertIsNone(detection)

    def test_analyze_data_point_invalid_scenario(self):
        """Test that data points with invalid scenarios are rejected."""
        # Create test data with invalid scenario
        data_point = VariableData.objects.create(
            variable=self.variable,
            gid=self.location,
            adm_level=self.admin_level,
            start_date=datetime(2024, 1, 15).date(),
            end_date=datetime(2024, 1, 15).date(),
            value=100,
            raw_data={
                "should_trigger_alert": True,
                "scenario": "Invalid Scenario",  # Not in scenario_mappings
                "threshold": 50,
                "variable": "conflict_events",
                "confidence_target": 0.85
            }
        )

        detection = self.detector._analyze_data_point(data_point)
        self.assertIsNone(detection)

    def test_get_configuration_schema(self):
        """Test configuration schema generation."""
        schema = self.detector.get_configuration_schema()

        self.assertIsInstance(schema, dict)
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)

        # Check properties
        properties = schema["properties"]
        self.assertIn("test_source_name", properties)
        self.assertIn("minimum_confidence", properties)
        self.assertIn("alert_threshold_multiplier", properties)

        # Verify property constraints
        self.assertEqual(properties["minimum_confidence"]["minimum"], 0.0)
        self.assertEqual(properties["minimum_confidence"]["maximum"], 1.0)

    def test_calculate_severity(self):
        """Test severity calculation."""
        mock_detection = Mock()
        mock_detection.confidence_score = 0.85

        # Test Conflict Escalation scenario
        mock_detection.detection_data = {"scenario": "Conflict Escalation"}
        severity = self.detector._calculate_severity(mock_detection)
        self.assertEqual(severity, 5)  # High confidence conflict should be severity 5

        # Test Food Crisis scenario
        mock_detection.detection_data = {"scenario": "Food Crisis"}
        severity = self.detector._calculate_severity(mock_detection)
        self.assertEqual(severity, 4)  # High confidence food crisis should be severity 4

        # Test with lower confidence
        mock_detection.confidence_score = 0.75
        mock_detection.detection_data = {"scenario": "Conflict Escalation"}
        severity = self.detector._calculate_severity(mock_detection)
        self.assertEqual(severity, 4)  # Reduced by 1 for lower confidence (< 0.8)

        # Test with low confidence
        mock_detection.confidence_score = 0.6
        mock_detection.detection_data = {"scenario": "Conflict Escalation"}
        severity = self.detector._calculate_severity(mock_detection)
        self.assertEqual(severity, 4)  # Reduced by 1 for low confidence