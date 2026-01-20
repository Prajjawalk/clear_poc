"""Tests for alert framework models."""

# from django.db.utils import IntegrityError

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from alert_framework.models import AlertTemplate, Detection, Detector, PublishedAlert
from alerts.models import ShockType
from location.models import AdmLevel, Location


class DetectorModelTest(TestCase):
    """Test cases for Detector model."""

    def setUp(self):
        """Set up test data."""
        self.detector_data = {
            "name": "Test Detector",
            "description": "A test detector for unit testing",
            "class_name": "alert_framework.detectors.surge_detector.ConflictSurgeDetector",
            "active": True,
            "configuration": {"threshold_multiplier": 2.0, "baseline_days": 30, "minimum_events": 5},
        }

    def test_create_detector(self):
        """Test creating a detector."""
        detector = Detector.objects.create(**self.detector_data)

        self.assertEqual(detector.name, "Test Detector")
        self.assertTrue(detector.active)
        self.assertEqual(detector.configuration["threshold_multiplier"], 2.0)
        self.assertEqual(detector.run_count, 0)
        self.assertEqual(detector.detection_count, 0)
        self.assertIsNotNone(detector.created_at)

    def test_detector_unique_name(self):
        """Test that detector names must be unique."""
        Detector.objects.create(**self.detector_data)

        with self.assertRaises(IntegrityError):
            Detector.objects.create(**self.detector_data)

    def test_detector_str_representation(self):
        """Test string representation of detector."""
        detector = Detector.objects.create(**self.detector_data)
        self.assertEqual(str(detector), "Test Detector")

    def test_success_rate_property(self):
        """Test success rate calculation."""
        detector = Detector.objects.create(**self.detector_data)

        # Should return None when run_count is 0
        self.assertIsNone(detector.success_rate)

        # Test with no detections
        detector.run_count = 5
        detector.detection_count = 0
        detector.save()
        self.assertEqual(detector.success_rate, 0.0)

        # Test with some detections (less than 1 per run)
        detector.detection_count = 3
        detector.save()
        self.assertEqual(detector.success_rate, 0.6)  # 3/5 = 0.6

        # Test with high detection rate (>= 1 per run)
        detector.detection_count = 10
        detector.save()
        self.assertEqual(detector.success_rate, 1.0)  # 10/5 >= 1.0

    def test_average_detections_per_run_property(self):
        """Test average detections per run calculation."""
        detector = Detector.objects.create(**self.detector_data)

        # Should return 0 when run_count is 0
        self.assertEqual(detector.average_detections_per_run, 0)

        # Update counts and test calculation
        detector.run_count = 5
        detector.detection_count = 15
        detector.save()
        self.assertEqual(detector.average_detections_per_run, 3.0)


