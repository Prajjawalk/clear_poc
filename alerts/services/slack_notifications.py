"""Slack notification service for alerts."""

import logging
from typing import Optional

from django.conf import settings
from django.urls import reverse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackNotificationService:
    """Service for sending alert notifications to Slack."""

    def __init__(self):
        """Initialize Slack client."""
        self.enabled = getattr(settings, 'SLACK_ENABLED', False)
        self.token = getattr(settings, 'SLACK_BOT_TOKEN', '')
        self.channel = getattr(settings, 'SLACK_ALERT_CHANNEL', '#alerts')

        if self.enabled and self.token:
            self.client = WebClient(token=self.token)
        else:
            self.client = None

    def send_alert_to_slack(self, alert) -> bool:
        """
        Send an alert notification to Slack channel.

        Args:
            alert: Alert instance to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Slack notifications disabled, skipping")
            return False

        if not self.client:
            logger.warning("Slack client not initialized, skipping notification")
            return False

        try:
            # Build the message
            blocks = self._build_alert_blocks(alert)

            # Send to Slack
            response = self.client.chat_postMessage(
                channel=self.channel,
                blocks=blocks,
                text=f"New Alert: {alert.title}"  # Fallback text for notifications
            )

            if response['ok']:
                logger.info(f"Alert {alert.id} sent to Slack channel {self.channel}")
                return True
            else:
                logger.error(f"Slack API returned ok=False for alert {alert.id}")
                return False

        except SlackApiError as e:
            logger.error(f"Slack API error sending alert {alert.id}: {e.response['error']}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending alert {alert.id} to Slack: {e}")
            return False

    def _build_alert_blocks(self, alert):
        """
        Build Slack Block Kit message for an alert.

        Args:
            alert: Alert instance

        Returns:
            List of Slack block objects
        """
        # Severity emoji and color
        severity_config = self._get_severity_config(alert.severity)

        # Build alert URL
        site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        alert_path = reverse('alerts:alert_detail', kwargs={'pk': alert.pk})
        alert_url = f"{site_url}{alert_path}"

        # Format locations
        location_names = ', '.join([loc.name for loc in alert.locations.all()[:5]])
        if alert.locations.count() > 5:
            location_names += f" (+{alert.locations.count() - 5} more)"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_config['emoji']} {alert.title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Shock Type:*\n{alert.shock_type.icon} {alert.shock_type.name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity_config['emoji']} {alert.severity_display}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Date:*\n{str(alert.shock_date)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Locations:*\n{location_names}"
                    }
                ]
            }
        ]

        # Add alert text (truncate if too long)
        alert_text = alert.text
        if len(alert_text) > 500:
            alert_text = alert_text[:497] + "..."

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": alert_text
            }
        })

        # Add footer with data source
        from django.utils import timezone
        created_str = timezone.localtime(alert.created_at).strftime('%Y-%m-%d %H:%M UTC') if alert.created_at else 'Unknown'

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Source: {alert.data_source.name} | Created: {created_str}"
                }
            ]
        })

        # Add action button
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Alert Details",
                        "emoji": True
                    },
                    "url": alert_url,
                    "style": severity_config['button_style']
                }
            ]
        })

        return blocks

    def _get_severity_config(self, severity: int) -> dict:
        """
        Get emoji and styling for severity level.

        Args:
            severity: Severity level (1-5)

        Returns:
            Dict with emoji and button_style
        """
        configs = {
            1: {"emoji": "🟢", "button_style": "primary"},   # Low
            2: {"emoji": "🟡", "button_style": "primary"},   # Moderate
            3: {"emoji": "🟠", "button_style": "primary"},   # High
            4: {"emoji": "🔴", "button_style": "danger"},    # Very High
            5: {"emoji": "🔴", "button_style": "danger"},    # Critical
        }
        return configs.get(severity, {"emoji": "⚪", "button_style": "primary"})
