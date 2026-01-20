"""Tests for alert framework serializers."""

from django.core.paginator import Paginator
from django.test import TestCase
from django.utils import timezone

from alert_framework.models import AlertTemplate, Detection, Detector
from alert_framework.serializers import (
    AlertTemplateSerializer,
    DetectionSerializer,
    DetectorSerializer,
    LocationSerializer,
    PaginationSerializer,
)
from alerts.models import ShockType
from location.models import AdmLevel, Location


class DetectorSerializerTest(TestCase):
    """Test cases for DetectorSerializer."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(
            name="Test Detector",
            description="A test detector for serialization",
            class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector",
            active=True,
            configuration={"threshold_multiplier": 2.0, "baseline_days": 30},
            run_count=5,
            detection_count=10,
        )

        # Create some detections for stats
        shock_type = ShockType.objects.create(name="Conflict")
        Detection.objects.create(
            detector=self.detector, title="Test Detection 1", detection_timestamp=timezone.now(), confidence_score=0.8, shock_type=shock_type, status="pending"
        )
        Detection.objects.create(
            detector=self.detector, title="Test Detection 2", detection_timestamp=timezone.now(), confidence_score=0.9, shock_type=shock_type, status="processed"
        )

    def test_basic_serialization(self):
        """Test basic detector serialization."""
        result = DetectorSerializer.to_dict(self.detector)

        self.assertEqual(result["id"], self.detector.id)
        self.assertEqual(result["name"], "Test Detector")
        self.assertEqual(result["description"], "A test detector for serialization")
        self.assertTrue(result["active"])
        self.assertIn("configuration", result)
        self.assertEqual(result["configuration"]["threshold_multiplier"], 2.0)

    def test_serialization_with_stats(self):
        """Test detector serialization with statistics."""
        result = DetectorSerializer.to_dict(self.detector, include_stats=True)

        self.assertIn("statistics", result)
        stats = result["statistics"]
        self.assertEqual(stats["total_detections"], 2)
        self.assertEqual(stats["pending_detections"], 1)
        self.assertEqual(stats["processed_detections"], 1)
        self.assertEqual(stats["run_count"], 5)
        self.assertEqual(stats["detection_count"], 10)
        self.assertIsNotNone(stats["success_rate"])
        self.assertEqual(stats["average_detections_per_run"], 2.0)

    def test_serialization_without_config(self):
        """Test detector serialization without configuration."""
        result = DetectorSerializer.to_dict(self.detector, include_config=False)

        self.assertNotIn("configuration", result)
        self.assertIn("name", result)
        self.assertIn("active", result)


class DetectionSerializerTest(TestCase):
    """Test cases for DetectionSerializer."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector", active=True)

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.admin_level = AdmLevel.objects.create(name="State", code="1")
        self.location = Location.objects.create(
            name="Test Location",
            geo_id="SD_001",
            admin_level=self.admin_level
        )

        self.detection = Detection.objects.create(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=timezone.now(),
            confidence_score=0.85,
            shock_type=self.shock_type,
            detection_data={"events": 25, "baseline": 10},
            status="pending",
        )
        self.detection.locations.add(self.location)

    def test_basic_serialization(self):
        """Test basic detection serialization."""
        result = DetectionSerializer.to_dict(self.detection)

        self.assertEqual(result["id"], self.detection.id)
        self.assertEqual(result["title"], "Test Detection")
        self.assertEqual(result["confidence_score"], 0.85)
        self.assertEqual(result["status"], "pending")
        self.assertIn("detection_data", result)
        self.assertEqual(result["detection_data"]["events"], 25)

    def test_serialization_with_detector(self):
        """Test detection serialization with detector info."""
        result = DetectionSerializer.to_dict(self.detection, include_detector=True)

        self.assertIn("detector", result)
        detector_info = result["detector"]
        self.assertEqual(detector_info["id"], self.detector.id)
        self.assertEqual(detector_info["name"], "Test Detector")

    def test_serialization_with_locations(self):
        """Test detection serialization with locations."""
        result = DetectionSerializer.to_dict(self.detection, include_locations=True)

        self.assertIn("locations", result)
        self.assertEqual(len(result["locations"]), 1)
        location_info = result["locations"][0]
        self.assertEqual(location_info["id"], self.location.id)
        self.assertEqual(location_info["name"], "Test Location")

    def test_serialization_without_locations(self):
        """Test detection serialization without locations."""
        result = DetectionSerializer.to_dict(self.detection, include_locations=False)

        self.assertIn("locations", result)
        self.assertEqual(len(result["locations"]), 0)

    def test_shock_type_serialization(self):
        """Test shock type is included in serialization."""
        result = DetectionSerializer.to_dict(self.detection)

        self.assertIn("shock_type", result)
        shock_info = result["shock_type"]
        self.assertEqual(shock_info["id"], self.shock_type.id)
        self.assertEqual(shock_info["name"], "Conflict")

    def test_summary_serialization(self):
        """Test detection summary serialization."""
        result = DetectionSerializer.to_summary_dict(self.detection)

        expected_keys = ["id", "detection_timestamp", "status", "confidence_score", "location_count"]
        for key in expected_keys:
            self.assertIn(key, result)

        self.assertEqual(result["location_count"], 1)


