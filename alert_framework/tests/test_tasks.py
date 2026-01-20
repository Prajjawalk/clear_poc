"""Tests for Celery tasks."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from alert_framework.models import AlertTemplate, Detection, Detector, PublishedAlert
from alert_framework.tasks import (
    cancel_published_alert,
    monitor_published_alerts,
    publish_alert,
    run_detector,
    update_published_alert,
)
from alerts.models import ShockType
from location.models import AdmLevel, Location


class RunDetectorTaskTest(TestCase):
    """Test cases for run_detector task."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(
            name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector", active=True, configuration={"threshold_multiplier": 2.0}
        )
        self.admin_level = AdmLevel.objects.create(code="1", name="State")
        self.location = Location.objects.create(
            name="Test Location",
            geo_id="SD_001",
            admin_level=self.admin_level
        )

    @patch.object(run_detector, 'max_retries', 0)  # Set max_retries to 0 to skip retries
    def test_detector_not_found(self):
        """Test task behavior when detector doesn't exist."""
        result = run_detector(detector_id=99999)

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error_message"])

    @patch.object(run_detector, 'max_retries', 0)
    def test_inactive_detector(self):
        """Test task behavior with inactive detector."""
        self.detector.active = False
        self.detector.save()

        result = run_detector(detector_id=self.detector.id)

        self.assertFalse(result["success"])
        self.assertIn("not active", result["error_message"])

    @patch("alert_framework.tasks.import_string")
    @patch.object(run_detector, 'max_retries', 0)
    def test_successful_detection(self, mock_import_string):
        """Test successful detector execution."""
        # Mock detector class
        mock_detector_class = Mock()
        mock_detector_instance = Mock()
        mock_detector_instance.detect.return_value = [
            {"detection_timestamp": timezone.now(), "confidence_score": 0.85, "locations": [], "metadata": {"events": 25}}
        ]
        mock_detector_class.return_value = mock_detector_instance
        mock_import_string.return_value = mock_detector_class

        # Mock deduplication checker
        with patch("alert_framework.tasks.duplication_checker") as mock_dedup:
            mock_dedup.is_duplicate.return_value = False

            result = run_detector(detector_id=self.detector.id)

        self.assertTrue(result["success"])
        self.assertEqual(result["detections_created"], 1)
        self.assertEqual(result["detections_duplicates"], 0)

    @patch("alert_framework.tasks.import_string")
    @patch.object(run_detector, 'max_retries', 0)
    def test_duplicate_detection(self, mock_import_string):
        """Test detection with duplicate results."""
        # Mock detector class
        mock_detector_class = Mock()
        mock_detector_instance = Mock()
        mock_detector_instance.detect.return_value = [
            {"detection_timestamp": timezone.now(), "confidence_score": 0.85, "locations": [], "metadata": {"events": 25}}
        ]
        mock_detector_class.return_value = mock_detector_instance
        mock_import_string.return_value = mock_detector_class

        # Mock deduplication checker to return duplicate
        with patch("alert_framework.tasks.duplication_checker") as mock_dedup:
            mock_dedup.is_duplicate.return_value = True

            result = run_detector(detector_id=self.detector.id)

        self.assertTrue(result["success"])
        self.assertEqual(result["detections_created"], 0)
        self.assertEqual(result["detections_duplicates"], 1)


class PublishAlertTaskTest(TestCase):
    """Test cases for publish_alert task."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector", active=True)

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.detection = Detection.objects.create(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=timezone.now(),
            confidence_score=0.8,
            shock_type=self.shock_type
        )

        self.template = AlertTemplate.objects.create(
            name="Test Template", shock_type=self.shock_type, title="Alert: {{ detector_name }}", text="Detection confidence: {{ confidence }}%"
        )

    @patch.object(publish_alert, 'max_retries', 0)
    def test_detection_not_found(self):
        """Test task behavior when detection doesn't exist."""
        result = publish_alert(detection_id=99999, template_id=self.template.id)

        self.assertFalse(result["success"])
        self.assertIn("error_message", result)

    @patch.object(publish_alert, 'max_retries', 0)
    def test_template_not_found(self):
        """Test task behavior when template doesn't exist."""
        result = publish_alert(detection_id=self.detection.id, template_id=99999)

        self.assertFalse(result["success"])
        self.assertIn("error_message", result)

    @patch("alert_framework.api_client.PublicAlertInterface")
    @patch.object(publish_alert, 'max_retries', 0)
    def test_successful_publication(self, mock_interface):
        """Test successful alert publication."""
        # Mock successful publication
        mock_interface_instance = Mock()
        mock_interface_instance.publish_alert.return_value = {"test_api": {"success": True, "external_id": "alert_123", "response": {"id": "alert_123", "status": "published"}}}
        mock_interface.return_value = mock_interface_instance

        result = publish_alert(detection_id=self.detection.id, template_id=self.template.id)

        self.assertTrue(result["success"])
        self.assertEqual(len(result["published_alerts"]), 1)
        self.assertEqual(len(result["failed_apis"]), 0)

        # Check that PublishedAlert was created
        published_alert = PublishedAlert.objects.get(detection=self.detection, template=self.template)
        self.assertEqual(published_alert.status, "published")
        self.assertEqual(published_alert.external_id, "alert_123")

    @patch("alert_framework.api_client.PublicAlertInterface")
    @patch.object(publish_alert, 'max_retries', 0)
    def test_failed_publication(self, mock_interface):
        """Test failed alert publication."""
        # Mock failed publication
        mock_interface_instance = Mock()
        mock_interface_instance.publish_alert.return_value = {"test_api": {"success": False, "error": "API connection failed"}}
        mock_interface.return_value = mock_interface_instance

        result = publish_alert(detection_id=self.detection.id, template_id=self.template.id)

        self.assertFalse(result["success"])
        self.assertEqual(len(result["published_alerts"]), 0)
        self.assertEqual(len(result["failed_apis"]), 1)

        # Check that PublishedAlert was created with failed status
        published_alert = PublishedAlert.objects.get(detection=self.detection, template=self.template)
        self.assertEqual(published_alert.status, "failed")
        self.assertIn("API connection failed", published_alert.error_message)


