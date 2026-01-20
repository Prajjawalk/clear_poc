"""Management command to test Slack notification integration."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from alerts.models import Alert
from alerts.services.slack_notifications import SlackNotificationService


class Command(BaseCommand):
    """Test Slack notification by sending a test alert."""

    help = 'Send a test alert to Slack to verify integration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--alert-id',
            type=int,
            help='ID of an existing alert to send (optional)'
        )

    def handle(self, *args, **options):
        """Execute the command."""
        service = SlackNotificationService()

        if not service.enabled:
            self.stdout.write(
                self.style.WARNING('Slack is disabled. Set SLACK_ENABLED=True in your .env file')
            )
            return

        if not service.client:
            self.stdout.write(
                self.style.ERROR('Slack client not initialized. Check SLACK_BOT_TOKEN in your .env file')
            )
            return

        self.stdout.write(f'Slack enabled: {service.enabled}')
        self.stdout.write(f'Slack channel: {service.channel}')

        # Get or use existing alert
        alert_id = options.get('alert_id')

        if alert_id:
            try:
                alert = Alert.objects.get(id=alert_id)
                self.stdout.write(f'Using existing alert: {alert.title} (ID: {alert.id})')
            except Alert.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Alert with ID {alert_id} not found')
                )
                return
        else:
            # Get the most recent alert
            alert = Alert.objects.order_by('-created_at').first()
            if not alert:
                self.stdout.write(
                    self.style.ERROR('No alerts found in database. Create an alert first.')
                )
                return
            self.stdout.write(f'Using most recent alert: {alert.title} (ID: {alert.id})')

        # Send to Slack
        self.stdout.write('Sending alert to Slack...')
        result = service.send_alert_to_slack(alert)

        if result:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Alert sent successfully to {service.channel}')
            )
        else:
            self.stdout.write(
                self.style.ERROR('✗ Failed to send alert. Check logs for details.')
            )
