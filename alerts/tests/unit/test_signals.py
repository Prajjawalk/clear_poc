"""Tests for alert signal handlers."""

from datetime import date, timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from alerts.models import Alert, ShockType
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class AlertSignalTest(TestCase):
    """Tests for alert signal handlers."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level
        )

        cls.source = Source.objects.create(
            name="Test Source",
            description="Test data source",
            type="api",
            class_name="TestSource"
        )

        cls.shock_type = ShockType.objects.create(name="Conflict")

    def test_alert_creation_signal(self):
        """Test that alert creation triggers post_save signal."""
        with patch('alerts.signals.logger.info') as mock_logger:
            alert = Alert.objects.create(
                title="Test Signal Alert",
                text="Testing signal handling",
                shock_type=self.shock_type,
                severity=3,
                shock_date=date.today(),
                valid_from=timezone.now(),
                valid_until=timezone.now() + timedelta(days=7),
                data_source=self.source,
                go_no_go=True,
            )

            # Should have logged the alert creation
            mock_logger.assert_called_with(
                f"New alert created: {alert.id} - {alert.title}"
            )

    def test_alert_locations_changed_signal(self):
        """Test that adding locations triggers m2m_changed signal and notifications."""
        alert = Alert.objects.create(
            title="Test Location Signal Alert",
            text="Testing location change signal",
            shock_type=self.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        with patch('alerts.signals.logger.info') as mock_logger:
            with patch('alerts.services.notifications.NotificationService.notify_new_alert') as mock_notify:
                # This should trigger the m2m_changed signal
                alert.locations.add(self.location)

                # Should have logged the location addition
                mock_logger.assert_any_call(
                    f"Alert {alert.id} locations added, triggering notifications"
                )

                # Should have called notification service
                mock_notify.assert_called_once_with(alert)

    def test_signal_with_notification_results(self):
        """Test signal handling with notification service results."""
        alert = Alert.objects.create(
            title="Test Notification Results Signal",
            text="Testing notification results logging",
            shock_type=self.shock_type,
            severity=4,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        # Mock notification service to return specific results
        mock_results = {
            'email_queued': 2,
            'internal_created': 3,
            'errors': 1
        }

        with patch('alerts.signals.logger.info') as mock_logger:
            with patch('alerts.services.notifications.NotificationService.notify_new_alert', return_value=mock_results):
                alert.locations.add(self.location)

                # Should have logged the results
                expected_message = (
                    f"Alert {alert.id} notifications: "
                    f"2 emails queued, 3 internal created, 1 errors"
                )
                mock_logger.assert_called_with(expected_message)

    def test_alert_update_does_not_trigger_creation_signal(self):
        """Test that updating an existing alert doesn't trigger creation signal."""
        alert = Alert.objects.create(
            title="Test Update Alert",
            text="Testing update behavior",
            shock_type=self.shock_type,
            severity=2,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        with patch('alerts.signals.logger.info') as mock_logger:
            # Update the alert
            alert.title = "Updated Alert Title"
            alert.save()

            # Should not have called logger for creation
            mock_logger.assert_not_called()

    def test_location_removal_does_not_trigger_notification(self):
        """Test that removing locations doesn't trigger notifications."""
        alert = Alert.objects.create(
            title="Test Location Removal",
            text="Testing location removal",
            shock_type=self.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(self.location)

        with patch('alerts.services.notifications.NotificationService.notify_new_alert') as mock_notify:
            # Remove location - this should not trigger notifications
            alert.locations.remove(self.location)

            # Should not have called notification service
            mock_notify.assert_not_called()

    def test_signal_with_multiple_locations(self):
        """Test signal handling when adding multiple locations."""
        alert = Alert.objects.create(
            title="Test Multiple Locations",
            text="Testing multiple location addition",
            shock_type=self.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        # Create second location
        location2 = Location.objects.create(
            name="Port Sudan",
            geo_id="SD002",
            admin_level=self.admin_level
        )

        with patch('alerts.services.notifications.NotificationService.notify_new_alert') as mock_notify:
            # Add multiple locations at once
            alert.locations.add(self.location, location2)

            # Should have called notification service once
            mock_notify.assert_called_once_with(alert)

    def test_signal_error_handling(self):
        """Test signal behavior when notification service raises an exception."""
        alert = Alert.objects.create(
            title="Test Error Handling",
            text="Testing error handling in signals",
            shock_type=self.shock_type,
            severity=5,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        with patch('alerts.services.notifications.NotificationService.notify_new_alert', side_effect=Exception("Test error")):
            with patch('alerts.signals.logger.info'):
                # This should not raise an exception even if notification service fails
                try:
                    alert.locations.add(self.location)
                except Exception:
                    self.fail("Signal handler should not raise exceptions")

    def test_signal_only_triggers_for_location_add(self):
        """Test that signal only triggers for 'post_add' action."""
        alert = Alert.objects.create(
            title="Test Action Specificity",
            text="Testing signal action specificity",
            shock_type=self.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )

        with patch('alerts.services.notifications.NotificationService.notify_new_alert') as mock_notify:
            # First add a location (should trigger)
            alert.locations.add(self.location)
            self.assertEqual(mock_notify.call_count, 1)

            # Clear locations (should not trigger additional notifications)
            alert.locations.clear()
            self.assertEqual(mock_notify.call_count, 1)  # Still just 1 call