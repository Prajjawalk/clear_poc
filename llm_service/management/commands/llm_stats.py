"""Management command to show LLM service statistics and health."""

import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q

from llm_service.models import QueryLog, CachedResponse, ProviderConfig
from llm_service.service import LLMService


class Command(BaseCommand):
    help = "Show LLM service statistics and health information"

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            type=str,
            choices=["hour", "day", "week", "month", "all"],
            default="day",
            help="Time period for statistics (default: day)",
        )
        parser.add_argument(
            "--provider",
            type=str,
            help="Show stats for specific provider only",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output in JSON format",
        )
        parser.add_argument(
            "--detailed",
            action="store_true",
            help="Show detailed statistics",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        try:
            service = LLMService()

            if options["json"]:
                stats = self._get_stats_json(service, options)
                self.stdout.write(json.dumps(stats, indent=2, default=str))
            else:
                self._show_stats_verbose(service, options)

        except Exception as e:
            if options["json"]:
                self.stdout.write(json.dumps({"error": str(e)}))
            else:
                self.stdout.write(f"{self.style.ERROR(f'Error: {e}')}")

    def _get_stats_json(self, service, options):
        """Get statistics in JSON format."""
        stats = {
            "timestamp": timezone.now(),
            "period": options["period"],
            "service_status": self._get_service_status(service),
            "query_stats": self._get_query_stats(options),
            "cache_stats": self._get_cache_stats(),
            "provider_stats": self._get_provider_stats(service, options),
        }

        if options["detailed"]:
            stats["detailed"] = self._get_detailed_stats(options)

        return stats

    def _show_stats_verbose(self, service, options):
        """Show statistics with verbose output."""
        period = options["period"]
        provider_filter = options.get("provider")

        self.stdout.write(f"{self.style.HTTP_INFO('='*60)}")
        self.stdout.write(f"{self.style.HTTP_INFO('LLM Service Statistics')}")
        if provider_filter:
            self.stdout.write(f"{self.style.HTTP_INFO(f'Provider: {provider_filter}')}")
        self.stdout.write(f"{self.style.HTTP_INFO(f'Period: {period}')}")
        self.stdout.write(f"{self.style.HTTP_INFO('='*60)}")

        # Service status
        self._show_service_status(service)

        # Query statistics
        self._show_query_stats(options)

        # Cache statistics
        self._show_cache_stats()

        # Provider statistics
        self._show_provider_stats(service, options)

        if options["detailed"]:
            self._show_detailed_stats(options)

    def _get_time_filter(self, period):
        """Get time filter for the specified period."""
        now = timezone.now()

        if period == "hour":
            since = now - timezone.timedelta(hours=1)
        elif period == "day":
            since = now - timezone.timedelta(days=1)
        elif period == "week":
            since = now - timezone.timedelta(weeks=1)
        elif period == "month":
            since = now - timezone.timedelta(days=30)
        else:  # "all"
            since = None

        return since

    def _get_service_status(self, service):
        """Get service status information."""
        try:
            provider_status = service.get_provider_status()
            total_providers = len(provider_status.get("providers", []))
            active_providers = sum(1 for p in provider_status.get("providers", []) if p.get("active", False))

            return {
                "providers_total": total_providers,
                "providers_active": active_providers,
                "service_healthy": active_providers > 0
            }
        except Exception as e:
            return {"error": str(e)}

    def _show_service_status(self, service):
        """Show service status with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Service Status:')}")

        try:
            status = self._get_service_status(service)

            if "error" in status:
                self.stdout.write(f"  {self.style.ERROR(f'Status check failed: {status['error']}')}")
                return

            total = status["providers_total"]
            active = status["providers_active"]
            healthy = status["service_healthy"]

            self.stdout.write(f"  Total providers: {total}")
            self.stdout.write(f"  Active providers: {active}")

            if healthy:
                self.stdout.write(f"  {self.style.SUCCESS('✓ Service is healthy')}")
            else:
                self.stdout.write(f"  {self.style.ERROR('✗ Service is unhealthy (no active providers)')}")

        except Exception as e:
            self.stdout.write(f"  {self.style.ERROR(f'Status check failed: {e}')}")

    def _get_query_stats(self, options):
        """Get query statistics."""
        since = self._get_time_filter(options["period"])

        queryset = QueryLog.objects.all()
        if since:
            queryset = queryset.filter(created_at__gte=since)
        if options.get("provider"):
            queryset = queryset.filter(provider=options["provider"])

        stats = queryset.aggregate(
            total_queries=Count("id"),
            successful_queries=Count("id", filter=Q(success=True)),
            failed_queries=Count("id", filter=Q(success=False)),
            total_tokens=Sum("total_tokens"),
            avg_response_time=Avg("response_time_ms"),
            cache_hits=Count("id", filter=Q(metadata__cache_hit=True))
        )

        # Calculate success rate
        total = stats["total_queries"] or 0
        successful = stats["successful_queries"] or 0
        stats["success_rate"] = (successful / total * 100) if total > 0 else 0

        # Calculate cache hit rate
        cache_hits = stats["cache_hits"] or 0
        stats["cache_hit_rate"] = (cache_hits / total * 100) if total > 0 else 0

        return stats

    def _show_query_stats(self, options):
        """Show query statistics with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Query Statistics:')}")

        stats = self._get_query_stats(options)

        self.stdout.write(f"  Total queries: {stats['total_queries']:,}")
        self.stdout.write(f"  Successful: {stats['successful_queries']:,}")
        self.stdout.write(f"  Failed: {stats['failed_queries']:,}")
        self.stdout.write(f"  Success rate: {stats['success_rate']:.1f}%")

        if stats["total_tokens"]:
            self.stdout.write(f"  Total tokens: {stats['total_tokens']:,}")

        if stats["avg_response_time"]:
            self.stdout.write(f"  Avg response time: {stats['avg_response_time']:.0f}ms")

        self.stdout.write(f"  Cache hits: {stats['cache_hits']:,}")
        self.stdout.write(f"  Cache hit rate: {stats['cache_hit_rate']:.1f}%")

    def _get_cache_stats(self):
        """Get cache statistics."""
        now = timezone.now()

        total_entries = CachedResponse.objects.count()
        expired_entries = CachedResponse.objects.filter(expires_at__lt=now).count()
        active_entries = total_entries - expired_entries

        if total_entries > 0:
            hit_stats = CachedResponse.objects.aggregate(
                total_hits=Sum("hit_count"),
                avg_hits_per_entry=Avg("hit_count")
            )
        else:
            hit_stats = {"total_hits": 0, "avg_hits_per_entry": 0}

        return {
            "total_entries": total_entries,
            "active_entries": active_entries,
            "expired_entries": expired_entries,
            "total_hits": hit_stats["total_hits"] or 0,
            "avg_hits_per_entry": hit_stats["avg_hits_per_entry"] or 0
        }

    def _show_cache_stats(self):
        """Show cache statistics with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Cache Statistics:')}")

        stats = self._get_cache_stats()

        self.stdout.write(f"  Total cache entries: {stats['total_entries']:,}")
        self.stdout.write(f"  Active entries: {stats['active_entries']:,}")
        self.stdout.write(f"  Expired entries: {stats['expired_entries']:,}")
        self.stdout.write(f"  Total cache hits: {stats['total_hits']:,}")

        if stats["avg_hits_per_entry"]:
            self.stdout.write(f"  Avg hits per entry: {stats['avg_hits_per_entry']:.1f}")

    def _get_provider_stats(self, service, options):
        """Get provider-specific statistics."""
        since = self._get_time_filter(options["period"])

        queryset = QueryLog.objects.all()
        if since:
            queryset = queryset.filter(created_at__gte=since)

        provider_stats = queryset.values("provider").annotate(
            queries=Count("id"),
            successful=Count("id", filter=Q(success=True)),
            failed=Count("id", filter=Q(success=False)),
            avg_response_time=Avg("response_time_ms"),
            total_tokens=Sum("total_tokens")
        ).order_by("-queries")

        # Add success rates
        for stat in provider_stats:
            total = stat["queries"]
            successful = stat["successful"]
            stat["success_rate"] = (successful / total * 100) if total > 0 else 0

        return list(provider_stats)

    def _show_provider_stats(self, service, options):
        """Show provider statistics with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Provider Statistics:')}")

        stats = self._get_provider_stats(service, options)

        if not stats:
            self.stdout.write("  No provider statistics available")
            return

        for stat in stats:
            provider = stat["provider"]
            self.stdout.write(f"\n  {self.style.HTTP_INFO(f'Provider: {provider}')}")
            self.stdout.write(f"    Queries: {stat['queries']:,}")
            self.stdout.write(f"    Success rate: {stat['success_rate']:.1f}%")

            if stat["avg_response_time"]:
                self.stdout.write(f"    Avg response time: {stat['avg_response_time']:.0f}ms")

            if stat["total_tokens"]:
                self.stdout.write(f"    Total tokens: {stat['total_tokens']:,}")

    def _get_detailed_stats(self, options):
        """Get detailed statistics."""
        since = self._get_time_filter(options["period"])

        queryset = QueryLog.objects.all()
        if since:
            queryset = queryset.filter(created_at__gte=since)
        if options.get("provider"):
            queryset = queryset.filter(provider=options["provider"])

        # Model usage
        model_stats = queryset.values("model").annotate(
            queries=Count("id"),
            avg_tokens=Avg("total_tokens")
        ).order_by("-queries")

        # Hourly distribution
        from django.db.models import DateTimeField
        from django.db.models.functions import TruncHour

        hourly_stats = queryset.annotate(
            hour=TruncHour("created_at")
        ).values("hour").annotate(
            queries=Count("id")
        ).order_by("hour")

        return {
            "model_usage": list(model_stats),
            "hourly_distribution": list(hourly_stats)
        }

    def _show_detailed_stats(self, options):
        """Show detailed statistics with verbose output."""
        self.stdout.write(f"\n{self.style.WARNING('Detailed Statistics:')}")

        stats = self._get_detailed_stats(options)

        # Model usage
        model_stats = stats["model_usage"]
        if model_stats:
            self.stdout.write(f"\n  {self.style.HTTP_INFO('Model Usage:')}")
            for stat in model_stats[:5]:  # Top 5 models
                model = stat["model"]
                queries = stat["queries"]
                avg_tokens = stat["avg_tokens"] or 0
                self.stdout.write(f"    {model}: {queries:,} queries (avg {avg_tokens:.0f} tokens)")

        # Recent activity
        hourly_stats = stats["hourly_distribution"]
        if hourly_stats:
            self.stdout.write(f"\n  {self.style.HTTP_INFO('Recent Hourly Activity:')}")
            for stat in hourly_stats[-6:]:  # Last 6 hours
                hour = stat["hour"].strftime("%Y-%m-%d %H:00")
                queries = stat["queries"]
                self.stdout.write(f"    {hour}: {queries:,} queries")