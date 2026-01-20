"""Management command to test unmatched location notification functionality."""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from data_pipeline.models import Source
from data_pipeline.tasks import get_source_class
from location.models import UnmatchedLocation


class Command(BaseCommand):
    help = 'Test the unmatched location notification functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-name',
            type=str,
            default='IOM',
            help='Name of the source to test with (default: IOM)'
        )
        parser.add_argument(
            '--create-test-data',
            action='store_true',
            help='Create some test unmatched location records'
        )

    def handle(self, *args, **options):
        source_name = options['source_name']

        try:
            # Get the source
            source = Source.objects.get(name=source_name)
            self.stdout.write(f"Testing with source: {source.name}")

            # Create test unmatched locations if requested
            if options['create_test_data']:
                self.create_test_unmatched_locations(source)

            # Get source instance
            source_instance = get_source_class(source)

            # Test the notification functionality
            self.stdout.write("Testing unmatched location notification...")
            source_instance.notify_unmatched_locations_summary()

            self.stdout.write(
                self.style.SUCCESS(
                    'Successfully tested unmatched location notification functionality. '
                    'Check the admin notifications to see if administrators received the notification.'
                )
            )

        except Source.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Source "{source_name}" not found. Available sources:')
            )
            for source in Source.objects.all():
                self.stdout.write(f'  - {source.name}')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error testing notification: {str(e)}')
            )

    def create_test_unmatched_locations(self, source):
        """Create some test unmatched location records."""
        self.stdout.write("Creating test unmatched location records...")

        # Create recent unmatched locations
        recent_time = timezone.now() - timedelta(hours=1)

        test_locations = [
            ("Al-Fashir District", "Expected admin level: 2 | Additional info: Test location 1"),
            ("Nyala Township", "Expected admin level: 2 | Additional info: Test location 2"),
            ("Kassala Province", "Expected admin level: 1 | Additional info: Test location 3"),
            ("Unknown Settlement", "Expected admin level: 2 | Additional info: Test location 4"),
            ("Darfur Region West", "Expected admin level: 1 | Additional info: Test location 5"),
        ]

        for location_name, context in test_locations:
            unmatched, created = UnmatchedLocation.objects.get_or_create(
                name=location_name,
                source=source.name,
                defaults={
                    'context': context,
                    'admin_level': '2',
                    'occurrence_count': 1,
                    'last_seen': recent_time,
                }
            )

            if not created:
                # Update existing record to make it recent
                unmatched.last_seen = recent_time
                unmatched.occurrence_count += 1
                unmatched.save()

            self.stdout.write(f"  - {location_name} ({'created' if created else 'updated'})")

        self.stdout.write(f"Created/updated {len(test_locations)} test unmatched locations")