class DetectionModelTest(TestCase):
    """Test cases for Detection model."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector", active=True)

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.admin_level = AdmLevel.objects.create(name="State", code="1")

        self.location = Location.objects.create(name="Test Location", admin_level=self.admin_level)

    def test_create_detection(self):
        """Test creating a detection."""
        detection_time = timezone.now()

        detection = Detection.objects.create(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=detection_time,
            confidence_score=0.85,
            shock_type=self.shock_type,
            detection_data={"events": 25, "baseline": 10},
        )

        detection.locations.add(self.location)

        self.assertEqual(detection.detector, self.detector)
        self.assertEqual(detection.confidence_score, 0.85)
        self.assertEqual(detection.status, "pending")  # Default status
        self.assertEqual(detection.locations.count(), 1)
        self.assertEqual(detection.detection_data["events"], 25)

    def test_detection_str_representation(self):
        """Test string representation of detection."""
        detection_time = timezone.now()
        detection = Detection.objects.create(detector=self.detector, title="Test Detection", detection_timestamp=detection_time, confidence_score=0.75)

        expected = f"{self.detector.name} - {detection_time.strftime('%Y-%m-%d %H:%M')}"
        self.assertEqual(str(detection), expected)

    def test_confidence_score_validation(self):
        """Test that confidence score is properly validated."""
        detection = Detection(
            detector=self.detector,
            title="Test Detection",
            detection_timestamp=timezone.now(),
            confidence_score=1.5,  # Invalid: > 1.0
        )

        with self.assertRaises(ValidationError):
            detection.full_clean()

        detection.confidence_score = -0.1  # Invalid: < 0.0
        with self.assertRaises(ValidationError):
            detection.full_clean()

        detection.confidence_score = 0.85  # Valid
        detection.detection_data = {"test": "data"}
        detection.full_clean()  # Should not raise

    def test_detection_ordering(self):
        """Test that detections are ordered by timestamp descending."""
        time1 = timezone.now()
        time2 = time1.replace(hour=time1.hour + 1)

        detection1 = Detection.objects.create(detector=self.detector, title="Detection 1", detection_timestamp=time1, confidence_score=0.5)

        detection2 = Detection.objects.create(detector=self.detector, title="Detection 2", detection_timestamp=time2, confidence_score=0.7)

        detections = list(Detection.objects.all())
        self.assertEqual(detections[0], detection2)  # Most recent first
        self.assertEqual(detections[1], detection1)


class AlertTemplateModelTest(TestCase):
    """Test cases for AlertTemplate model."""

    def setUp(self):
        """Set up test data."""
        self.shock_type = ShockType.objects.create(name="Conflict")

    def test_create_alert_template(self):
        """Test creating an alert template."""
        template = AlertTemplate.objects.create(
            name="Conflict Alert Template",
            shock_type=self.shock_type,
            title="ALERT: Conflict detected in {{ location }}",
            text="A conflict event has been detected with {{ confidence }}% confidence.",
            variables={"location": "str", "confidence": "float"},
            active=True,
        )

        self.assertEqual(template.name, "Conflict Alert Template")
        self.assertEqual(template.shock_type, self.shock_type)
        self.assertTrue(template.active)
        self.assertEqual(template.variables["location"], "str")

    def test_template_str_representation(self):
        """Test string representation of template."""
        template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Test Title", text="Test Text")

        expected = f"{self.shock_type.name} - Test Template"
        self.assertEqual(str(template), expected)

    def test_template_render(self):
        """Test template rendering with Jinja2."""
        template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Alert in {{ location }}", text="Confidence: {{ confidence }}%")

        context = {"location": "Khartoum", "confidence": 85.5}
        rendered = template.render(context)

        self.assertEqual(rendered["title"], "Alert in Khartoum")
        self.assertEqual(rendered["text"], "Confidence: 85.5%")

    def test_template_ordering(self):
        """Test that templates are ordered by shock type and name."""
        shock_type2 = ShockType.objects.create(name="Displacement")

        template1 = AlertTemplate.objects.create(name="B Template", shock_type=self.shock_type, title="Title", text="Text")

        template2 = AlertTemplate.objects.create(name="A Template", shock_type=shock_type2, title="Title", text="Text")

        templates = list(AlertTemplate.objects.all())
        # Should be ordered by shock_type name, then template name
        self.assertEqual(templates[0], template1)  # Conflict comes before Displacement
        self.assertEqual(templates[1], template2)


class PublishedAlertModelTest(TestCase):
    """Test cases for PublishedAlert model."""

    def setUp(self):
        """Set up test data."""
        self.detector = Detector.objects.create(name="Test Detector", class_name="alert_framework.detectors.surge_detector.ConflictSurgeDetector")

        self.shock_type = ShockType.objects.create(name="Conflict")

        self.detection = Detection.objects.create(
            detector=self.detector, title="Test Detection", detection_timestamp=timezone.now(), confidence_score=0.8, shock_type=self.shock_type
        )

        self.template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Test Alert", text="Test alert content")

    def test_create_published_alert(self):
        """Test creating a published alert."""
        published_alert = PublishedAlert.objects.create(
            detection=self.detection, template=self.template, api_name="create_test_api", external_id="alert_123", language="en", status="published"
        )

        self.assertEqual(published_alert.detection, self.detection)
        self.assertEqual(published_alert.template, self.template)
        self.assertEqual(published_alert.api_name, "create_test_api")
        self.assertEqual(published_alert.external_id, "alert_123")
        self.assertEqual(published_alert.status, "published")
        self.assertEqual(published_alert.language, "en")
        self.assertEqual(published_alert.retry_count, 0)

    def test_published_alert_unique_constraint_fail(self):
        """Test unique constraint on detection, api_name, and language - fail."""
        # Test basic unique constraint
        PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="test_api", language="en")

        # Should raise IntegrityError for duplicate
        with self.assertRaises(IntegrityError):
            PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="test_api", language="en")

    def test_published_alert_unique_constraint_pass(self):
        """Test unique constraint on detection, api_name, and language - pass."""
        # Test basic unique constraint
        alert1 = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="test_api", language="en")

        # Should allow different language
        alert2 = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="test_api", language="ar")

        # Verify both were created
        self.assertEqual(alert1.language, "en")
        self.assertEqual(alert2.language, "ar")

    def test_mark_published(self):
        """Test marking alert as published."""
        published_alert = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="mark_published_api")

        response_data = {"id": "ext_123", "message": "Published successfully"}
        published_alert.mark_published("ext_123", response_data)

        published_alert.refresh_from_db()
        self.assertEqual(published_alert.status, "published")
        self.assertEqual(published_alert.external_id, "ext_123")
        self.assertEqual(published_alert.publication_metadata, response_data)
        self.assertIsNotNone(published_alert.published_at)

    def test_mark_failed(self):
        """Test marking alert as failed."""
        published_alert = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="mark_failed_api")

        error_message = "API connection failed"
        published_alert.mark_failed(error_message)

        published_alert.refresh_from_db()
        self.assertEqual(published_alert.status, "failed")
        self.assertEqual(published_alert.error_message, error_message)
        self.assertEqual(published_alert.retry_count, 1)

    def test_mark_updated(self):
        """Test marking alert as updated."""
        published_alert = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="mark_updated_api", status="published")

        update_data = {"updated_at": "2023-01-01T12:00:00Z"}
        published_alert.mark_updated(update_data)

        published_alert.refresh_from_db()
        self.assertEqual(published_alert.status, "updated")
        self.assertIsNotNone(published_alert.last_updated)
        self.assertIn("updated_at", published_alert.publication_metadata)

    def test_mark_cancelled(self):
        """Test marking alert as cancelled."""
        published_alert = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="mark_cancelled_api", status="published")

        reason = "False alarm detected"
        published_alert.mark_cancelled(reason)

        published_alert.refresh_from_db()
        self.assertEqual(published_alert.status, "cancelled")
        self.assertEqual(published_alert.cancellation_reason, reason)
        self.assertIsNotNone(published_alert.cancelled_at)

    def test_published_alert_str_representation(self):
        """Test string representation of published alert."""
        published_alert = PublishedAlert.objects.create(detection=self.detection, template=self.template, api_name="str_repr_api", external_id="alert_123")

        expected = "Alert alert_123 (str_repr_api)"
        self.assertEqual(str(published_alert), expected)

        # Test with pending alert (no external ID)
        published_alert.external_id = ""
        published_alert.save()

        expected = "Alert pending (str_repr_api)"
        self.assertEqual(str(published_alert), expected)
