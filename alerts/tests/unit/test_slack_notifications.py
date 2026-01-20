"""Unit tests for Slack notification service."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from alerts.models import Alert, ShockType
from alerts.services.slack_notifications import SlackNotificationService
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class SlackNotificationServiceTest(TestCase):
    """Test SlackNotificationService functionality."""

    def setUp(self):
        """Set up test data."""
        self.shock_type = ShockType.objects.create(name="Conflict", icon="⚔️", color="#dc3545")
        self.source = Source.objects.create(name="Test Source", type="api", is_active=True, class_name="TestSource")
        self.admin_level = AdmLevel.objects.create(code="1", name="Test State Level")
        self.location = Location.objects.create(name="Test Location", geo_id="TL001", admin_level=self.admin_level)

    @override_settings(SLACK_ENABLED=False)
    def test_slack_disabled(self):
        """Test that service does nothing when Slack is disabled."""
        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        result = service.send_alert_to_slack(alert)

        self.assertFalse(result)
        self.assertIsNone(service.client)

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    @patch("alerts.services.notifications.NotificationService.notify_new_alert")
    def test_slack_send_success(self, mock_notify, mock_webclient):
        """Test successful Slack message sending."""
        # Mock the Slack API response
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Critical Security Alert",
            text="This is a test alert with important information.",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=5,
        )
        alert.locations.add(self.location)

        result = service.send_alert_to_slack(alert)

        self.assertTrue(result)
        mock_client.chat_postMessage.assert_called_once()

        # Check the message structure
        call_args = mock_client.chat_postMessage.call_args
        self.assertEqual(call_args[1]["channel"], "#test-channel")
        self.assertIn("blocks", call_args[1])
        self.assertIn("text", call_args[1])

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_slack_api_error(self, mock_webclient):
        """Test handling of Slack API errors."""
        from slack_sdk.errors import SlackApiError

        # Mock the Slack API error
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = SlackApiError(message="channel_not_found", response={"error": "channel_not_found"})
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        result = service.send_alert_to_slack(alert)

        self.assertFalse(result)

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    @patch("alerts.services.notifications.NotificationService.notify_new_alert")
    def test_message_structure(self, mock_notify, mock_webclient):
        """Test the structure of Slack message blocks."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        service.send_alert_to_slack(alert)

        call_args = mock_client.chat_postMessage.call_args
        blocks = call_args[1]["blocks"]

        # Check block types
        self.assertEqual(blocks[0]["type"], "header")
        self.assertEqual(blocks[1]["type"], "section")
        self.assertEqual(blocks[2]["type"], "section")
        self.assertEqual(blocks[3]["type"], "context")
        self.assertEqual(blocks[4]["type"], "actions")

        # Check header contains title
        self.assertIn("Test Alert", blocks[0]["text"]["text"])

        # Check action button exists
        self.assertEqual(blocks[4]["elements"][0]["type"], "button")

    def test_severity_config(self):
        """Test severity emoji and styling configuration."""
        service = SlackNotificationService()

        config_low = service._get_severity_config(1)
        self.assertEqual(config_low["emoji"], "🟢")

        config_high = service._get_severity_config(4)
        self.assertEqual(config_high["emoji"], "🔴")
        self.assertEqual(config_high["button_style"], "danger")

        config_critical = service._get_severity_config(5)
        self.assertEqual(config_critical["emoji"], "🔴")
        self.assertEqual(config_critical["button_style"], "danger")

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    @patch("alerts.services.notifications.NotificationService.notify_new_alert")
    def test_long_text_truncation(self, mock_notify, mock_webclient):
        """Test that long alert text is truncated."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        # Create alert with very long text
        long_text = "A" * 600

        alert = Alert.objects.create(
            title="Test Alert",
            text=long_text,
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        service.send_alert_to_slack(alert)

        call_args = mock_client.chat_postMessage.call_args
        blocks = call_args[1]["blocks"]

        # Find the text block
        text_block = blocks[2]
        self.assertIn("...", text_block["text"]["text"])
        self.assertLess(len(text_block["text"]["text"]), 600)

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel", SITE_URL="https://example.com")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_alert_url_generation(self, mock_webclient):
        """Test that alert URLs are correctly generated."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        service.send_alert_to_slack(alert)

        call_args = mock_client.chat_postMessage.call_args
        blocks = call_args[1]["blocks"]

        # Check action button URL
        button = blocks[4]["elements"][0]
        self.assertIn("https://example.com", button["url"])
        self.assertIn(str(alert.pk), button["url"])

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_multiple_locations_display(self, mock_webclient):
        """Test that multiple locations are properly formatted."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        # Create multiple locations
        locations = []
        for i in range(7):
            loc = Location.objects.create(name=f"Location {i}", geo_id=f"LOC{i:03d}", admin_level=self.admin_level)
            locations.append(loc)

        alert = Alert.objects.create(
            title="Multi-location Alert",
            text="Alert affecting multiple locations",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=4,
        )
        alert.locations.add(*locations)

        service.send_alert_to_slack(alert)

        call_args = mock_client.chat_postMessage.call_args
        blocks = call_args[1]["blocks"]

        # Find the fields section
        section = blocks[1]
        location_field = None
        for field in section["fields"]:
            if "Locations" in field["text"]:
                location_field = field
                break

        self.assertIsNotNone(location_field)
        # Should show first 5 locations plus "(+2 more)"
        self.assertIn("(+2 more)", location_field["text"])

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_slack_response_not_ok(self, mock_webclient):
        """Test handling when Slack API returns ok=False."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": False, "error": "some_error"}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        result = service.send_alert_to_slack(alert)

        self.assertFalse(result)

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="")
    def test_missing_token(self):
        """Test that service handles missing token gracefully."""
        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        result = service.send_alert_to_slack(alert)

        self.assertFalse(result)
        self.assertIsNone(service.client)

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_all_severity_levels(self, mock_webclient):
        """Test message formatting for all severity levels."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        for severity in [1, 2, 3, 4, 5]:
            alert = Alert.objects.create(
                title=f"Severity {severity} Alert",
                text="Test alert text",
                shock_type=self.shock_type,
                data_source=self.source,
                shock_date="2025-01-01",
                valid_from="2025-01-01T00:00:00Z",
                valid_until="2025-12-31T23:59:59Z",
                severity=severity,
            )
            alert.locations.add(self.location)

            result = service.send_alert_to_slack(alert)
            self.assertTrue(result)

            # Verify severity config
            config = service._get_severity_config(severity)
            self.assertIn("emoji", config)
            self.assertIn("button_style", config)

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_unexpected_exception_handling(self, mock_webclient):
        """Test handling of unexpected exceptions."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("Unexpected error")
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        result = service.send_alert_to_slack(alert)

        self.assertFalse(result)

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_block_structure_completeness(self, mock_webclient):
        """Test that all required blocks are present and properly structured."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert = Alert.objects.create(
            title="Complete Block Test",
            text="Testing complete block structure",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=3,
        )
        alert.locations.add(self.location)

        service.send_alert_to_slack(alert)

        call_args = mock_client.chat_postMessage.call_args
        blocks = call_args[1]["blocks"]

        # Verify all block types
        block_types = [block["type"] for block in blocks]
        expected_types = ["header", "section", "section", "context", "actions"]
        self.assertEqual(block_types, expected_types)

        # Verify header block
        self.assertIn("text", blocks[0])
        self.assertEqual(blocks[0]["text"]["type"], "plain_text")

        # Verify fields section
        self.assertIn("fields", blocks[1])
        fields = blocks[1]["fields"]
        self.assertEqual(len(fields), 4)  # Shock Type, Severity, Date, Locations

        # Verify text section
        self.assertIn("text", blocks[2])
        self.assertEqual(blocks[2]["text"]["type"], "mrkdwn")

        # Verify context block
        self.assertIn("elements", blocks[3])
        self.assertGreater(len(blocks[3]["elements"]), 0)

        # Verify actions block
        self.assertIn("elements", blocks[4])
        self.assertEqual(len(blocks[4]["elements"]), 1)
        self.assertEqual(blocks[4]["elements"][0]["type"], "button")

    @override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="xoxb-test-token", SLACK_ALERT_CHANNEL="#test-channel")
    @patch("alerts.services.slack_notifications.WebClient")
    def test_fallback_text(self, mock_webclient):
        """Test that fallback text is provided for notifications."""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_webclient.return_value = mock_client

        service = SlackNotificationService()

        alert_title = "Important Security Alert"
        alert = Alert.objects.create(
            title=alert_title,
            text="Test alert text",
            shock_type=self.shock_type,
            data_source=self.source,
            shock_date="2025-01-01",
            valid_from="2025-01-01T00:00:00Z",
            valid_until="2025-12-31T23:59:59Z",
            severity=5,
        )
        alert.locations.add(self.location)

        service.send_alert_to_slack(alert)

        call_args = mock_client.chat_postMessage.call_args
        fallback_text = call_args[1]["text"]

        # Verify fallback text includes alert title
        self.assertIn(alert_title, fallback_text)

    def test_severity_config_edge_cases(self):
        """Test severity config for edge cases and invalid values."""
        service = SlackNotificationService()

        # Test default for invalid severity
        config = service._get_severity_config(0)
        self.assertEqual(config["emoji"], "⚪")
        self.assertEqual(config["button_style"], "primary")

        config = service._get_severity_config(10)
        self.assertEqual(config["emoji"], "⚪")

        # Test all valid severities
        for severity in [1, 2, 3, 4, 5]:
            config = service._get_severity_config(severity)
            self.assertIn("emoji", config)
            self.assertIn("button_style", config)
            self.assertIn(config["button_style"], ["primary", "danger"])
