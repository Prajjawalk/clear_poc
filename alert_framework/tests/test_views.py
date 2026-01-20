"""Tests for alert framework views."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from alert_framework.models import AlertTemplate, Detection, Detector
from alerts.models import ShockType


class AlertFrameworkViewTest(TestCase):
    """Test cases for alert framework views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")

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
            name="Test Template",
            shock_type=self.shock_type,
            title="Alert: {{ shock_type }}",
            text="Detection from {{ detector_name }} at {{ detection_timestamp }}"
        )

    def test_dashboard_view(self):
        """Test dashboard view access and content."""
        url = reverse("alert_framework:dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alert Framework Dashboard")
        self.assertContains(response, "Active Detectors")
        self.assertContains(response, "Pending Detections")

    def test_detector_list_view(self):
        """Test detector list view."""
        url = reverse("alert_framework:detector_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detectors")
        self.assertContains(response, self.detector.name)

    def test_detector_detail_view(self):
        """Test detector detail view."""
        url = reverse("alert_framework:detector_detail", args=[self.detector.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.detector.name)
        self.assertContains(response, self.detector.description)

    def test_detection_list_view(self):
        """Test detection list view."""
        url = reverse("alert_framework:detection_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detections")
        # Should contain the detector name associated with the detection
        self.assertContains(response, self.detector.name)

    def test_detection_detail_view(self):
        """Test detection detail view."""
        url = reverse("alert_framework:detection_detail", args=[self.detection.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Detection #{self.detection.id}")
        self.assertContains(response, self.detector.name)

    def test_template_list_view(self):
        """Test alert template list view."""
        url = reverse("alert_framework:template_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alert Templates")
        self.assertContains(response, self.template.name)

    def test_template_detail_view(self):
        """Test alert template detail view."""
        url = reverse("alert_framework:template_detail", args=[self.template.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.template.name)
        # Check for the template name in the page, not the actual template content
        self.assertContains(response, "Test Template")

    @patch("alert_framework.tasks.run_detector.delay")
    def test_detector_run_view(self, mock_run_detector):
        """Test detector run view."""
        mock_run_detector.return_value.id = "task_123"

        # Login required for this view
        self.client.login(username="testuser", password="testpass123")

        url = reverse("alert_framework:detector_run", args=[self.detector.pk])
        response = self.client.post(url)

        # Should redirect after successful task queueing
        self.assertEqual(response.status_code, 302)
        mock_run_detector.assert_called_once_with(self.detector.id)

    def test_detector_run_inactive_detector(self):
        """Test running an inactive detector."""
        self.detector.active = False
        self.detector.save()

        # Login required for this view
        self.client.login(username="testuser", password="testpass123")

        url = reverse("alert_framework:detector_run", args=[self.detector.pk])
        response = self.client.post(url)

        # Should redirect with error message
        self.assertEqual(response.status_code, 302)

    def test_detection_action_view(self):
        """Test detection action view."""
        # Login required for this view
        self.client.login(username="testuser", password="testpass123")

        url = reverse("alert_framework:detection_action", args=[self.detection.pk])

        # Test processing action
        response = self.client.post(url, {"action": "process"})
        self.assertEqual(response.status_code, 302)

        # Check that detection was processed
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, "processed")

    def test_detection_action_dismiss(self):
        """Test dismissing a detection."""
        # Login required for this view
        self.client.login(username="testuser", password="testpass123")

        url = reverse("alert_framework:detection_action", args=[self.detection.pk])

        response = self.client.post(url, {"action": "dismiss"})
        self.assertEqual(response.status_code, 302)

        # Check that detection was dismissed
        self.detection.refresh_from_db()
        self.assertEqual(self.detection.status, "dismissed")

    def test_detection_list_filtering(self):
        """Test detection list filtering functionality."""
        # Create another detection with different status
        detection2 = Detection.objects.create(
            detector=self.detector,
            title="Processed Detection",
            detection_timestamp=timezone.now(),
            confidence_score=0.6,
            shock_type=self.shock_type,
            status="processed"
        )

        url = reverse("alert_framework:detection_list")

        # Test filtering by pending status
        response = self.client.get(url, {"status": "pending"})
        self.assertEqual(response.status_code, 200)

        # Check that only the pending detection is shown in the table
        # Use URLs to avoid false positives with CSS color codes
        detection1_url = reverse('alert_framework:detection_detail', args=[self.detection.pk])
        detection2_url = reverse('alert_framework:detection_detail', args=[detection2.pk])

        self.assertContains(response, detection1_url)
        self.assertNotContains(response, detection2_url)

        # Test filtering by processed status
        response = self.client.get(url, {"status": "processed"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, detection1_url)
        self.assertContains(response, detection2_url)

    def test_detector_list_search(self):
        """Test detector list search functionality."""
        # Create another detector
        detector2 = Detector.objects.create(name="Different Detector", class_name="alert_framework.detectors.surge_detector.DisplacementSurgeDetector", active=True)

        url = reverse("alert_framework:detector_list")

        # Test search by name
        response = self.client.get(url, {"search": "Test"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.detector.name)
        self.assertNotContains(response, detector2.name)

        # Test search that matches both
        response = self.client.get(url, {"search": "Detector"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.detector.name)
        self.assertContains(response, detector2.name)

    def test_view_context_data(self):
        """Test that views provide expected context data."""
        url = reverse("alert_framework:dashboard")
        response = self.client.get(url)

        # Check that statistics are provided in context
        self.assertIn("detector_stats", response.context)
        self.assertIn("detection_stats", response.context)
        self.assertIn("recent_detections", response.context)
        self.assertIn("active_detectors", response.context)

    def test_404_views(self):
        """Test 404 responses for non-existent objects."""
        # Test non-existent detector
        url = reverse("alert_framework:detector_detail", args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # Test non-existent detection
        url = reverse("alert_framework:detection_detail", args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # Test non-existent template
        url = reverse("alert_framework:template_detail", args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
