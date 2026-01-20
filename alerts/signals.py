"""Signal handlers for alerts app."""

import logging

from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from .models import Alert

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Alert)
def handle_new_alert_created(sender, instance, created, **kwargs):
    """Log when a new alert is created."""
    if created:
        logger.info(f"New alert created: {instance.id} - {instance.title}")


@receiver(m2m_changed, sender=Alert.locations.through)
def handle_alert_locations_changed(sender, instance, action, **kwargs):
    """Trigger notifications when alert locations are set."""
    if action == 'post_add':
        logger.info(f"Alert {instance.id} locations added, triggering notifications")

        try:
            # Import here to avoid circular imports
            from alerts.services.notifications import NotificationService

            service = NotificationService()
            results = service.notify_new_alert(instance)

            logger.info(
                f"Alert {instance.id} notifications sent: "
                f"{results['email_queued']} emails, "
                f"{results['internal_created']} internal"
            )

            logger.info(
                f"Alert {instance.id} notifications: "
                f"{results['email_queued']} emails queued, "
                f"{results['internal_created']} internal created, "
                f"{results['errors']} errors"
            )
        except Exception as e:
            logger.error(f"Failed to send notifications for alert {instance.id}: {e}")