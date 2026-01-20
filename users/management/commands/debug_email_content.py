"""Debug email verification content."""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from alerts.services.notifications import NotificationService


class Command(BaseCommand):
    help = 'Debug email verification content'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            default=9,
            help='User ID to test with'
        )

    def handle(self, *args, **options):
        """Debug email content."""
        user_id = options['user_id']

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User with ID {user_id} not found'))
            return

        self.stdout.write(f'Testing email content for user: {user.username} ({user.email})')

        # Check if user has a profile and token
        if not hasattr(user, 'profile'):
            self.stdout.write(self.style.ERROR('User has no profile'))
            return

        # Generate token if not exists
        if not user.profile.email_verification_token:
            self.stdout.write('Generating verification token...')
            user.profile.generate_verification_token()

        self.stdout.write(f'Verification token: {user.profile.email_verification_token}')

        # Build verification URL
        verification_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/users/verify-email/{user.profile.email_verification_token}/"
        self.stdout.write(f'Verification URL: {verification_url}')

        # Get email content from database template
        service = NotificationService()
        try:
            email_content = service.render_email_from_template(
                template_name='email_verification',
                user=user,
                verification_url=verification_url
            )

            self.stdout.write('\n=== EMAIL CONTENT ===')
            self.stdout.write(f'Subject: {email_content.get("subject", "NO SUBJECT")}')
            self.stdout.write(f'\n--- TEXT CONTENT ---')
            text_content = email_content.get('text_content', 'NO TEXT CONTENT')
            self.stdout.write(text_content)

            self.stdout.write(f'\n--- HTML CONTENT ---')
            html_content = email_content.get('html_content', 'NO HTML CONTENT')
            self.stdout.write(html_content)

            # Override with verification URL in context
            text_with_url = text_content.replace('{{verification_url}}', verification_url)
            html_with_url = html_content.replace('{{verification_url}}', verification_url)

            self.stdout.write(f'\n=== FINAL EMAIL CONTENT (with URL) ===')
            self.stdout.write(f'Subject: {email_content.get("subject", "Verify your email address")}')
            self.stdout.write(f'\n--- FINAL TEXT ---')
            self.stdout.write(text_with_url)
            self.stdout.write(f'\n--- FINAL HTML ---')
            self.stdout.write(html_with_url)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to render email template: {e}'))
            import traceback
            self.stdout.write(traceback.format_exc())

        # Check if email template exists in database
        from alerts.models import EmailTemplate
        try:
            template = EmailTemplate.objects.get(name='email_verification')
            self.stdout.write(f'\n=== DATABASE TEMPLATE FOUND ===')
            self.stdout.write(f'Template active: {template.active}')
            self.stdout.write(f'Subject template: {template.subject}')
            self.stdout.write(f'HTML header: {template.html_header[:100]}...')
        except EmailTemplate.DoesNotExist:
            self.stdout.write(self.style.WARNING('\n=== NO DATABASE TEMPLATE FOUND ==='))
            self.stdout.write('Email template "email_verification" not found in database!')
            self.stdout.write('This might be why emails are empty or not working.')
            self.stdout.write('Run: python manage.py create_email_templates')