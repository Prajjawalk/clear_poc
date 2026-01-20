"""Tests for alert framework API views."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from alert_framework.models import AlertTemplate, Detection, Detector
from alerts.models import ShockType
from location.models import AdmLevel, Location

User = get_user_model()


class APIViewsTestCase(TestCase):
    """Base test case for API views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        # Create test data
        self.detector = Detector.objects.create(
            name="Test Detector",
            description="A test detector for API testing",
            class_name="alert_framework.detectors.test_detector.TestDetector",
            active=True,
            configuration={"threshold": 0.8},
            run_count=5,
            detection_count=10,
        )

        self.inactive_detector = Detector.objects.create(name="Inactive Detector", class_name="alert_framework.detectors.test_detector.TestDetector", active=False)

        self.shock_type = ShockType.objects.create(name="Conflict")
        self.admin_level = AdmLevel.objects.create(name="State", code="1")
        self.location = Location.objects.create(name="Test Location", admin_level=self.admin_level)

        # Create detections
        now = timezone.now()
        self.detection = Detection.objects.create(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=now - timedelta(hours=1),
            confidence_score=0.85,
            shock_type=self.shock_type,
            status="pending",
            detection_data={"events": 15, "baseline": 8},
        )
        self.detection.locations.add(self.location)

        self.processed_detection = Detection.objects.create(
            detector=self.detector,
            title="Processed Detection",
            detection_timestamp=now - timedelta(days=1),
            confidence_score=0.75,
            shock_type=self.shock_type,
            status="processed",
            processed_at=now,
        )

        self.template = AlertTemplate.objects.create(
            name="Test Template", shock_type=self.shock_type, title="Alert: {{ location }}", text="Detection with {{ confidence }}% confidence", active=True
        )


class DetectorListAPIViewTest(APIViewsTestCase):
    """Test cases for DetectorListAPIView."""

    def test_list_detectors(self):
        """Test listing all detectors."""
        response = self.client.get("/alert_framework/api/detectors/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("detectors", data)
        self.assertIn("pagination", data)
        self.assertEqual(len(data["detectors"]), 2)

        # Check detector data structure
        detector_data = data["detectors"][0]
        required_fields = ["id", "name", "description", "class_name", "active", "configuration"]
        for field in required_fields:
            self.assertIn(field, detector_data)

    def test_list_detectors_with_search(self):
        """Test listing detectors with search filter."""
        response = self.client.get("/alert_framework/api/detectors/?search=Test")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["detectors"]), 1)
        self.assertEqual(data["detectors"][0]["name"], "Test Detector")

    def test_list_detectors_filter_active(self):
        """Test filtering detectors by active status."""
        response = self.client.get("/alert_framework/api/detectors/?active=true")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["detectors"]), 1)
        self.assertTrue(data["detectors"][0]["active"])

    def test_list_detectors_pagination(self):
        """Test detector list pagination."""
        # Create more detectors to test pagination
        for i in range(25):
            Detector.objects.create(name=f"Detector {i}", class_name="test.detector", active=True)

        response = self.client.get("/alert_framework/api/detectors/?page=2")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        pagination = data["pagination"]
        self.assertEqual(pagination["page"], 2)
        self.assertTrue(pagination["has_previous"])


class DetectorDetailAPIViewTest(APIViewsTestCase):
    """Test cases for DetectorDetailAPIView."""

    def test_get_detector_detail(self):
        """Test getting detector details."""
        url = f"/alert_framework/api/detectors/{self.detector.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["id"], self.detector.id)
        self.assertEqual(data["name"], "Test Detector")
        self.assertIn("statistics", data)
        self.assertIn("recent_detections", data)

        # Check statistics
        stats = data["statistics"]
        self.assertEqual(stats["total_detections"], 2)
        self.assertEqual(stats["pending_detections"], 1)
        self.assertEqual(stats["processed_detections"], 1)

    def test_get_nonexistent_detector(self):
        """Test getting details for non-existent detector."""
        response = self.client.get("/alert_framework/api/detectors/99999/")
        self.assertEqual(response.status_code, 404)

        data = response.json()
        self.assertIn("error", data)


class DetectionListAPIViewTest(APIViewsTestCase):
    """Test cases for DetectionListAPIView."""

    def test_list_detections(self):
        """Test listing all detections."""
        response = self.client.get("/alert_framework/api/detections/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("detections", data)
        self.assertIn("pagination", data)
        self.assertEqual(len(data["detections"]), 2)

    def test_list_detections_filter_by_detector(self):
        """Test filtering detections by detector."""
        url = f"/alert_framework/api/detections/?detector={self.detector.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["detections"]), 2)
        for detection in data["detections"]:
            self.assertEqual(detection["detector"]["id"], self.detector.id)

    def test_list_detections_filter_by_status(self):
        """Test filtering detections by status."""
        response = self.client.get("/alert_framework/api/detections/?status=pending")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["detections"]), 1)
        self.assertEqual(data["detections"][0]["status"], "pending")

    def test_list_detections_filter_by_confidence(self):
        """Test filtering detections by confidence threshold."""
        response = self.client.get("/alert_framework/api/detections/?min_confidence=0.8")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["detections"]), 1)
        self.assertGreaterEqual(data["detections"][0]["confidence_score"], 0.8)

    def test_list_detections_filter_by_date_range(self):
        """Test filtering detections by date range."""
        start_date = (timezone.now() - timedelta(hours=2)).isoformat()
        end_date = timezone.now().isoformat()

        url = f"/alert_framework/api/detections/?start_date={start_date}&end_date={end_date}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["detections"]), 1)

    def test_detection_data_structure(self):
        """Test detection data structure in API response."""
        response = self.client.get("/alert_framework/api/detections/")
        data = response.json()

        detection = data["detections"][0]
        required_fields = ["id", "title", "detection_timestamp", "status", "confidence_score", "detector", "locations", "detection_data"]
        for field in required_fields:
            self.assertIn(field, detection)

        # Check nested structures
        self.assertIn("id", detection["detector"])
        self.assertIn("name", detection["detector"])
        self.assertIsInstance(detection["locations"], list)


