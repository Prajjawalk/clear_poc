"""Management command to test Celery email verification task."""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from alerts.tasks import send_email_verification
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test Celery email verification task'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to send verification email to'
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run task synchronously (not through Celery)'
        )

    def handle(self, *args, **options):
        """Test Celery email verification."""

        if options['user_id']:
            user_id = options['user_id']
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User with ID {user_id} not found'))
                return
        else:
            user = User.objects.first()
            if not user:
                self.stdout.write(self.style.ERROR('No users found in database'))
                return
            user_id = user.id

        self.stdout.write(f'Testing email verification for user: {user.username} ({user.email})')

        if options['sync']:
            self.stdout.write('Running task synchronously...')
            try:
                result = send_email_verification(user_id)
                self.stdout.write(self.style.SUCCESS(f'Task completed: {result}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Task failed: {e}'))
        else:
            self.stdout.write('Queuing task through Celery...')
            try:
                task = send_email_verification.delay(user_id)
                self.stdout.write(f'Task queued with ID: {task.id}')
                self.stdout.write('Check Celery logs for execution details.')

                # Try to get the result (this will block until task completes)
                self.stdout.write('Waiting for task result...')
                try:
                    result = task.get(timeout=30)
                    self.stdout.write(self.style.SUCCESS(f'Task completed: {result}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Task failed or timeout: {e}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to queue task: {e}'))