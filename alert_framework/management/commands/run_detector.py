"""Management command to manually run a detector."""

from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from alert_framework.models import Detector
from alert_framework.tasks import run_detector
from alert_framework.utils import run_task_with_fallback


class Command(BaseCommand):
    """Manually trigger detector execution from command line."""

    help = "Manually run a detector with optional date range"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "detector",
            type=str,
            nargs="?",  # Make detector optional when using --list
            help="Detector ID or name to run",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            help="Start date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
            default=None,
        )
        parser.add_argument(
            "--end-date",
            type=str,
            help="End date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
            default=None,
        )
        parser.add_argument(
            "--days",
            type=int,
            help="Number of days to look back (alternative to start-date, default: 7)",
            default=None,
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all available detectors",
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Run synchronously (without Celery) for debugging",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        if options["list"]:
            self.list_detectors()
            return

        # Ensure detector argument is provided
        if not options["detector"]:
            raise CommandError(
                "Detector ID or name is required. Use --list to see available detectors."
            )

        # Get detector
        detector = self.get_detector(options["detector"])

        if not detector:
            raise CommandError(f"Detector '{options['detector']}' not found")

        # Parse date parameters
        start_date, end_date = self.parse_dates(options)

        self.stdout.write(
            self.style.SUCCESS(f"\n{'='*60}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Running detector: {detector.name}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"{'='*60}\n")
        )
        self.stdout.write(f"Detector ID: {detector.id}")
        self.stdout.write(f"Class: {detector.class_name}")
        self.stdout.write(f"Status: {'Active' if detector.active else 'Inactive'}")
        self.stdout.write(f"Start date: {start_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.stdout.write(f"End date: {end_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not detector.active:
            self.stdout.write(
                self.style.WARNING(
                    "\nWarning: Detector is inactive but will run anyway."
                )
            )

        # Run detector
        self.stdout.write(f"\n{self.style.SUCCESS('Starting detection...')}\n")

        try:
            if options["sync"]:
                # Run synchronously (directly call the task function)
                from alert_framework.tasks import run_detector as run_detector_task

                result = run_detector_task(
                    detector.id,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
            else:
                # Run via Celery with fallback
                result, execution_mode = run_task_with_fallback(
                    run_detector,
                    detector.id,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    task_name=f"Detector '{detector.name}'",
                )

                # If using Celery, wait for result
                if execution_mode == "celery":
                    self.stdout.write("Task submitted to Celery queue...")
                    self.stdout.write(f"Task ID: {result.id}")
                    self.stdout.write("\nWaiting for result...")
                    result = result.get(timeout=300)  # 5 minute timeout
                elif execution_mode == "sync":
                    self.stdout.write("Running synchronously (Celery not available)...")

            # Display results
            self.display_results(result)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nError running detector: {str(e)}"))
            raise CommandError(f"Detector execution failed: {str(e)}")

    def get_detector(self, detector_identifier):
        """Get detector by ID or name."""
        # Try as ID first
        try:
            detector_id = int(detector_identifier)
            return Detector.objects.get(id=detector_id)
        except (ValueError, Detector.DoesNotExist):
            pass

        # Try as name
        try:
            return Detector.objects.get(name__iexact=detector_identifier)
        except Detector.DoesNotExist:
            return None

    def parse_dates(self, options):
        """Parse start and end dates from command options."""
        end_date = timezone.now()

        if options["end_date"]:
            try:
                end_date = self.parse_datetime(options["end_date"])
            except ValueError as e:
                raise CommandError(f"Invalid end date format: {e}")

        if options["start_date"]:
            try:
                start_date = self.parse_datetime(options["start_date"])
            except ValueError as e:
                raise CommandError(f"Invalid start date format: {e}")
        elif options["days"]:
            start_date = end_date - timedelta(days=options["days"])
        else:
            # Default to 7 days
            start_date = end_date - timedelta(days=7)

        return start_date, end_date

    def parse_datetime(self, date_string):
        """Parse datetime from string, handling both date and datetime formats."""
        # Try full datetime format first
        for fmt in [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(date_string, fmt)
                # Make timezone aware
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                return dt
            except ValueError:
                continue

        raise ValueError(
            f"Could not parse '{date_string}'. Use format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"
        )

    def list_detectors(self):
        """List all available detectors."""
        detectors = Detector.objects.all().order_by("id")

        if not detectors:
            self.stdout.write(self.style.WARNING("No detectors found."))
            return

        self.stdout.write(self.style.SUCCESS(f"\nAvailable detectors ({detectors.count()}):"))
        self.stdout.write(f"\n{'ID':<5} {'Name':<40} {'Status':<10} {'Class'}")
        self.stdout.write("-" * 100)

        for detector in detectors:
            status = self.style.SUCCESS("Active") if detector.active else self.style.ERROR("Inactive")
            self.stdout.write(f"{detector.id:<5} {detector.name:<40} {status:<10} {detector.class_name}")

        self.stdout.write(f"\nUsage: python manage.py run_detector <id_or_name> [options]")

    def display_results(self, result):
        """Display execution results."""
        self.stdout.write(f"\n{self.style.SUCCESS('='*60)}")
        self.stdout.write(self.style.SUCCESS("Detection Results"))
        self.stdout.write(f"{self.style.SUCCESS('='*60)}\n")

        if result.get("success"):
            self.stdout.write(self.style.SUCCESS("✓ Detector executed successfully"))
        else:
            self.stdout.write(self.style.ERROR("✗ Detector execution failed"))
            if result.get("error_message"):
                self.stdout.write(self.style.ERROR(f"  Error: {result['error_message']}"))
            return

        # Display statistics
        detections_created = result.get("detections_created", 0)
        detections_duplicates = result.get("detections_duplicates", 0)
        alerts_created = result.get("alerts_created", 0)
        duration = result.get("duration_seconds", 0)

        self.stdout.write(f"\nDetections created: {self.style.SUCCESS(str(detections_created))}")

        if detections_duplicates > 0:
            self.stdout.write(
                f"Duplicate detections skipped: {self.style.WARNING(str(detections_duplicates))}"
            )

        if alerts_created is not None:
            self.stdout.write(f"Alerts created: {self.style.SUCCESS(str(alerts_created))}")

        self.stdout.write(f"Duration: {duration:.2f} seconds")

        if result.get("processing_error"):
            self.stdout.write(
                self.style.WARNING(
                    f"\nWarning: Alert processing had errors: {result['processing_error']}"
                )
            )

        # Summary message
        if detections_created == 0:
            self.stdout.write(
                f"\n{self.style.WARNING('No new detections found in the specified date range.')}"
            )
        else:
            self.stdout.write(
                f"\n{self.style.SUCCESS(f'Created {detections_created} detection(s)')}"
            )
            if alerts_created and alerts_created > 0:
                self.stdout.write(
                    f"{self.style.SUCCESS(f'Generated {alerts_created} alert(s)')}"
                )
