"""Management command to list and monitor detectors."""

from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from alert_framework.models import Detector


class Command(BaseCommand):
    """List and monitor configured detectors."""

    help = "List and monitor configured detectors"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Show only active detectors",
        )
        parser.add_argument(
            "--stats",
            action="store_true",
            help="Show detection statistics for each detector",
        )
        parser.add_argument(
            "--recent",
            type=int,
            help="Show detections from the last N days (default: 7)",
            default=7,
        )

    def handle(self, *args, **options):
        """Execute the command."""
        queryset = Detector.objects.all()

        if options["active_only"]:
            queryset = queryset.filter(active=True)

        detectors = queryset.order_by("name")

        if not detectors:
            self.stdout.write(self.style.WARNING("No detectors found."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {detectors.count()} detector{'s' if detectors.count() != 1 else ''}:"))

        for detector in detectors:
            self.display_detector(detector, options)

    def display_detector(self, detector, options):
        """Display information about a single detector."""
        self.stdout.write(f"\n{self.style.SUCCESS('■')} {detector.name}")
        self.stdout.write(f"  ID: {detector.id}")
        self.stdout.write(f"  Class: {detector.class_name}")

        status_style = self.style.SUCCESS if detector.active else self.style.ERROR
        status_text = "Active" if detector.active else "Inactive"
        self.stdout.write(f"  Status: {status_style(status_text)}")

        if detector.description:
            # Wrap long descriptions
            desc = detector.description
            if len(desc) > 80:
                desc = desc[:77] + "..."
            self.stdout.write(f"  Description: {desc}")

        if detector.schedule:
            self.stdout.write(f"  Schedule: {detector.schedule}")

        if detector.last_run:
            time_since = timezone.now() - detector.last_run
            if time_since.days > 0:
                last_run_text = f"{time_since.days} day{'s' if time_since.days != 1 else ''} ago"
            elif time_since.seconds > 3600:
                hours = time_since.seconds // 3600
                last_run_text = f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif time_since.seconds > 60:
                minutes = time_since.seconds // 60
                last_run_text = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                last_run_text = "Just now"

            self.stdout.write(f"  Last Run: {last_run_text}")
        else:
            self.stdout.write(f"  Last Run: {self.style.WARNING('Never')}")

        if detector.configuration:
            config_summary = self.summarize_config(detector.configuration)
            if config_summary:
                self.stdout.write(f"  Configuration: {config_summary}")

        if options["stats"]:
            self.display_detection_stats(detector, options["recent"])

    def summarize_config(self, config):
        """Create a brief summary of detector configuration."""
        summary_parts = []

        if "threshold_multiplier" in config:
            summary_parts.append(f"threshold×{config['threshold_multiplier']}")

        if "baseline_days" in config:
            summary_parts.append(f"baseline {config['baseline_days']}d")

        if "minimum_events" in config:
            summary_parts.append(f"min {config['minimum_events']} events")

        if "minimum_displaced" in config:
            summary_parts.append(f"min {config['minimum_displaced']} displaced")

        return ", ".join(summary_parts[:3])  # Show max 3 items

    def display_detection_stats(self, detector, recent_days):
        """Display detection statistics for a detector."""
        total_detections = detector.detections.count()
        pending_detections = detector.detections.filter(status="pending").count()
        processed_detections = detector.detections.filter(status="processed").count()
        dismissed_detections = detector.detections.filter(status="dismissed").count()

        # Recent detections
        recent_cutoff = timezone.now() - timezone.timedelta(days=recent_days)
        recent_detections = detector.detections.filter(detection_timestamp__gte=recent_cutoff).count()

        self.stdout.write(f"  Detections: {total_detections} total")

        if total_detections > 0:
            status_parts = []
            if pending_detections:
                status_parts.append(f"{pending_detections} pending")
            if processed_detections:
                status_parts.append(f"{processed_detections} processed")
            if dismissed_detections:
                status_parts.append(f"{dismissed_detections} dismissed")

            if status_parts:
                self.stdout.write(f"    ({', '.join(status_parts)})")

            if recent_detections:
                self.stdout.write(f"    {recent_detections} in last {recent_days} days")

            # Average confidence score
            avg_confidence = detector.detections.filter(confidence_score__isnull=False).aggregate(avg_confidence=models.Avg("confidence_score"))["avg_confidence"]

            if avg_confidence:
                self.stdout.write(f"    Avg confidence: {avg_confidence:.2f}")
