"""Management command to test email sending with detailed logging."""

from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test email sending with detailed error reporting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            type=str,
            default='test@example.com',
            help='Email address to send test email to'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose logging'
        )

    def handle(self, *args, **options):
        """Test email sending."""
        if options['verbose']:
            logging.basicConfig(level=logging.DEBUG)

        to_email = options['to']

        self.stdout.write(f"Testing email sending to: {to_email}")
        self.stdout.write(f"Email backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"SMTP host: {getattr(settings, 'EMAIL_HOST', 'Not set')}")
        self.stdout.write(f"SMTP port: {getattr(settings, 'EMAIL_PORT', 'Not set')}")
        self.stdout.write(f"SMTP user: {getattr(settings, 'EMAIL_HOST_USER', 'Not set')}")
        self.stdout.write(f"Use TLS: {getattr(settings, 'EMAIL_USE_TLS', 'Not set')}")
        self.stdout.write(f"Default from: {getattr(settings, 'EMAIL_DEFAULT_FROM', getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set'))}")

        try:
            # Test simple email
            msg = EmailMultiAlternatives(
                subject='Test Email from NRC EWAS Sudan',
                body='This is a test email to verify SMTP configuration.',
                from_email=getattr(settings, 'EMAIL_DEFAULT_FROM', getattr(settings, 'DEFAULT_FROM_EMAIL', 'test@example.com')),
                to=[to_email]
            )

            # Add HTML version
            html_content = """
            <html>
            <body>
                <h2>Test Email from NRC EWAS Sudan</h2>
                <p>This is a test email to verify SMTP configuration.</p>
                <p>If you receive this email, the SMTP settings are working correctly.</p>
            </body>
            </html>
            """
            msg.attach_alternative(html_content, "text/html")

            self.stdout.write("Attempting to send email...")
            msg.send(fail_silently=False)

            self.stdout.write(
                self.style.SUCCESS(f'Email sent successfully to {to_email}')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to send email: {e}')
            )
            self.stdout.write(f'Error type: {type(e).__name__}')
            self.stdout.write(f'Error details: {str(e)}')

            # Additional debugging
            import traceback
            self.stdout.write('Full traceback:')
            self.stdout.write(traceback.format_exc())