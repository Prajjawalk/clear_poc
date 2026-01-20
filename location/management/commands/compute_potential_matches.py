"""Management command to compute potential matches for unmatched locations."""

from django.core.management.base import BaseCommand

from location.models import UnmatchedLocation
from location.tasks import compute_potential_matches, recompute_all_potential_matches


class Command(BaseCommand):
    help = "Compute potential matches for unmatched locations"

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Recompute matches for all pending unmatched locations',
        )
        parser.add_argument(
            '--id',
            type=int,
            help='Compute matches for specific unmatched location ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recomputation even if already computed',
        )

    def handle(self, *args, **options):
        if options['all']:
            self.stdout.write('Starting batch computation of potential matches...')
            result = recompute_all_potential_matches.delay()
            self.stdout.write(
                self.style.SUCCESS(f'Queued batch computation task: {result.id}')
            )

        elif options['id']:
            unmatched_id = options['id']
            try:
                unmatched = UnmatchedLocation.objects.get(id=unmatched_id)

                if not options['force'] and unmatched.potential_matches_computed_at:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Matches already computed for "{unmatched.name}". Use --force to recompute.'
                        )
                    )
                    return

                self.stdout.write(f'Computing matches for: {unmatched.name}')
                result = compute_potential_matches.delay(unmatched_id)
                self.stdout.write(
                    self.style.SUCCESS(f'Queued computation task: {result.id}')
                )

            except UnmatchedLocation.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'UnmatchedLocation with ID {unmatched_id} not found')
                )
        else:
            # Show statistics and prompt for action
            total_unmatched = UnmatchedLocation.objects.filter(status='pending').count()
            computed = UnmatchedLocation.objects.filter(
                status='pending',
                potential_matches_computed_at__isnull=False
            ).count()
            pending = total_unmatched - computed

            self.stdout.write('Unmatched location statistics:')
            self.stdout.write(f'  Total pending: {total_unmatched}')
            self.stdout.write(f'  Matches computed: {computed}')
            self.stdout.write(f'  Computation pending: {pending}')

            if pending > 0:
                self.stdout.write(
                    f'\nTo compute matches for {pending} locations, run:'
                )
                self.stdout.write('  python manage.py compute_potential_matches --all')

            # Show recent unmatched locations as examples
            recent = UnmatchedLocation.objects.filter(
                status='pending'
            ).order_by('-last_seen')[:5]

            if recent:
                self.stdout.write('\nRecent unmatched locations:')
                for unmatched in recent:
                    status = '✓' if unmatched.potential_matches_computed_at else '⏳'
                    self.stdout.write(
                        f'  {status} {unmatched.name} ({unmatched.source}) - {unmatched.occurrence_count}x'
                    )