class LocationSerializerTest(TestCase):
    """Test cases for LocationSerializer."""

    def setUp(self):
        """Set up test data."""
        self.admin_level = AdmLevel.objects.create(name="State", code="1")
        self.location = Location.objects.create(
            name="Test Location",
            geo_id="SD_002",
            admin_level=self.admin_level
        )

    def test_basic_serialization(self):
        """Test basic location serialization."""
        result = LocationSerializer.to_dict(self.location)

        self.assertEqual(result["id"], self.location.id)
        self.assertEqual(result["name"], "Test Location")

    def test_admin_level_serialization(self):
        """Test admin level is included."""
        result = LocationSerializer.to_dict(self.location)

        self.assertIn("admin_level", result)
        admin_info = result["admin_level"]
        self.assertEqual(admin_info["id"], self.admin_level.id)
        self.assertEqual(admin_info["name"], "State")
        self.assertEqual(admin_info["level"], 1)

    def test_location_without_admin_level(self):
        """Test location serialization when admin level is None."""
        # Create a location with admin level first
        location = Location.objects.create(
            name="No Admin Location",
            geo_id="SD_999",
            admin_level=self.admin_level
        )
        # Then set admin_level to None to simulate the scenario
        location.admin_level = None

        result = LocationSerializer.to_dict(location)
        self.assertIsNone(result["admin_level"])


class AlertTemplateSerializerTest(TestCase):
    """Test cases for AlertTemplateSerializer."""

    def setUp(self):
        """Set up test data."""
        self.shock_type = ShockType.objects.create(name="Conflict")
        self.template = AlertTemplate.objects.create(
            name="Test Template",
            shock_type=self.shock_type,
            title="Alert: {{ location }}",
            text="Conflict detected with {{ confidence }}% confidence",
            variables={"location": "str", "confidence": "float"},
            active=True,
            detector_type="ConflictSurgeDetector",
        )

    def test_basic_serialization(self):
        """Test basic template serialization."""
        result = AlertTemplateSerializer.to_dict(self.template)

        self.assertEqual(result["id"], self.template.id)
        self.assertEqual(result["name"], "Test Template")
        self.assertEqual(result["title"], "Alert: {{ location }}")
        self.assertEqual(result["text"], "Conflict detected with {{ confidence }}% confidence")
        self.assertTrue(result["active"])
        self.assertEqual(result["detector_type"], "ConflictSurgeDetector")

    def test_shock_type_serialization(self):
        """Test shock type is included."""
        result = AlertTemplateSerializer.to_dict(self.template)

        self.assertIn("shock_type", result)
        shock_info = result["shock_type"]
        self.assertEqual(shock_info["id"], self.shock_type.id)
        self.assertEqual(shock_info["name"], "Conflict")

    def test_variables_serialization(self):
        """Test variables are included."""
        result = AlertTemplateSerializer.to_dict(self.template)

        self.assertIn("variables", result)
        self.assertEqual(result["variables"]["location"], "str")
        self.assertEqual(result["variables"]["confidence"], "float")


class PaginationSerializerTest(TestCase):
    """Test cases for PaginationSerializer."""

    def setUp(self):
        """Set up test data."""
        # Create some detectors for pagination
        for i in range(25):
            Detector.objects.create(name=f"Detector {i}", class_name="test.detector", active=True)

    def test_pagination_serialization(self):
        """Test pagination metadata serialization."""
        detectors = Detector.objects.all()
        paginator = Paginator(detectors, 10)  # 10 per page
        page_obj = paginator.get_page(2)  # Second page

        result = PaginationSerializer.to_dict(page_obj, paginator)

        self.assertEqual(result["page"], 2)
        self.assertEqual(result["total_pages"], 3)  # 25 items / 10 per page = 3 pages
        self.assertEqual(result["per_page"], 10)
        self.assertEqual(result["total_count"], 25)
        self.assertTrue(result["has_previous"])
        self.assertTrue(result["has_next"])

    def test_first_page_pagination(self):
        """Test pagination for first page."""
        detectors = Detector.objects.all()
        paginator = Paginator(detectors, 10)
        page_obj = paginator.get_page(1)

        result = PaginationSerializer.to_dict(page_obj, paginator)

        self.assertEqual(result["page"], 1)
        self.assertFalse(result["has_previous"])
        self.assertTrue(result["has_next"])

    def test_last_page_pagination(self):
        """Test pagination for last page."""
        detectors = Detector.objects.all()
        paginator = Paginator(detectors, 10)
        page_obj = paginator.get_page(3)  # Last page

        result = PaginationSerializer.to_dict(page_obj, paginator)

        self.assertEqual(result["page"], 3)
        self.assertTrue(result["has_previous"])
        self.assertFalse(result["has_next"])
