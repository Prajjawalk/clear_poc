"""Tests for alert framework services."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from alert_framework.models import AlertTemplate, Detection, Detector
from alert_framework.services import AlertStatisticsService, DetectorConfigurationService
from alerts.models import ShockType


class AlertStatisticsServiceTest(TestCase):
    """Test cases for AlertStatisticsService."""

    def setUp(self):
        """Set up test data."""
        # Create detectors
        self.active_detector = Detector.objects.create(
            name="Active Detector", class_name="test.detector", active=True, run_count=10, detection_count=25, last_run=timezone.now() - timedelta(hours=1)
        )

        self.inactive_detector = Detector.objects.create(name="Inactive Detector", class_name="test.detector", active=False)

        # Create shock types
        self.shock_type = ShockType.objects.create(name="Conflict")

        # Create detections
        now = timezone.now()
        self.recent_detection = Detection.objects.create(
            detector=self.active_detector,
            title="Recent Detection",
            detection_timestamp=now - timedelta(hours=2),
            confidence_score=0.9,
            shock_type=self.shock_type,
            status="pending",
        )

        self.processed_detection = Detection.objects.create(
            detector=self.active_detector,
            title="Processed Detection",
            detection_timestamp=now - timedelta(days=1),
            confidence_score=0.8,
            shock_type=self.shock_type,
            status="processed",
            processed_at=now - timedelta(hours=1),
        )

        self.old_detection = Detection.objects.create(
            detector=self.active_detector,
            title="Old Detection",
            detection_timestamp=now - timedelta(days=10),
            confidence_score=0.7,
            shock_type=self.shock_type,
            status="dismissed",
            processed_at=now - timedelta(days=9),
        )

        # Create alert templates
        self.template = AlertTemplate.objects.create(name="Test Template", shock_type=self.shock_type, title="Alert Template", text="Test content", active=True)

    def test_get_detector_stats(self):
        """Test detector statistics calculation."""
        stats = AlertStatisticsService.get_detector_stats()

        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["recent_runs"], 1)  # Only active_detector ran recently

    def test_get_detection_stats_all_time(self):
        """Test detection statistics for all time."""
        stats = AlertStatisticsService.get_detection_stats()

        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["dismissed"], 1)
        self.assertEqual(stats["duplicates"], 0)
        self.assertEqual(stats["high_confidence"], 2)  # 0.9 and 0.8 scores
        self.assertIsNotNone(stats["average_confidence"])

    def test_get_detection_stats_with_timeframe(self):
        """Test detection statistics with timeframe filtering."""
        stats = AlertStatisticsService.get_detection_stats(timeframe_days=7)

        # Should only include recent_detection and processed_detection
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["dismissed"], 0)

    def test_get_recent_detection_stats(self):
        """Test recent detection statistics."""
        stats = AlertStatisticsService.get_recent_detection_stats()

        self.assertIn("last_hour", stats)
        self.assertIn("last_24h", stats)
        self.assertIn("last_7d", stats)
        self.assertIn("last_30d", stats)

        # Should have detections in recent periods
        self.assertGreaterEqual(stats["last_24h"], 1)
        self.assertGreaterEqual(stats["last_7d"], 2)
        self.assertEqual(stats["last_30d"], 3)

    def test_get_detector_performance_stats(self):
        """Test detector performance statistics."""
        stats = AlertStatisticsService.get_detector_performance_stats(self.active_detector.id)

        self.assertEqual(stats["run_count"], 10)
        self.assertEqual(stats["detection_count"], 25)
        self.assertEqual(stats["total_detections"], 3)
        self.assertEqual(stats["pending_detections"], 1)
        self.assertEqual(stats["processed_detections"], 1)
        self.assertEqual(stats["dismissed_detections"], 1)
        self.assertIsNotNone(stats["last_run"])
        self.assertIsNotNone(stats["time_since_last_run"])

    def test_get_detector_performance_stats_nonexistent(self):
        """Test detector performance stats for non-existent detector."""
        stats = AlertStatisticsService.get_detector_performance_stats(99999)
        self.assertEqual(stats, {})

    def test_get_template_stats(self):
        """Test template statistics."""
        stats = AlertStatisticsService.get_template_stats()

        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["shock_types_covered"], 1)
        self.assertEqual(stats["detector_specific"], 0)  # No detector_type set

    def test_get_system_health_metrics(self):
        """Test system health metrics calculation."""
        metrics = AlertStatisticsService.get_system_health_metrics()

        self.assertIn("detectors_with_recent_activity", metrics)
        self.assertIn("pending_detection_rate", metrics)
        self.assertIn("high_confidence_rate", metrics)
        self.assertIn("active_detector_rate", metrics)
        self.assertIn("average_processing_time", metrics)

        # Check that rates are percentages
        self.assertGreaterEqual(metrics["pending_detection_rate"], 0)
        self.assertLessEqual(metrics["pending_detection_rate"], 100)
        self.assertEqual(metrics["active_detector_rate"], 50.0)  # 1 active out of 2 total

    def test_get_detection_trends(self):
        """Test detection trends calculation."""
        trends = AlertStatisticsService.get_detection_trends(days=7)

        self.assertIn("daily_counts", trends)
        self.assertIn("status_breakdown", trends)
        self.assertIn("top_active_detectors", trends)

        self.assertIsInstance(trends["daily_counts"], list)
        self.assertIsInstance(trends["status_breakdown"], list)
        self.assertIsInstance(trends["top_active_detectors"], list)

    def test_calculate_avg_processing_time(self):
        """Test average processing time calculation."""
        # Test private method through public interface
        metrics = AlertStatisticsService.get_system_health_metrics()
        avg_time = metrics["average_processing_time"]

        # Should have a processing time for the processed detection
        self.assertIsNotNone(avg_time)
        self.assertIsInstance(avg_time, float)

    def test_calculate_avg_processing_time_no_processed(self):
        """Test average processing time when no detections are processed."""
        # Remove processed detections
        Detection.objects.filter(status="processed").delete()

        metrics = AlertStatisticsService.get_system_health_metrics()
        avg_time = metrics["average_processing_time"]

        self.assertIsNone(avg_time)


class DetectorConfigurationServiceTest(TestCase):
    """Test cases for DetectorConfigurationService."""

    def setUp(self):
        """Set up test data."""
        self.detector_with_config = Detector.objects.create(
            name="Configured Detector",
            class_name="test.detector",
            configuration={
                "threshold_multiplier": 2.5,
                "baseline_days": 30,
                "minimum_events": 10,
                "minimum_displaced": 100,
                "monitored_sources": ["IDMC", "ACLED"],
                "monitored_variables": ["displacement", "conflict"],
            },
        )

        self.detector_no_config = Detector.objects.create(name="No Config Detector", class_name="test.detector")

        self.detector_empty_config = Detector.objects.create(name="Empty Config Detector", class_name="test.detector", configuration={})

    def test_get_configuration_summary_full_config(self):
        """Test configuration summary with full configuration."""
        summary = DetectorConfigurationService.get_configuration_summary(self.detector_with_config)

        # Should include threshold, baseline, and minimum_events (first 3)
        self.assertIn("threshold×2.5", summary)
        self.assertIn("baseline 30d", summary)
        self.assertIn("min 10 events", summary)

        # Should not include all items (limited to 3)
        parts = summary.split(", ")
        self.assertLessEqual(len(parts), 3)

    def test_get_configuration_summary_no_config(self):
        """Test configuration summary with no configuration."""
        summary = DetectorConfigurationService.get_configuration_summary(self.detector_no_config)
        self.assertEqual(summary, "No configuration")

    def test_get_configuration_summary_empty_config(self):
        """Test configuration summary with empty configuration."""
        summary = DetectorConfigurationService.get_configuration_summary(self.detector_empty_config)
        self.assertEqual(summary, "No configuration")

    def test_get_configuration_summary_partial_config(self):
        """Test configuration summary with partial configuration."""
        detector = Detector.objects.create(
            name="Partial Config", class_name="test.detector", configuration={"threshold_multiplier": 1.5, "monitored_sources": ["IDMC", "ACLED", "HDX"]}
        )

        summary = DetectorConfigurationService.get_configuration_summary(detector)

        self.assertIn("threshold×1.5", summary)
        self.assertIn("monitors 3 sources", summary)

    def test_get_configuration_summary_variables_only(self):
        """Test configuration summary with only monitored variables."""
        detector = Detector.objects.create(name="Variables Only", class_name="test.detector", configuration={"monitored_variables": ["var1", "var2"]})

        summary = DetectorConfigurationService.get_configuration_summary(detector)
        self.assertEqual(summary, "monitors 2 variables")

    def test_get_configuration_summary_empty_lists(self):
        """Test configuration summary with empty monitoring lists."""
        detector = Detector.objects.create(
            name="Empty Lists", class_name="test.detector", configuration={"monitored_sources": [], "monitored_variables": [], "threshold_multiplier": 2.0}
        )

        summary = DetectorConfigurationService.get_configuration_summary(detector)
        self.assertEqual(summary, "threshold×2.0")

    def test_get_configuration_summary_limit_to_three(self):
        """Test that configuration summary limits to 3 items."""
        detector = Detector.objects.create(
            name="Many Configs",
            class_name="test.detector",
            configuration={
                "threshold_multiplier": 2.0,
                "baseline_days": 30,
                "minimum_events": 5,
                "minimum_displaced": 50,
                "monitored_sources": ["IDMC"],
                "monitored_variables": ["displacement"],
            },
        )

        summary = DetectorConfigurationService.get_configuration_summary(detector)
        parts = summary.split(", ")

        # Should have exactly 3 parts
        self.assertEqual(len(parts), 3)
        self.assertIn("threshold×2.0", parts[0])
        self.assertIn("baseline 30d", parts[1])
        self.assertIn("min 5 events", parts[2])
