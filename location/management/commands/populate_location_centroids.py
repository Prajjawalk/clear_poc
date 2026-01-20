"""Management command to populate location centroids and point types."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from location.models import Location


class Command(BaseCommand):
    """Populate location centroids for locations with boundaries but no points."""

    help = "Populate location centroids and set point types for existing location data"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recalculation of centroids even if points already exist',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        """Execute the command."""
        force = options['force']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Get statistics before operation
        total_locations = Location.objects.count()
        with_boundaries = Location.objects.filter(boundary__isnull=False).count()
        with_points = Location.objects.filter(point__isnull=False).count()
        without_points = Location.objects.filter(point__isnull=True).count()

        if force:
            targets_for_centroid = Location.objects.filter(boundary__isnull=False)
            targets_for_gps = Location.objects.filter(point__isnull=False, boundary__isnull=True)
        else:
            targets_for_centroid = Location.objects.filter(boundary__isnull=False, point__isnull=True)
            targets_for_gps = Location.objects.filter(point__isnull=False, point_type__isnull=True)

        centroid_count = targets_for_centroid.count()
        gps_count = targets_for_gps.count()

        self.stdout.write(f"Current location statistics:")
        self.stdout.write(f"  Total locations: {total_locations}")
        self.stdout.write(f"  Locations with boundaries: {with_boundaries}")
        self.stdout.write(f"  Locations with points: {with_points}")
        self.stdout.write(f"  Locations without points: {without_points}")
        self.stdout.write("")

        if dry_run:
            self.stdout.write(f"Would update {centroid_count} locations with centroid points")
            self.stdout.write(f"Would update {gps_count} locations with GPS point_type")
            return

        if centroid_count == 0 and gps_count == 0:
            self.stdout.write(self.style.SUCCESS("No locations need updating"))
            return

        try:
            with transaction.atomic():
                # Update locations with boundary centroids
                if centroid_count > 0:
                    self.stdout.write(f"Calculating centroids for {centroid_count} locations...")

                    if force:
                        sql = '''
                        UPDATE location_location
                        SET point = ST_Centroid(boundary),
                            point_type = 'centroid'
                        WHERE boundary IS NOT NULL;
                        '''
                    else:
                        sql = '''
                        UPDATE location_location
                        SET point = ST_Centroid(boundary),
                            point_type = 'centroid'
                        WHERE boundary IS NOT NULL
                        AND point IS NULL;
                        '''

                    with connection.cursor() as cursor:
                        cursor.execute(sql)
                        rows_updated = cursor.rowcount

                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Updated {rows_updated} locations with centroid points")
                    )

                # Update existing points as GPS coordinates
                if gps_count > 0:
                    self.stdout.write(f"Setting point_type for {gps_count} existing GPS coordinates...")

                    if force:
                        updated = Location.objects.filter(
                            point__isnull=False,
                            boundary__isnull=True
                        ).update(point_type='gps')
                    else:
                        updated = Location.objects.filter(
                            point__isnull=False,
                            point_type__isnull=True
                        ).update(point_type='gps')

                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Updated {updated} locations with GPS point_type")
                    )

                # Final statistics
                final_total_with_points = Location.objects.filter(point__isnull=False).count()
                final_centroid_count = Location.objects.filter(point_type='centroid').count()
                final_gps_count = Location.objects.filter(point_type='gps').count()

                self.stdout.write("")
                self.stdout.write(self.style.SUCCESS("Final statistics:"))
                self.stdout.write(f"  Total locations with points: {final_total_with_points}")
                self.stdout.write(f"  Centroid points: {final_centroid_count}")
                self.stdout.write(f"  GPS points: {final_gps_count}")

        except Exception as e:
            raise CommandError(f"Failed to populate centroids: {e}")