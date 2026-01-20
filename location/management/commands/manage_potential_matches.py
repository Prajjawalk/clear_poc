"""Management command for managing potential location matches."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Manage potential location matches efficiently."""

    help = "Manage potential location matches"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-old",
            action="store_true",
            help="Clear old computed matches older than 30 days",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show statistics about potential matches",
        )
        parser.add_argument(
            "--recompute-failed",
            action="store_true",
            help="Recompute matches that failed",
        )

    def handle(self, *args, **options):
        """Handle the management command."""
        from location.models import UnmatchedLocation
        from datetime import datetime, timedelta, UTC

        if options["clear_old"]:
            cutoff = datetime.now(UTC) - timedelta(days=30)
            old_count = UnmatchedLocation.objects.filter(
                potential_matches_computed_at__lt=cutoff,
                status="matched",  # Only clear for already matched locations
            ).update(potential_matches=None, potential_matches_computed_at=None)
            self.stdout.write(self.style.SUCCESS(f"Cleared {old_count} old computed matches"))

        if options["recompute_failed"]:
            # Find locations that should have matches but don't
            failed_locations = UnmatchedLocation.objects.filter(status="pending", potential_matches_computed_at__isnull=True)
            count = failed_locations.count()

            if count > 0:
                from location.tasks import recompute_all_potential_matches

                task = recompute_all_potential_matches.delay()
                self.stdout.write(self.style.SUCCESS(f"Queued recomputation for {count} locations (task: {task.id})"))
            else:
                self.stdout.write("No failed computations found")

        if options["status"]:
            total_unmatched = UnmatchedLocation.objects.count()
            computed = UnmatchedLocation.objects.exclude(potential_matches_computed_at__isnull=True).count()
            pending = UnmatchedLocation.objects.filter(status="pending", potential_matches_computed_at__isnull=True).count()
            matched = UnmatchedLocation.objects.filter(status="matched").count()

            self.stdout.write(f"Total unmatched locations: {total_unmatched}")
            self.stdout.write(f"With computed matches: {computed}")
            self.stdout.write(f"Pending computation: {pending}")
            self.stdout.write(f"Successfully matched: {matched}")

            if pending > 0:
                self.stdout.write(self.style.WARNING(f"Note: {pending} locations need computation"))

        # Default action if no options specified
        if not any(options.values()):
            self.handle(*args, **{"status": True})
