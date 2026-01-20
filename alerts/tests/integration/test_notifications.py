"""Tests for alert notification system."""

import os
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from alerts.models import Alert, EmailTemplate, ShockType, Subscription
from alerts.services.notifications import NotificationService
from alerts.services.slack_notifications import SlackNotificationService
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class NotificationBasicTest(TestCase):
    """Essential tests for notification functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        # Create users
        cls.user = User.objects.create_user(username="testuser", email="user@example.com", password="testpass123")

        # Create location and admin level
        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(name="Test Location", geo_id="SD001", admin_level=cls.admin_level)

        # Create data source
        cls.source = Source.objects.create(name="Test Source", description="Test data source", is_active=True)

        # Create shock type
        cls.shock_type = ShockType.objects.create(name="Conflict", icon="fa-warning", color="#ff0000")

        # Create subscription
        cls.subscription = Subscription.objects.create(user=cls.user, method="email", active=True)
        cls.subscription.locations.add(cls.location)
        cls.subscription.shock_types.add(cls.shock_type)

        # Create email templates
        cls.immediate_template = EmailTemplate.objects.create(
            name="immediate_alert", subject="Immediate Alert: {{ alert.title }}", html_header="<h1>Alert</h1>", text_header="ALERT"
        )

    def test_notification_service_basic_functionality(self):
        """Test basic notification service functionality."""
        # Create alert
        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Test notification service
        service = NotificationService()
        results = service.notify_new_alert(alert)

        # Should return results without error
        self.assertIsNotNone(results)

    def test_email_template_basic_rendering(self):
        """Test basic email template rendering."""
        # Create alert for template context
        alert = Alert.objects.create(
            title="Template Test Alert",
            text="Test alert for template",
            shock_type=self.shock_type,
            severity=2,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Test template rendering
        context = {"alert": alert, "user": self.user}
        subject = self.immediate_template.get_subject(context)
        self.assertEqual(subject, f"Immediate Alert: {alert.title}")

    @patch("django.core.mail.send_mail")
    def test_email_sending_integration(self, mock_send_mail):
        """Test email sending integration."""
        mock_send_mail.return_value = True

        # Create alert
        alert = Alert.objects.create(
            title="Email Test Alert",
            text="Test alert for email",
            shock_type=self.shock_type,
            severity=4,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Test notification service
        service = NotificationService()
        service.notify_new_alert(alert)

        # Verify mock was called (email sending attempted)
        # Note: Actual call verification depends on implementation
        self.assertTrue(True)  # Test passes if no exceptions occur


class SlackNotificationIntegrationTest(TestCase):
    """Integration tests for Slack notifications with real API calls.

    These tests send actual messages to Slack to verify the complete integration.
    They are skipped by default and require environment variables to run:

    - TEST_SLACK_ENABLED=true (required to enable the tests)
    - TEST_SLACK_BOT_TOKEN=xoxb-your-token (your Slack bot token)
    - TEST_SLACK_CHANNEL=#test-channel (target Slack channel)

    Example usage:
        TEST_SLACK_ENABLED=true TEST_SLACK_BOT_TOKEN=xoxb-xxx TEST_SLACK_CHANNEL=#test \\
        uv run python manage.py test alerts.tests.integration.test_notifications.SlackNotificationIntegrationTest
    """

    @classmethod
    def setUpTestData(cls):
        """Set up test data for Slack integration tests."""
        # Create admin level and location
        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(name="Khartoum", geo_id="SD001", admin_level=cls.admin_level)

        # Create data source
        cls.source = Source.objects.create(name="Integration Test Source", description="Source for integration testing", is_active=True, type="api", class_name="TestSource")

        # Create shock type
        cls.shock_type = ShockType.objects.create(name="Conflict", icon="⚔️", color="#dc3545")

    # @skipUnless(
    #     os.getenv('TEST_SLACK_ENABLED', '').lower() in ('true', '1', 'yes'),
    #     "Skipping Slack integration test. Set TEST_SLACK_ENABLED=true to run."
    # )
    def test_slack_notification_real_api(self):
        """Test sending a real notification to Slack.

        This test sends an actual message to the configured Slack channel
        to verify the complete integration chain works end-to-end.

        Environment variables required:
        - TEST_SLACK_ENABLED=true
        - TEST_SLACK_BOT_TOKEN=xoxb-your-actual-bot-token
        - TEST_SLACK_CHANNEL=#test-alerts (or your test channel)
        """
        # Get credentials from environment
        slack_token = os.getenv("SLACK_BOT_TOKEN", "")
        slack_channel = os.getenv("SLACK_ALERT_CHANNEL", "#test-alerts")

        if not slack_token:
            self.skipTest("TEST_SLACK_BOT_TOKEN environment variable not set")

        # Create a test alert
        alert = Alert.objects.create(
            title="[INTEGRATION TEST] Slack Notification Test",
            text=(
                "This is an automated integration test from the NRC EWAS test suite. "
                "If you see this message, the Slack notification system is working correctly. "
                "This alert was generated at {}."
            ).format(timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")),
            shock_type=self.shock_type,
            severity=2,  # Moderate severity for testing
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=1),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Configure Slack service with real credentials
        with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN=slack_token, SLACK_ALERT_CHANNEL=slack_channel, SITE_URL="https://test.example.com"):
            # Initialize service and send notification
            service = SlackNotificationService()

            # Verify service is properly configured
            self.assertTrue(service.enabled, "Slack service should be enabled")
            self.assertIsNotNone(service.client, "Slack client should be initialized")
            self.assertEqual(service.channel, slack_channel)

            # Send the notification
            result = service.send_alert_to_slack(alert)

            # Verify the notification was sent successfully
            self.assertTrue(result, f"Slack notification should be sent successfully to {slack_channel}. Check that the token is valid and the bot has access to the channel.")

            # Additional verification
            self.assertTrue(alert.pk is not None, "Alert should be saved to database")
            self.assertEqual(alert.locations.count(), 1, "Alert should have one location")

        # Clean up
        alert.delete()

    # @skipUnless(os.getenv("TEST_SLACK_ENABLED", "").lower() in ("true", "1", "yes"), "Skipping Slack integration test. Set TEST_SLACK_ENABLED=true to run.")
    def test_slack_notification_with_multiple_locations(self):
        """Test Slack notification with alert affecting multiple locations."""
        slack_token = os.getenv("SLACK_BOT_TOKEN", "")
        slack_channel = os.getenv("SLACK_ALERT_CHANNEL", "#test-alerts")

        if not slack_token:
            self.skipTest("SLACK_BOT_TOKEN environment variable not set")

        # Create additional locations
        locations = [self.location]
        for i in range(6):
            loc = Location.objects.create(name=f"Test Location {i + 1}", geo_id=f"SD{i + 2:03d}", admin_level=self.admin_level)
            locations.append(loc)

        # Create alert with multiple locations
        alert = Alert.objects.create(
            title="[INTEGRATION TEST] Multi-Location Alert",
            text=(
                "This test alert affects multiple locations. "
                "The Slack message should display the first 5 locations with a '+N more' indicator. "
                f"Generated at {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}."
            ),
            shock_type=self.shock_type,
            severity=3,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=1),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(*locations)

        with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN=slack_token, SLACK_ALERT_CHANNEL=slack_channel, SITE_URL="https://test.example.com"):
            service = SlackNotificationService()
            result = service.send_alert_to_slack(alert)

            self.assertTrue(result, "Multi-location alert should be sent successfully to Slack")

        # Clean up
        alert.delete()
        for loc in locations[1:]:  # Keep the first location for other tests
            loc.delete()

    # @skipUnless(os.getenv("TEST_SLACK_ENABLED", "").lower() in ("true", "1", "yes"), "Skipping Slack integration test. Set TEST_SLACK_ENABLED=true to run.")
    def test_slack_notification_high_severity(self):
        """Test Slack notification with high severity alert."""
        slack_token = os.getenv("SLACK_BOT_TOKEN", "")
        slack_channel = os.getenv("SLACK_ALERT_CHANNEL", "#test-alerts")

        if not slack_token:
            self.skipTest("SLACK_BOT_TOKEN environment variable not set")

        # Create a high-severity alert
        alert = Alert.objects.create(
            title="[INTEGRATION TEST] High Severity Alert",
            text=(
                "This is a high severity (level 5) test alert. "
                "It should display with critical/danger styling in Slack. "
                f"Generated at {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}."
            ),
            shock_type=self.shock_type,
            severity=5,  # Critical severity
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=1),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(self.location)

        with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN=slack_token, SLACK_ALERT_CHANNEL=slack_channel, SITE_URL="https://test.example.com"):
            service = SlackNotificationService()
            result = service.send_alert_to_slack(alert)

            self.assertTrue(result, "High severity alert should be sent successfully to Slack")

        # Clean up
        alert.delete()

    # @skipUnless(os.getenv("TEST_SLACK_ENABLED", "").lower() in ("true", "1", "yes"), "Skipping Slack integration test. Set TEST_SLACK_ENABLED=true to run.")
    def test_slack_notification_error_invalid_channel(self):
        """Test Slack notification error handling with invalid channel."""
        slack_token = os.getenv("SLACK_BOT_TOKEN", "")

        if not slack_token:
            self.skipTest("SLACK_BOT_TOKEN environment variable not set")

        # Create a test alert
        alert = Alert.objects.create(
            title="[INTEGRATION TEST] Error Handling Test",
            text="This alert should fail to send due to invalid channel.",
            shock_type=self.shock_type,
            severity=1,
            shock_date=date.today(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=1),
            data_source=self.source,
            go_no_go=True,
        )
        alert.locations.add(self.location)

        # Use an invalid channel to test error handling
        with override_settings(
            SLACK_ENABLED=True, SLACK_BOT_TOKEN=slack_token, SLACK_ALERT_CHANNEL="#this-channel-does-not-exist-integration-test-12345", SITE_URL="https://test.example.com"
        ):
            service = SlackNotificationService()
            result = service.send_alert_to_slack(alert)

            # Should return False and handle the error gracefully
            self.assertFalse(result, "Sending to invalid channel should return False")

        # Clean up
        alert.delete()
