"""Central notification service for all delivery methods."""

import logging
from typing import Dict, List, Optional

from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from alerts.models import Alert, EmailTemplate, Subscription, UserAlert
from notifications.models import InternalNotification

logger = logging.getLogger(__name__)


class NotificationService:
    """Central notification service for all delivery methods."""

    def notify_new_alert(self, alert: Alert) -> Dict[str, int]:
        """
        Send notifications for a new alert.

        Returns dict with counts of notifications sent by type.
        """
        results = {
            'email_queued': 0,
            'internal_created': 0,
            'slack_sent': 0,
            'errors': 0
        }

        # Send to Slack channel if enabled
        try:
            from alerts.services.slack_notifications import SlackNotificationService
            slack_service = SlackNotificationService()
            if slack_service.send_alert_to_slack(alert):
                results['slack_sent'] = 1
        except Exception as e:
            logger.error(f"Failed to send Slack notification for alert {alert.id}: {e}")

        # Get matching subscriptions
        subscriptions = self.get_matching_subscriptions(alert)

        # Process immediate notifications
        immediate_subs = subscriptions.filter(frequency='immediate')

        for sub in immediate_subs:
            try:
                # Check master email switch
                if sub.user.profile.email_notifications_enabled:
                    self.queue_email_notification(sub.user, alert)
                    results['email_queued'] += 1

                # Always create internal notification
                self.create_internal_notification(sub.user, alert)
                results['internal_created'] += 1

            except Exception as e:
                logger.error(f"Failed to notify user {sub.user.id} for alert {alert.id}: {e}")
                results['errors'] += 1

        logger.info(
            f"Alert {alert.id} notifications sent: "
            f"{results['email_queued']} emails, {results['internal_created']} internal, "
            f"{results['slack_sent']} slack"
        )

        return results

    def get_matching_subscriptions(self, alert: Alert):
        """
        Get all subscriptions matching the alert criteria.

        Matches subscriptions based on:
        - Shock type
        - Location hierarchy (including parent locations)

        Note: No go_no_go check - all alerts are sent.
        """
        # Collect all locations including parent hierarchy
        # This allows state-level subscriptions to match city-level alerts
        alert_location_ids = set()

        for loc in alert.locations.all():
            # Add the location itself
            alert_location_ids.add(loc.id)

            # Add all parent locations up the hierarchy
            parent = loc.parent
            while parent:
                alert_location_ids.add(parent.id)
                parent = parent.parent

        # Match subscriptions against location hierarchy
        return Subscription.objects.filter(
            active=True,
            locations__id__in=alert_location_ids,
            shock_types=alert.shock_type
        ).select_related('user', 'user__profile').distinct()

    def queue_email_notification(self, user: User, alert: Alert):
        """Queue an email notification for async sending."""
        from alerts.tasks import send_immediate_alert_email

        # Queue the task for async processing
        send_immediate_alert_email.delay(user.id, alert.id)

        logger.info(f"Queued email notification for user {user.id}, alert {alert.id}")

    def create_internal_notification(self, user: User, alert: Alert):
        """Create an internal notification for the user."""
        notification = InternalNotification.create_alert_notification(user, alert)

        logger.info(f"Created internal notification {notification.id} for user {user.id}")

        return notification

    def render_email_from_template(
        self,
        template_name: str,
        user: User,
        alert: Optional[Alert] = None,
        alerts: Optional[List[Alert]] = None,
        **extra_context
    ) -> Dict[str, str]:
        """Render email content using database templates."""
        try:
            template = EmailTemplate.objects.get(name=template_name, active=True)
        except EmailTemplate.DoesNotExist:
            logger.error(f"Email template '{template_name}' not found or inactive")
            # Fallback to hardcoded template if database template missing
            return self.render_fallback_template(template_name, user, alert, alerts)

        # Build context for template rendering
        context = {
            'user': user,
            'alert': alert,
            'alerts': alerts,
            'unsubscribe_url': self.build_unsubscribe_url(user),
            'settings_url': self.build_settings_url(user),
            'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            **extra_context  # Add any additional context variables
        }

        # Get rendered subject
        rendered_subject = template.get_subject(context)

        # Render HTML and text content
        html_content = template.render_html(context)
        text_content = template.render_text(context)

        return {
            'subject': rendered_subject,
            'html_content': html_content,
            'text_content': text_content
        }

    def render_fallback_template(
        self,
        template_name: str,
        user: User,
        alert: Optional[Alert] = None,
        alerts: Optional[List[Alert]] = None
    ) -> Dict[str, str]:
        """Render hardcoded fallback template when database template is missing."""
        if template_name == 'individual_alert' and alert:
            subject = f"[EWAS Alert] {alert.title}"

            text_content = f"""
New Alert: {alert.title}

Dear {user.first_name or 'Subscriber'},

A new {alert.shock_type.name} alert has been issued that matches your subscription:

Title: {alert.title}
Date: {alert.shock_date}
Severity: {alert.severity_display}

{alert.text}

View full alert: {self.build_alert_url(alert)}

---
To unsubscribe: {self.build_unsubscribe_url(user)}
To update preferences: {self.build_settings_url(user)}
"""

            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .alert-header {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
        .alert-content {{ margin: 20px 0; }}
        .footer {{ font-size: 12px; color: #6c757d; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="alert-header">
            <h2>New Alert: {alert.title}</h2>
        </div>

        <p>Dear {user.first_name or 'Subscriber'},</p>

        <p>A new <strong>{alert.shock_type.name}</strong> alert has been issued that matches your subscription:</p>

        <div class="alert-content">
            <p><strong>Date:</strong> {alert.shock_date}</p>
            <p><strong>Severity:</strong> {alert.severity_display}</p>

            <div>{alert.text}</div>
        </div>

        <p><a href="{self.build_alert_url(alert)}">View full alert</a></p>

        <div class="footer">
            <hr>
            <p>
                <a href="{self.build_unsubscribe_url(user)}">Unsubscribe</a> |
                <a href="{self.build_settings_url(user)}">Update Preferences</a>
            </p>
        </div>
    </div>
</body>
</html>
"""

            return {
                'subject': subject,
                'html_content': html_content,
                'text_content': text_content
            }

        # Default fallback for unknown templates
        return {
            'subject': f"[EWAS] Notification",
            'html_content': "<p>Notification content not available</p>",
            'text_content': "Notification content not available"
        }

    def build_unsubscribe_url(self, user: User) -> str:
        """Build unsubscribe URL for the user."""
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        path = reverse('alerts:subscription_list')
        return f"{base_url}{path}"

    def build_settings_url(self, user: User) -> str:
        """Build settings/preferences URL for the user."""
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        path = reverse('alerts:subscription_list')
        return f"{base_url}{path}"

    def build_alert_url(self, alert: Alert) -> str:
        """Build URL to view the alert."""
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        path = reverse('alerts:alert_detail', kwargs={'pk': alert.pk})
        return f"{base_url}{path}"

    def process_daily_digest(self):
        """Process and send daily digest emails."""
        yesterday = timezone.now() - timezone.timedelta(days=1)

        # Get users with daily subscription
        daily_subs = Subscription.objects.filter(
            active=True,
            frequency='daily'
        ).select_related('user', 'user__profile').distinct()

        count = 0
        for sub in daily_subs:
            if not sub.user.profile.email_notifications_enabled:
                continue

            # Get yesterday's alerts matching subscription
            alerts = Alert.objects.filter(
                created_at__gte=yesterday,
                locations__in=sub.locations.all(),
                shock_types__in=sub.shock_types.all()
            ).distinct()

            if alerts.exists():
                from alerts.tasks import send_digest_email
                send_digest_email.delay(
                    sub.user.id,
                    list(alerts.values_list('id', flat=True)),
                    'daily'
                )
                count += 1

        logger.info(f"Queued {count} daily digest emails")
        return count

    def process_weekly_digest(self):
        """Process and send weekly digest emails."""
        last_week = timezone.now() - timezone.timedelta(days=7)

        # Get users with weekly subscription
        weekly_subs = Subscription.objects.filter(
            active=True,
            frequency='weekly'
        ).select_related('user', 'user__profile').distinct()

        count = 0
        for sub in weekly_subs:
            if not sub.user.profile.email_notifications_enabled:
                continue

            # Get last week's alerts matching subscription
            alerts = Alert.objects.filter(
                created_at__gte=last_week,
                locations__in=sub.locations.all(),
                shock_types__in=sub.shock_types.all()
            ).distinct()

            if alerts.exists():
                from alerts.tasks import send_digest_email
                send_digest_email.delay(
                    sub.user.id,
                    list(alerts.values_list('id', flat=True)),
                    'weekly'
                )
                count += 1

        logger.info(f"Queued {count} weekly digest emails")
        return count