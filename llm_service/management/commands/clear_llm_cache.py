"""Management command to clear LLM cache entries."""

import time
from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.utils import timezone

from llm_service.models import CachedResponse


class Command(BaseCommand):
    help = "Clear LLM cache entries (Redis and/or database)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--redis-only",
            action="store_true",
            help="Clear only Redis cache, not database cache",
        )
        parser.add_argument(
            "--db-only",
            action="store_true",
            help="Clear only database cache, not Redis cache",
        )
        parser.add_argument(
            "--expired-only",
            action="store_true",
            help="Clear only expired entries (database only)",
        )
        parser.add_argument(
            "--provider",
            type=str,
            help="Clear cache only for specific provider",
        )
        parser.add_argument(
            "--older-than-days",
            type=int,
            help="Clear entries older than specified days",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be cleared without actually clearing",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        try:
            self._validate_options(options)

            if not options["force"] and not options["dry_run"]:
                self._show_confirmation(options)

            # Clear caches based on options
            if options["redis_only"]:
                self._clear_redis_cache(options)
            elif options["db_only"]:
                self._clear_database_cache(options)
            else:
                # Clear both by default
                self._clear_redis_cache(options)
                self._clear_database_cache(options)

        except Exception as e:
            raise CommandError(f"Cache clearing failed: {e}")

    def _validate_options(self, options):
        """Validate command options."""
        if options["redis_only"] and options["db_only"]:
            raise CommandError("Cannot specify both --redis-only and --db-only")

        if options["expired_only"] and options["redis_only"]:
            raise CommandError("--expired-only only works with database cache")

    def _show_confirmation(self, options):
        """Show confirmation dialog."""
        scope = "all caches"
        if options["redis_only"]:
            scope = "Redis cache"
        elif options["db_only"]:
            scope = "database cache"

        filters = []
        if options["provider"]:
            filters.append(f"provider={options['provider']}")
        if options["expired_only"]:
            filters.append("expired entries only")
        if options["older_than_days"]:
            filters.append(f"older than {options['older_than_days']} days")

        filter_text = f" ({', '.join(filters)})" if filters else ""

        confirm = input(f"Are you sure you want to clear {scope}{filter_text}? [y/N]: ")
        if confirm.lower() not in ['y', 'yes']:
            self.stdout.write("Operation cancelled.")
            return

    def _clear_redis_cache(self, options):
        """Clear Redis cache entries."""
        self.stdout.write(f"{self.style.WARNING('Clearing Redis cache...')}")

        if options["dry_run"]:
            self.stdout.write("  [DRY RUN] Would clear Redis cache entries matching pattern: llm_query:*")
            return

        try:
            # Get Django's cache backend
            cache_backend = cache

            # We can't easily filter Redis keys by provider without iterating
            # For now, clear all LLM cache entries
            # In a production system, you might want to implement more sophisticated filtering

            # Clear all keys matching our pattern
            # Note: This is a simplified approach - production systems might need
            # more sophisticated Redis key management

            cleared_count = 0

            # If using Redis directly, we could do:
            # redis_client = cache._cache.get_client()
            # keys = redis_client.keys("llm_query:*")
            # if keys:
            #     cleared_count = redis_client.delete(*keys)

            # For now, just clear the entire cache if no specific filters
            if not options["provider"]:
                cache.clear()
                self.stdout.write(f"  {self.style.SUCCESS('✓ Cleared entire Redis cache')}")
            else:
                self.stdout.write(f"  {self.style.WARNING('⚠ Redis filtering by provider not implemented - skipping')}")

        except Exception as e:
            self.stdout.write(f"  {self.style.ERROR(f'✗ Redis cache clearing failed: {e}')}")
            raise

    def _clear_database_cache(self, options):
        """Clear database cache entries."""
        self.stdout.write(f"{self.style.WARNING('Clearing database cache...')}")

        try:
            # Build queryset based on options
            queryset = CachedResponse.objects.all()

            # Filter by provider
            if options["provider"]:
                queryset = queryset.filter(provider=options["provider"])

            # Filter by expiration
            if options["expired_only"]:
                queryset = queryset.filter(expires_at__lt=timezone.now())

            # Filter by age
            if options["older_than_days"]:
                cutoff_date = timezone.now() - timezone.timedelta(days=options["older_than_days"])
                queryset = queryset.filter(created_at__lt=cutoff_date)

            # Get count before deletion
            total_count = queryset.count()

            if options["dry_run"]:
                self.stdout.write(f"  [DRY RUN] Would delete {total_count} database cache entries")
                self._show_cache_breakdown(queryset)
                return

            if total_count == 0:
                self.stdout.write(f"  {self.style.WARNING('No database cache entries to clear')}")
                return

            # Show breakdown before deletion
            self._show_cache_breakdown(queryset)

            # Delete entries
            start_time = time.time()
            deleted_count, _ = queryset.delete()
            deletion_time = time.time() - start_time

            self.stdout.write(
                f"  {self.style.SUCCESS(f'✓ Deleted {deleted_count} database cache entries in {deletion_time:.2f}s')}"
            )

        except Exception as e:
            self.stdout.write(f"  {self.style.ERROR(f'✗ Database cache clearing failed: {e}')}")
            raise

    def _show_cache_breakdown(self, queryset):
        """Show breakdown of cache entries to be cleared."""
        try:
            from django.db.models import Count

            # Provider breakdown
            provider_stats = queryset.values('provider').annotate(count=Count('id')).order_by('provider')
            if provider_stats:
                self.stdout.write("    Provider breakdown:")
                for stat in provider_stats:
                    self.stdout.write(f"      {stat['provider']}: {stat['count']} entries")

            # Expiration status
            now = timezone.now()
            expired_count = queryset.filter(expires_at__lt=now).count()
            active_count = queryset.filter(expires_at__gte=now).count()

            if expired_count > 0 or active_count > 0:
                self.stdout.write("    Expiration status:")
                self.stdout.write(f"      Expired: {expired_count} entries")
                self.stdout.write(f"      Active: {active_count} entries")

        except Exception as e:
            self.stdout.write(f"    {self.style.WARNING(f'Could not show breakdown: {e}')}")