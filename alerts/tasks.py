"""Celery tasks for alert notifications."""

import logging
from typing import List

from celery import shared_task
from celery.schedules import crontab
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from alerts.models import Alert, EmailTemplate, UserAlert
from alerts.services.notifications import NotificationService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_immediate_alert_email(self, user_id: int, alert_id: int):
    """Send immediate alert notification email using database templates."""
    try:
        user = User.objects.get(pk=user_id)
        alert = Alert.objects.get(pk=alert_id)

        # Double-check email notifications are enabled
        if not user.profile.email_notifications_enabled:
            logger.info(f"Email notifications disabled for user {user_id}")
            return "Email notifications disabled for user"

        # Check if email is verified
        if not user.profile.email_verified:
            logger.warning(f"Email not verified for user {user_id}")
            return "Email not verified"

        # Get email content from database template
        service = NotificationService()
        email_content = service.render_email_from_template(
            template_name='individual_alert',
            user=user,
            alert=alert
        )

        # Send email using Django's EmailMultiAlternatives
        msg = EmailMultiAlternatives(
            subject=email_content['subject'],
            body=email_content['text_content'],
            from_email=getattr(settings, 'EMAIL_DEFAULT_FROM', settings.DEFAULT_FROM_EMAIL),
            to=[user.email]
        )
        msg.attach_alternative(email_content['html_content'], "text/html")

        # Send email with detailed error handling
        try:
            logger.info(f"Attempting to send alert email to {user.email} for alert {alert_id}")
            msg.send(fail_silently=False)
            logger.info(f"Alert email sent successfully to {user.email}")
        except Exception as email_error:
            logger.error(f"SMTP Error sending alert to {user.email}: {email_error}")
            logger.error(f"Email error type: {type(email_error).__name__}")
            raise email_error

        # Update tracking
        UserAlert.objects.update_or_create(
            user=user,
            alert=alert,
            defaults={'received_at': timezone.now()}
        )

        logger.info(
            'email_notification_sent',
            extra={
                'user_id': user_id,
                'alert_id': alert_id,
                'template': 'individual_alert',
                'status': 'success'
            }
        )

        return f"Email sent successfully to {user.email}"

    except (Alert.DoesNotExist, User.DoesNotExist) as exc:
        # Don't retry if alert or user was deleted
        logger.warning(
            'alert_or_user_not_found',
            extra={
                'user_id': user_id,
                'alert_id': alert_id,
                'error': str(exc)
            }
        )
        return f"Alert or user no longer exists: {exc}"

    except EmailTemplate.DoesNotExist:
        logger.error(
            'email_template_missing',
            extra={
                'template_name': 'individual_alert',
                'user_id': user_id,
                'alert_id': alert_id
            }
        )
        raise

    except Exception as exc:
        logger.error(
            'email_send_failed',
            extra={
                'user_id': user_id,
                'alert_id': alert_id,
                'error': str(exc)
            }
        )
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_digest_email(self, user_id: int, alert_ids: List[int], frequency: str):
    """Send digest email with multiple alerts."""
    try:
        user = User.objects.get(pk=user_id)
        alerts = Alert.objects.filter(id__in=alert_ids).order_by('-shock_date')

        if not alerts.exists():
            logger.info(f"No alerts found for digest email to user {user_id}")
            return "No alerts to send"

        # Double-check email notifications are enabled
        if not user.profile.email_notifications_enabled:
            logger.info(f"Email notifications disabled for user {user_id}")
            return "Email notifications disabled"

        # Check if email is verified
        if not user.profile.email_verified:
            logger.warning(f"Email not verified for user {user_id}")
            return "Email not verified"

        # Determine template name based on frequency
        template_name = f"{frequency}_digest"

        # Get email content from database template
        service = NotificationService()
        email_content = service.render_email_from_template(
            template_name=template_name,
            user=user,
            alerts=list(alerts)
        )

        # Send email
        msg = EmailMultiAlternatives(
            subject=email_content['subject'],
            body=email_content['text_content'],
            from_email=getattr(settings, 'EMAIL_DEFAULT_FROM', settings.DEFAULT_FROM_EMAIL),
            to=[user.email]
        )
        msg.attach_alternative(email_content['html_content'], "text/html")

        # Send email with detailed error handling
        try:
            logger.info(f"Attempting to send {frequency} digest email to {user.email}")
            msg.send(fail_silently=False)
            logger.info(f"{frequency} digest email sent successfully to {user.email}")
        except Exception as email_error:
            logger.error(f"SMTP Error sending {frequency} digest to {user.email}: {email_error}")
            logger.error(f"Email error type: {type(email_error).__name__}")
            raise email_error

        # Update tracking for all alerts
        for alert in alerts:
            UserAlert.objects.update_or_create(
                user=user,
                alert=alert,
                defaults={'received_at': timezone.now()}
            )

        logger.info(
            f"{frequency}_digest_sent",
            extra={
                'user_id': user_id,
                'alert_count': len(alert_ids),
                'frequency': frequency,
                'status': 'success'
            }
        )

        return f"{frequency.capitalize()} digest sent to {user.email} with {len(alerts)} alerts"

    except User.DoesNotExist as exc:
        # Don't retry if user was deleted
        logger.warning(
            f"{frequency}_digest_user_not_found",
            extra={
                'user_id': user_id,
                'alert_count': len(alert_ids),
                'error': str(exc)
            }
        )
        return f"User no longer exists: {exc}"

    except Exception as exc:
        logger.error(
            f"{frequency}_digest_failed",
            extra={
                'user_id': user_id,
                'alert_count': len(alert_ids),
                'error': str(exc)
            }
        )
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_daily_digest():
    """Send daily digest emails to all subscribed users."""
    logger.info("Starting daily digest task")

    service = NotificationService()
    count = service.process_daily_digest()

    logger.info(f"Daily digest task completed: {count} emails queued")
    return f"Queued {count} daily digest emails"