class DetectionDetailAPIViewTest(APIViewsTestCase):
    """Test cases for DetectionDetailAPIView."""

    def test_get_detection_detail(self):
        """Test getting detection details."""
        url = f"/alert_framework/api/detections/{self.detection.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["id"], self.detection.id)
        self.assertEqual(data["title"], "Test Detection")
        self.assertEqual(data["confidence_score"], 0.85)
        self.assertIn("detector", data)
        self.assertIn("locations", data)
        self.assertIn("detection_data", data)

    def test_get_nonexistent_detection(self):
        """Test getting details for non-existent detection."""
        response = self.client.get("/alert_framework/api/detections/99999/")
        self.assertEqual(response.status_code, 404)


class RunDetectorAPIViewTest(APIViewsTestCase):
    """Test cases for run_detector_api view."""

    def test_run_detector_success(self):
        """Test successfully triggering detector execution."""
        url = f"/alert_framework/api/detectors/{self.detector.id}/run/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("task_id", data)
        self.assertIn("detector", data)

    def test_run_inactive_detector(self):
        """Test running an inactive detector."""
        url = f"/alert_framework/api/detectors/{self.inactive_detector.id}/run/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

        data = response.json()
        self.assertIn("error", data)

    def test_run_nonexistent_detector(self):
        """Test running a non-existent detector."""
        response = self.client.post("/alert_framework/api/detectors/99999/run/")
        self.assertEqual(response.status_code, 404)

    def test_run_detector_wrong_method(self):
        """Test using wrong HTTP method."""
        url = f"/alert_framework/api/detectors/{self.detector.id}/run/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)


class SystemStatsAPIViewTest(APIViewsTestCase):
    """Test cases for SystemStatsAPIView."""

    def test_get_system_stats(self):
        """Test getting system statistics."""
        response = self.client.get("/alert_framework/api/stats/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        required_sections = ["timestamp", "detector_stats", "detection_stats", "template_stats", "trends", "system_health"]
        for section in required_sections:
            self.assertIn(section, data)

        # Check detector stats
        detector_stats = data["detector_stats"]
        self.assertEqual(detector_stats["total"], 2)
        self.assertEqual(detector_stats["active"], 1)

        # Check detection stats
        detection_stats = data["detection_stats"]
        self.assertEqual(detection_stats["total"], 2)
        self.assertEqual(detection_stats["pending"], 1)


class DetectionActionAPIViewTest(APIViewsTestCase):
    """Test cases for detection_action_api view."""

    def test_process_detection(self):
        """Test processing a detection."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        data = {"action": "process"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        self.assertTrue(response_data["success"])
        self.assertIn("detection", response_data)

        # Verify detection was updated
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, "processed")

    def test_dismiss_detection(self):
        """Test dismissing a detection."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        data = {"action": "dismiss"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        # Verify detection was updated
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, "dismissed")

    def test_mark_duplicate_detection(self):
        """Test marking detection as duplicate."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        data = {"action": "mark_duplicate", "original_id": str(self.processed_detection.id)}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        # Verify detection was updated
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, "dismissed")
        self.assertIn("duplicate_of", self.detection.detection_data)

    def test_mark_duplicate_missing_original(self):
        """Test marking duplicate without original ID."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        data = {"action": "mark_duplicate"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_invalid_action(self):
        """Test invalid action."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        data = {"action": "invalid_action"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_action_on_nonexistent_detection(self):
        """Test action on non-existent detection."""
        url = "/alert_framework/api/detections/99999/action/"
        data = {"action": "process"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)

    def test_action_wrong_method(self):
        """Test using wrong HTTP method for action."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_action_missing_parameter(self):
        """Test action without action parameter."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 400)

    def test_process_already_processed_detection(self):
        """Test processing an already processed detection."""
        url = f"/alert_framework/api/detections/{self.processed_detection.id}/action/"
        data = {"action": "process"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

        response_data = response.json()
        self.assertIn("error", response_data)


class APIErrorHandlingTest(APIViewsTestCase):
    """Test cases for API error handling."""

    def test_invalid_json_in_post(self):
        """Test handling of invalid JSON in POST requests."""
        url = f"/alert_framework/api/detections/{self.detection.id}/action/"
        _response = self.client.post(url, data="invalid json", content_type="application/json")
        # Should handle gracefully, not crash

    def test_api_with_invalid_parameters(self):
        """Test API with invalid query parameters."""
        # Invalid date format
        response = self.client.get("/alert_framework/api/detections/?start_date=invalid-date")
        self.assertEqual(response.status_code, 200)  # Should handle gracefully

        # Invalid confidence value
        response = self.client.get("/alert_framework/api/detections/?min_confidence=invalid")
        self.assertEqual(response.status_code, 200)  # Should handle gracefully