class UpdatePublishedAlertTaskTest(TestCase):
    """Test cases for update_published_alert task."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector")

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.detection = Detection.objects.create(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=timezone.now(),
            confidence_score=0.8,
            shock_type=self.shock_type
        )

        self.template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Alert Title", text="Alert Text")

        self.published_alert = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="test_api", external_id="alert_123", status="published")

    @patch.object(update_published_alert, 'max_retries', 0)
    def test_published_alert_not_found(self):
        """Test task behavior when published alert doesn't exist."""
        result = update_published_alert(published_alert_id=99999)
        self.assertFalse(result["success"])
        self.assertIn("error_message", result)

    @patch.object(update_published_alert, 'max_retries', 0)
    def test_no_external_id(self):
        """Test task behavior when published alert has no external ID."""
        self.published_alert.external_id = ""
        self.published_alert.save()

        result = update_published_alert(published_alert_id=self.published_alert.id)

        self.assertFalse(result["success"])
        self.assertIn("no external ID", result["error_message"])

    @patch("alert_framework.api_client.PublicAlertInterface")
    @patch.object(update_published_alert, 'max_retries', 0)
    def test_successful_update(self, mock_interface):
        """Test successful alert update."""
        # Mock successful update
        mock_interface_instance = Mock()
        mock_interface_instance.update_alert.return_value = {"test_api": {"success": True, "response": {"status": "updated", "timestamp": "2023-01-01T12:00:00Z"}}}
        mock_interface.return_value = mock_interface_instance

        result = update_published_alert(published_alert_id=self.published_alert.id)

        self.assertTrue(result["success"])

        # Check that published alert was updated
        self.published_alert.refresh_from_db()
        self.assertEqual(self.published_alert.status, "updated")
        self.assertIsNotNone(self.published_alert.last_updated)


class CancelPublishedAlertTaskTest(TestCase):
    """Test cases for cancel_published_alert task."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector")

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.detection = Detection.objects.create(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=timezone.now(),
            confidence_score=0.8,
            shock_type=self.shock_type
        )

        self.template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Alert Title", text="Alert Text")

        self.published_alert = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="test_api", external_id="alert_123", status="published")

    @patch("alert_framework.api_client.PublicAlertInterface")
    @patch.object(cancel_published_alert, 'max_retries', 0)
    def test_successful_cancellation(self, mock_interface):
        """Test successful alert cancellation."""
        # Mock successful cancellation
        mock_interface_instance = Mock()
        mock_interface_instance.cancel_alert.return_value = {"test_api": {"success": True, "response": {"status": "cancelled"}}}
        mock_interface.return_value = mock_interface_instance

        reason = "False alarm detected"
        result = cancel_published_alert(published_alert_id=self.published_alert.id, reason=reason)

        self.assertTrue(result["success"])

        # Check that published alert was cancelled
        self.published_alert.refresh_from_db()
        self.assertEqual(self.published_alert.status, "cancelled")
        self.assertEqual(self.published_alert.cancellation_reason, reason)
        self.assertIsNotNone(self.published_alert.cancelled_at)


class MonitorPublishedAlertsTaskTest(TestCase):
    """Test cases for monitor_published_alerts task."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector")

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.detection = Detection.objects.create(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=timezone.now(),
            confidence_score=0.8,
            shock_type=self.shock_type
        )

        self.template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Alert Title", text="Alert Text")

        # Create published alert from recent time
        self.published_alert = PublishedAlert.objects.create(
            detection=self.detection, template=self.template, api_name="test_api", external_id="alert_123", status="published", published_at=timezone.now() - timedelta(hours=1)
        )

    @patch("alert_framework.api_client.PublicAlertInterface")
    @patch.object(monitor_published_alerts, 'max_retries', 0)
    def test_monitor_published_alerts(self, mock_interface):
        """Test monitoring of published alerts."""
        # Mock alert interface
        mock_interface_instance = Mock()
        mock_interface_instance.check_api_health.return_value = {"test_api": {"healthy": True, "status": "OK"}}

        # Mock client for status checking
        mock_client = Mock()
        mock_client.get_alert_status.return_value = {"status": "active", "views": 1250, "last_updated": "2023-01-01T12:00:00Z"}
        mock_interface_instance.clients = {"test_api": mock_client}

        mock_interface.return_value = mock_interface_instance

        result = monitor_published_alerts()

        self.assertEqual(result["checked_alerts"], 1)
        self.assertEqual(result["status_updates"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertIn("test_api", result["api_health"])

        # Check that alert metadata was updated
        self.published_alert.refresh_from_db()
        self.assertIn("last_status_check", self.published_alert.publication_metadata)
