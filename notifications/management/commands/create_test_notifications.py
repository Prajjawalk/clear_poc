"""Management command to create test notifications for development."""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from notifications.models import InternalNotification


class Command(BaseCommand):
    help = 'Create test notifications for development and testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            default=9,
            help='User ID to create notifications for (default: 9)'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=10,
            help='Number of test notifications to create (default: 10)'
        )

    def handle(self, *args, **options):
        User = get_user_model()
        user_id = options['user_id']
        count = options['count']

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User with ID {user_id} does not exist')
            )
            return

        # Sample notification data
        test_notifications = [
            {
                'title': 'IDMC Data Update Complete',
                'message': 'New displacement data has been successfully processed from IDMC API. 234 new records added.',
                'type': 'update',
                'priority': 'normal',
                'action_url': '/pipeline/dashboard/',
                'action_text': 'View Data'
            },
            {
                'title': 'High Priority Alert: Blue Nile State',
                'message': 'Conflict escalation detected in Blue Nile State. Immediate attention required.',
                'type': 'alert',
                'priority': 'urgent',
                'action_url': '/alerts/alert_list/',
                'action_text': 'View Alert'
            },
            {
                'title': 'System Maintenance Scheduled',
                'message': 'Scheduled maintenance will occur tonight from 02:00 to 04:00 UTC. Expect brief service interruptions.',
                'type': 'system',
                'priority': 'low',
                'action_url': '',
                'action_text': ''
            },
            {
                'title': 'ACLED Data Processing Failed',
                'message': 'Unable to connect to ACLED API. Automatic retry scheduled in 30 minutes.',
                'type': 'update',
                'priority': 'high',
                'action_url': '/tasks/executions/',
                'action_text': 'View Tasks'
            },
            {
                'title': 'New User Registration',
                'message': 'New user "john.doe@nrc.no" has registered and is pending approval.',
                'type': 'system',
                'priority': 'normal',
                'action_url': '/admin/auth/user/',
                'action_text': 'Manage Users'
            },
            {
                'title': 'Weekly Report Generated',
                'message': 'Your weekly displacement report for Sudan has been generated and is ready for review.',
                'type': 'system',
                'priority': 'low',
                'action_url': '/reports/weekly/',
                'action_text': 'View Report'
            },
            {
                'title': 'Critical Alert: Khartoum',
                'message': 'Mass displacement event detected in Khartoum with estimated 15,000 affected individuals.',
                'type': 'alert',
                'priority': 'urgent',
                'action_url': '/alerts/alert_list/',
                'action_text': 'View Alert'
            },
            {
                'title': 'Data Quality Check Complete',
                'message': 'Automated data quality check completed. 3 data inconsistencies found and flagged for review.',
                'type': 'update',
                'priority': 'normal',
                'action_url': '/pipeline/dashboard/',
                'action_text': 'Review Data'
            },
            {
                'title': 'Location Matching Updated',
                'message': 'Gazetteer has been updated with 45 new location entries. Location matching accuracy improved.',
                'type': 'system',
                'priority': 'low',
                'action_url': '/location/dashboard/',
                'action_text': 'View Locations'
            },
            {
                'title': 'API Rate Limit Warning',
                'message': 'Approaching rate limit for UNHCR API. Consider reducing request frequency.',
                'type': 'system',
                'priority': 'normal',
                'action_url': '/tasks/scheduled/',
                'action_text': 'Manage Tasks'
            }
        ]

        created_count = 0

        for i in range(count):
            # Cycle through test notifications
            notification_data = test_notifications[i % len(test_notifications)]

            # Create unique titles for multiple notifications
            if i >= len(test_notifications):
                notification_data = notification_data.copy()
                notification_data['title'] += f' #{i + 1}'

            notification = InternalNotification.objects.create(
                user=user,
                **notification_data
            )

            created_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'Created notification: {notification.title}'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSuccessfully created {created_count} test notifications for user {user.username} (ID: {user_id})'
            )
        )

        # Show statistics
        total_notifications = InternalNotification.objects.filter(user=user).count()
        unread_notifications = InternalNotification.objects.filter(user=user, read=False).count()

        self.stdout.write(
            self.style.SUCCESS(
                f'User now has {total_notifications} total notifications ({unread_notifications} unread)'
            )
        )