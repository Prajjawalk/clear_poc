"""Management command to test email templates."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from alerts.models import Alert, EmailTemplate
from alerts.services.notifications import NotificationService


class Command(BaseCommand):
    """Test email template rendering with sample data."""

    help = "Test email template rendering and optionally send test email"

    def add_arguments(self, parser):
        parser.add_argument(
            'template',
            type=str,
            help='Template name to test'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID for template context'
        )
        parser.add_argument(
            '--alert-id',
            type=int,
            help='Alert ID for template context'
        )
        parser.add_argument(
            '--send-email',
            action='store_true',
            help='Actually send the test email'
        )
        parser.add_argument(
            '--output',
            choices=['text', 'html', 'both'],
            default='both',
            help='Output format to display'
        )

    def handle(self, *args, **options):
        template_name = options['template']
        user_id = options.get('user_id')
        alert_id = options.get('alert_id')
        send_email = options['send_email']
        output_format = options['output']

        # Get template
        try:
            template = EmailTemplate.objects.get(name=template_name, active=True)
        except EmailTemplate.DoesNotExist:
            raise CommandError(f"Template '{template_name}' not found or inactive")

        # Get user for context
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                raise CommandError(f"User with ID {user_id} not found")
        else:
            # Create a test user context
            user = User(
                id=1,
                username='testuser',
                email='test@example.com',
                first_name='Test'
            )

        # Get alert for context
        alert = None
        if alert_id:
            try:
                alert = Alert.objects.get(pk=alert_id)
            except Alert.DoesNotExist:
                raise CommandError(f"Alert with ID {alert_id} not found")
        elif template_name == 'individual_alert':
            # For alert templates, we need an alert
            alerts_qs = Alert.objects.all()[:1]
            if alerts_qs.exists():
                alert = alerts_qs.first()
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "No alerts found in database. Using mock alert data."
                    )
                )

        # Render template
        service = NotificationService()
        try:
            email_content = service.render_email_from_template(
                template_name=template_name,
                user=user,
                alert=alert
            )
        except Exception as e:
            raise CommandError(f"Failed to render template: {e}")

        # Display results
        self.stdout.write(f"\n{'-' * 50}")
        self.stdout.write(f"Template: {template_name}")
        self.stdout.write(f"User: {user.username} ({user.email})")
        if alert:
            self.stdout.write(f"Alert: {alert.title}")
        self.stdout.write(f"{'-' * 50}")

        self.stdout.write(f"\nSUBJECT:")
        self.stdout.write(email_content['subject'])

        if output_format in ['text', 'both']:
            self.stdout.write(f"\nTEXT CONTENT:")
            self.stdout.write(f"{'-' * 30}")
            self.stdout.write(email_content['text_content'])

        if output_format in ['html', 'both']:
            self.stdout.write(f"\nHTML CONTENT:")
            self.stdout.write(f"{'-' * 30}")
            self.stdout.write(email_content['html_content'])

        # Send test email if requested
        if send_email:
            if not user_id:
                raise CommandError("Must specify --user-id to send actual email")

            try:
                from django.core.mail import EmailMultiAlternatives
                from django.conf import settings

                msg = EmailMultiAlternatives(
                    subject=f"[TEST] {email_content['subject']}",
                    body=email_content['text_content'],
                    from_email=getattr(settings, 'EMAIL_DEFAULT_FROM', settings.DEFAULT_FROM_EMAIL),
                    to=[user.email]
                )
                msg.attach_alternative(email_content['html_content'], "text/html")
                msg.send(fail_silently=False)

                self.stdout.write(
                    self.style.SUCCESS(f"\nTest email sent to {user.email}")
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"\nFailed to send test email: {e}")
                )

        self.stdout.write(f"\n{'-' * 50}")
        self.stdout.write("Template test completed")
        self.stdout.write(f"{'-' * 50}\n")