@shared_task
def send_weekly_digest():
    """Send weekly digest emails to all subscribed users."""
    logger.info("Starting weekly digest task")

    service = NotificationService()
    count = service.process_weekly_digest()

    logger.info(f"Weekly digest task completed: {count} emails queued")
    return f"Queued {count} weekly digest emails"


@shared_task
def send_monthly_digest():
    """Send monthly digest emails to all subscribed users."""
    logger.info("Starting monthly digest task")

    last_month = timezone.now() - timezone.timedelta(days=30)

    from alerts.models import Subscription

    # Get users with monthly subscription
    monthly_subs = Subscription.objects.filter(
        active=True,
        frequency='monthly'
    ).select_related('user', 'user__profile').distinct()

    count = 0
    for sub in monthly_subs:
        if not sub.user.profile.email_notifications_enabled:
            continue

        # Get last month's alerts matching subscription
        alerts = Alert.objects.filter(
            created_at__gte=last_month,
            locations__in=sub.locations.all(),
            shock_types__in=sub.shock_types.all()
        ).distinct()

        if alerts.exists():
            send_digest_email.delay(
                sub.user.id,
                list(alerts.values_list('id', flat=True)),
                'monthly'
            )
            count += 1

    logger.info(f"Monthly digest task completed: {count} emails queued")
    return f"Queued {count} monthly digest emails"


@shared_task
def cleanup_expired_notifications():
    """Clean up expired internal notifications."""
    from notifications.models import InternalNotification

    expired = InternalNotification.objects.filter(
        expires_at__lt=timezone.now()
    )
    count = expired.count()
    expired.delete()

    logger.info(f"Cleaned up {count} expired notifications")
    return f"Deleted {count} expired notifications"


@shared_task
def send_email_verification(user_id: int):
    """Send email verification to user."""
    logger.info(f"CELERY TASK STARTED: send_email_verification for user_id={user_id}")
    try:
        user = User.objects.get(pk=user_id)

        if user.profile.email_verified:
            return "Email already verified"

        # Generate token if not exists
        if not user.profile.email_verification_token:
            user.profile.generate_verification_token()

        # Get email content from database template
        service = NotificationService()
        verification_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/users/verify-email/{user.profile.email_verification_token}/"

        # Pass verification URL as context to template
        email_content = service.render_email_from_template(
            template_name='email_verification',
            user=user,
            verification_url=verification_url
        )

        # Send email
        msg = EmailMultiAlternatives(
            subject=email_content.get('subject', 'Verify your email address'),
            body=email_content.get('text_content', f'Please verify your email: {verification_url}'),
            from_email=getattr(settings, 'EMAIL_DEFAULT_FROM', settings.DEFAULT_FROM_EMAIL),
            to=[user.email]
        )
        if email_content.get('html_content'):
            msg.attach_alternative(email_content['html_content'], "text/html")

        # Send email with detailed error handling
        try:
            logger.info(f"Attempting to send verification email to {user.email}")
            logger.info(f"Email backend: {getattr(settings, 'EMAIL_BACKEND', 'Not configured')}")
            logger.info(f"SMTP host: {getattr(settings, 'EMAIL_HOST', 'Not configured')}")

            msg.send(fail_silently=False)
            logger.info(f"Email sent successfully to {user.email}")

        except Exception as email_error:
            logger.error(f"SMTP Error sending to {user.email}: {email_error}")
            logger.error(f"Email error type: {type(email_error).__name__}")

            # Log email configuration for debugging
            logger.error(f"Email settings - Host: {getattr(settings, 'EMAIL_HOST', 'Not set')}")
            logger.error(f"Email settings - Port: {getattr(settings, 'EMAIL_PORT', 'Not set')}")
            logger.error(f"Email settings - User: {getattr(settings, 'EMAIL_HOST_USER', 'Not set')}")
            logger.error(f"Email settings - TLS: {getattr(settings, 'EMAIL_USE_TLS', 'Not set')}")

            raise email_error

        # Update sent timestamp only after successful send
        user.profile.email_verification_sent_at = timezone.now()
        user.profile.save(update_fields=['email_verification_sent_at'])

        logger.info(f"Email verification sent successfully to user {user_id} ({user.email})")
        return f"Verification email sent to {user.email}"

    except Exception as e:
        logger.error(f"Failed to send verification email to user {user_id}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise