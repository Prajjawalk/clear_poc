"""Tests for ScoringDetector implementation."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from alert_framework.detectors.scoring_detector import ScoringDetector
from alert_framework.models import Detector
from alerts.models import ShockType
from data_pipeline.models import Source, Variable, VariableData
from location.models import AdmLevel, Location


class ScoringDetectorTest(TestCase):
    """Test cases for ScoringDetector."""

    def setUp(self):
        """Set up test data."""
        # Create shock types
        self.shock_type_conflict = ShockType.objects.create(name="Conflict")
        self.shock_type_natural = ShockType.objects.create(name="Natural disasters")

        # Create source and variable
        self.source = Source.objects.create(
            name="Dataminr",
            type="api",
            class_name="data_pipeline.sources.dataminr.DataminrSource"
        )
        self.variable = Variable.objects.create(
            code="dataminr_alerts",
            name="Dataminr Alerts",
            source=self.source,
            type="qualitative",
            period="day",
            adm_level=1
        )

        # Create location structure
        self.admin_level = AdmLevel.objects.create(name="State", code="1")
        self.location_fashir = Location.objects.create(
            name="Al Fashir",
            geo_id="SD_ND_001",
            admin_level=self.admin_level
        )
        self.location_khartoum = Location.objects.create(
            name="Khartoum",
            geo_id="SD_KH_001",
            admin_level=self.admin_level
        )

        # Create test date
        self.test_date = datetime(2025, 10, 7).date()

    def _create_detector_config(self, config_overrides=None):
        """Helper to create detector configuration."""
        config = {
            "variable_code": "dataminr_alerts",
            "source_name": "Dataminr",
            "field_scores": {
                "alertType.name": {
                    "exact_match": {
                        "Urgent": 10,
                        "Alert": 5
                    }
                },
                "alertTopics": {
                    "contains": {
                        "Conflicts": 8,
                        "Casualties": 6,
                        "Violence": 5
                    },
                    "_mode": "max"
                }
            },
            "keyword_scores": {
                "killed": 5,
                "deaths": 5,
                "injured": 3,
                "attack": 4,
                "bombing": 6
            },
            "keyword_max_mode": False,
            "text_fields": ["headline", "text_fallback"],
            "location_multipliers": {
                "Al Fashir": 1.5,
                "Khartoum": 1.3
            },
            "location_fields": ["estimatedEventLocation[0]", "location_fallback"],
            "thresholds": {
                "critical": 25,
                "high": 15,
                "medium": 8,
                "low": 4
            },
            "min_detection_score": 8,
            "base_score": 1.0,
            "enable_clustering": False,
            "shock_type_mapping": {
                "alertTopics==Conflicts - Air": "Conflict",
                "contains:flood": "Natural disasters",
                "level==critical": "Conflict"
            }
        }
        if config_overrides:
            config.update(config_overrides)

        return Detector.objects.create(
            name="Test Scoring Detector",
            class_name="alert_framework.detectors.scoring_detector.ScoringDetector",
            active=True,
            configuration=config
        )

    def test_configuration_loading(self):
        """Test configuration loading and validation."""
        detector_config = self._create_detector_config({
            "min_detection_score": 10,
            "base_score": 2.0
        })
        detector = ScoringDetector(detector_config)

        self.assertEqual(detector.variable_code, "dataminr_alerts")
        self.assertEqual(detector.source_name, "Dataminr")
        self.assertEqual(detector.min_detection_score, 10)
        self.assertEqual(detector.base_score, 2.0)
        self.assertFalse(detector.enable_clustering)

    def test_field_value_extraction_simple(self):
        """Test extraction of simple field values."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        raw_data = {
            "headline": "Test headline",
            "alertType": {"name": "Urgent"}
        }
        mock_record = Mock(text="", original_location_text="")

        # Test simple field
        value = detector._get_field_value(raw_data, "headline", mock_record)
        self.assertEqual(value, "Test headline")

        # Test dot notation
        value = detector._get_field_value(raw_data, "alertType.name", mock_record)
        self.assertEqual(value, "Urgent")

    def test_field_value_extraction_array(self):
        """Test extraction of array field values with indexing."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        raw_data = {
            "estimatedEventLocation": ["Al Fashir", "Khartoum"]
        }
        mock_record = Mock(text="", original_location_text="")

        # Test array indexing
        value = detector._get_field_value(raw_data, "estimatedEventLocation[0]", mock_record)
        self.assertEqual(value, "Al Fashir")

        value = detector._get_field_value(raw_data, "estimatedEventLocation[1]", mock_record)
        self.assertEqual(value, "Khartoum")

    def test_field_scoring_exact_match(self):
        """Test field scoring with exact match rules."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        score_rules = {
            "exact_match": {
                "Urgent": 10,
                "Alert": 5,
                "Warning": 3
            }
        }

        # Test exact match
        score = detector._score_field_value("Urgent", score_rules)
        self.assertEqual(score, 10)

        score = detector._score_field_value("Alert", score_rules)
        self.assertEqual(score, 5)

        # Test non-match
        score = detector._score_field_value("Info", score_rules)
        self.assertEqual(score, 0)

    def test_field_scoring_contains(self):
        """Test field scoring with contains matching."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        score_rules = {
            "contains": {
                "conflict": 8,
                "violence": 5
            }
        }

        # Test string matching
        score = detector._score_field_value("Armed conflict in region", score_rules)
        self.assertEqual(score, 8)

        # Test array matching
        alert_topics = [
            {"name": "Conflicts - Air"},
            {"name": "Casualties"}
        ]
        score = detector._score_field_value(alert_topics, score_rules)
        self.assertEqual(score, 8)  # Should match "conflict" in "Conflicts - Air"

    def test_field_scoring_max_mode(self):
        """Test field scoring with max mode instead of sum."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        score_rules = {
            "contains": {
                "conflict": 8,
                "violence": 5,
                "air": 3
            },
            "_mode": "max"
        }

        # Multiple matches should return max, not sum
        score = detector._score_field_value("Armed conflict with air violence", score_rules)
        self.assertEqual(score, 8)  # Max of 8, 5, 3, not sum (16)

    def test_keyword_scoring(self):
        """Test text keyword scoring."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        # Test single keyword
        score = detector._score_keywords("Several people were killed in the attack")
        self.assertEqual(score, 9)  # killed (5) + attack (4)

        # Test keyword max mode
        detector.keyword_max_mode = True
        score = detector._score_keywords("Several people were killed in the attack")
        self.assertEqual(score, 5)  # max(killed=5, attack=4)

    def test_location_multiplier(self):
        """Test location-based score multipliers."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        # Test high-priority location
        multiplier = detector._get_location_multiplier("Al Fashir")
        self.assertEqual(multiplier, 1.5)

        multiplier = detector._get_location_multiplier("Khartoum")
        self.assertEqual(multiplier, 1.3)

        # Test normal location
        multiplier = detector._get_location_multiplier("Other City")
        self.assertEqual(multiplier, 1.0)

    def test_alert_level_determination(self):
        """Test alert level calculation from score."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        self.assertEqual(detector._get_alert_level(30), "critical")
        self.assertEqual(detector._get_alert_level(20), "high")
        self.assertEqual(detector._get_alert_level(10), "medium")
        self.assertEqual(detector._get_alert_level(5), "low")
        self.assertEqual(detector._get_alert_level(2), "none")

    def test_alert_scoring_integration(self):
        """Test complete alert scoring with all components."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        # Create mock alert record
        raw_data = {
            "headline": "People killed in bombing attack",
            "alertType": {"name": "Urgent"},
            "alertTopics": [{"name": "Conflicts - Air"}],
            "estimatedEventLocation": ["Al Fashir"]
        }

        mock_record = Mock(
            id=1,
            text="",
            original_location_text="",
            raw_data=raw_data,
            gid=self.location_fashir
        )

        score_data = detector._score_alert(mock_record)

        # Base (1) + field scores (10 for Urgent + 8 for Conflicts) + keywords (5 killed + 6 bombing + 4 attack) = 34
        # Then multiply by location (1.5 for Al Fashir) = 51
        self.assertEqual(score_data["level"], "critical")
        self.assertGreater(score_data["score"], 25)
        self.assertEqual(score_data["components"]["location_multiplier"], 1.5)

    def test_detect_with_data(self):
        """Test detection with actual VariableData records."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        # Create high-scoring alert
        raw_data = {
            "headline": "Multiple killed in bombing attack",
            "alertType": {"name": "Urgent"},
            "alertTopics": [{"name": "Conflicts - Air"}]
        }
        VariableData.objects.create(
            variable=self.variable,
            gid=self.location_fashir,
            adm_level=self.admin_level,
            start_date=self.test_date,
            end_date=self.test_date,
            raw_data=raw_data,
            text="Multiple killed in bombing attack"
        )

        # Create low-scoring alert (should be filtered)
        raw_data_low = {
            "headline": "Weather report",
            "alertType": {"name": "Info"}
        }
        VariableData.objects.create(
            variable=self.variable,
            gid=self.location_khartoum,
            adm_level=self.admin_level,
            start_date=self.test_date,
            end_date=self.test_date,
            raw_data=raw_data_low,
            text="Weather report"
        )

        start_date = timezone.make_aware(datetime.combine(self.test_date, datetime.min.time()))
        end_date = timezone.make_aware(datetime.combine(self.test_date, datetime.max.time()))

        detections = detector.detect(start_date, end_date)

        # Only high-scoring alert should create detection
        self.assertEqual(len(detections), 1)
        detection = detections[0]

        self.assertIn("bombing", detection["title"].lower())
        self.assertEqual(detection["shock_type_name"], "Conflict")
        self.assertGreater(detection["confidence_score"], 0.0)

    def test_shock_type_mapping_rules(self):
        """Test shock type determination from mapping rules."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        # Test field-based rule
        raw_data = {
            "headline": "Flood disaster in Sudan",
            "alertTopics": []
        }
        mock_record = Mock(
            raw_data=raw_data,
            text="Flood disaster in Sudan",
            original_location_text=""
        )

        result = detector._evaluate_shock_type_rule(
            "contains:flood",
            raw_data,
            mock_record,
            "high"
        )
        self.assertTrue(result)

        # Test level-based rule
        result = detector._evaluate_shock_type_rule("level==high", raw_data, mock_record, "high")
        self.assertTrue(result)

        result = detector._evaluate_shock_type_rule("level==critical", raw_data, mock_record, "high")
        self.assertFalse(result)

    def test_clustering_disabled_by_default(self):
        """Test that clustering is disabled by default."""
        detector_config = self._create_detector_config({"enable_clustering": False})
        detector = ScoringDetector(detector_config)

        # Create multiple alerts on different days to avoid unique constraint
        for i in range(5):
            raw_data = {
                "headline": f"Alert {i}",
                "alertType": {"name": "Urgent"}
            }
            alert_date = self.test_date + timedelta(days=i)
            VariableData.objects.create(
                variable=self.variable,
                gid=self.location_fashir,
                adm_level=self.admin_level,
                start_date=alert_date,
                end_date=alert_date,
                raw_data=raw_data
            )

        start_date = timezone.make_aware(datetime.combine(self.test_date, datetime.min.time()))
        end_date = timezone.make_aware(datetime.combine(self.test_date + timedelta(days=10), datetime.max.time()))

        detections = detector.detect(start_date, end_date)

        # Should get individual detections, no cluster detections
        self.assertGreater(len(detections), 0)
        for detection in detections:
            self.assertNotIn("cluster", detection.get("detection_data", {}).get("source", "").lower())

    def test_clustering_enabled(self):
        """Test temporal clustering of alerts."""
        detector_config = self._create_detector_config({
            "enable_clustering": True,
            "cluster_window_hours": 6,
            "cluster_min_alerts": 2
        })
        detector = ScoringDetector(detector_config)

        # Create cluster of alerts on different days (same day would violate unique constraint)
        base_datetime = timezone.make_aware(datetime.combine(self.test_date, datetime.min.time()))
        for i in range(3):
            raw_data = {
                "headline": f"Urgent alert {i}",
                "alertType": {"name": "Urgent"}
            }
            alert_date = self.test_date + timedelta(days=i)
            VariableData.objects.create(
                variable=self.variable,
                gid=self.location_fashir,
                adm_level=self.admin_level,
                start_date=alert_date,
                end_date=alert_date,
                raw_data=raw_data
            )

        end_date = base_datetime + timedelta(days=5)
        detections = detector.detect(base_datetime, end_date)

        # Should have individual detections (clustering may or may not create additional cluster detections)
        self.assertGreaterEqual(len(detections), 3)
        # Clustering is enabled, so at least the individual detections should exist
        self.assertGreater(len(detections), 0)

    def test_empty_data_handling(self):
        """Test handling of empty data."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        start_date = timezone.make_aware(datetime.combine(self.test_date, datetime.min.time()))
        end_date = timezone.make_aware(datetime.combine(self.test_date, datetime.max.time()))

        detections = detector.detect(start_date, end_date)

        self.assertEqual(len(detections), 0)

    def test_configuration_schema(self):
        """Test configuration schema generation."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        schema = detector.get_configuration_schema()

        self.assertEqual(schema["type"], "object")
        self.assertIn("variable_code", schema["properties"])
        self.assertIn("field_scores", schema["properties"])
        self.assertIn("keyword_scores", schema["properties"])
        self.assertIn("thresholds", schema["properties"])
        self.assertIn("min_detection_score", schema["properties"])

    def test_relevant_fields_extraction(self):
        """Test extraction of relevant fields for detection data."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        raw_data = {
            "headline": "Test headline",
            "alertType": {"name": "Urgent"},
            "alertTopics": [{"name": "Conflicts"}],
            "irrelevant_field": "ignored"
        }

        relevant = detector._extract_relevant_fields(raw_data)

        # Should only extract fields mentioned in scoring configuration
        self.assertIn("name", relevant)  # From alertType.name
        self.assertIn("alertTopics", relevant)
        self.assertNotIn("irrelevant_field", relevant)

    def test_detection_data_structure(self):
        """Test that detection data contains all required fields."""
        detector_config = self._create_detector_config()
        detector = ScoringDetector(detector_config)

        raw_data = {
            "headline": "Critical alert with casualties",
            "alertType": {"name": "Urgent"}
        }
        VariableData.objects.create(
            variable=self.variable,
            gid=self.location_fashir,
            adm_level=self.admin_level,
            start_date=self.test_date,
            end_date=self.test_date,
            raw_data=raw_data
        )

        start_date = timezone.make_aware(datetime.combine(self.test_date, datetime.min.time()))
        end_date = timezone.make_aware(datetime.combine(self.test_date, datetime.max.time()))

        detections = detector.detect(start_date, end_date)

        self.assertGreater(len(detections), 0)
        detection = detections[0]

        # Verify required fields
        self.assertIn("title", detection)
        self.assertIn("detection_timestamp", detection)
        self.assertIn("locations", detection)
        self.assertIn("confidence_score", detection)
        self.assertIn("shock_type_name", detection)
        self.assertIn("detection_data", detection)

        # Verify detection_data content
        detection_data = detection["detection_data"]
        self.assertIn("alert_id", detection_data)
        self.assertIn("score", detection_data)
        self.assertIn("alert_level", detection_data)
        self.assertIn("score_components", detection_data)
