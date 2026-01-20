"""Management command to test the BERT detector on existing data."""

import sys
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from alert_framework.models import Detector
from data_pipeline.models import VariableData


class Command(BaseCommand):
    """Test the BERT detector on existing Dataminr data."""

    help = "Test the BERT detector on existing Dataminr data"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--detector-id",
            type=int,
            help="Detector ID to test (default: search for DataminrBertDetector)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days of data to test (default: 7)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit number of data points to process",
        )
        parser.add_argument(
            "--show-detections",
            action="store_true",
            help="Show details of each detection",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run detection without saving to database",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        # Find the detector
        if options["detector_id"]:
            try:
                detector = Detector.objects.get(id=options["detector_id"])
            except Detector.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Detector with ID {options['detector_id']} not found"))
                sys.exit(1)
        else:
            # Find DataminrBertDetector (check both with and without module prefix)
            detector = Detector.objects.filter(
                class_name__in=["DataminrBertDetector", "dataminr_bert_detector.DataminrBertDetector"], active=True
            ).first()
            if not detector:
                self.stdout.write(self.style.ERROR("No active DataminrBertDetector found"))
                self.stdout.write("Available detectors:")
                for d in Detector.objects.all():
                    self.stdout.write(f"  - {d.name} (ID: {d.id}, Class: {d.class_name})")
                sys.exit(1)

        self.stdout.write(self.style.SUCCESS(f"\n{'='*70}"))
        self.stdout.write(self.style.SUCCESS(f"Testing detector: {detector.name}"))
        self.stdout.write(self.style.SUCCESS(f"Class: {detector.class_name}"))
        self.stdout.write(self.style.SUCCESS(f"ID: {detector.id}"))
        self.stdout.write(self.style.SUCCESS(f"{'='*70}\n"))

        # Show configuration
        config = detector.configuration or {}
        self.stdout.write(self.style.WARNING("Configuration:"))
        for key, value in config.items():
            if key == "shock_type_mapping" and isinstance(value, dict):
                self.stdout.write(f"  {key}:")
                for rule, shock_type in list(value.items())[:5]:  # Show first 5
                    self.stdout.write(f"    - {rule} → {shock_type}")
                if len(value) > 5:
                    self.stdout.write(f"    ... and {len(value) - 5} more rules")
            else:
                self.stdout.write(f"  {key}: {value}")

        # Get date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=options["days"])

        self.stdout.write(f"\nDate range: {start_date.date()} to {end_date.date()}")

        # Check available data
        variable_code = config.get("variable_code")
        if not variable_code:
            self.stdout.write(self.style.ERROR("No variable_code in detector configuration"))
            sys.exit(1)

        data_query = VariableData.objects.filter(
            variable__code=variable_code,
            start_date__gte=start_date.date(),
            start_date__lte=end_date.date(),
        )

        if options["limit"]:
            data_query = data_query[: options["limit"]]

        data_count = data_query.count()
        self.stdout.write(f"Available data points: {data_count}")

        if data_count == 0:
            self.stdout.write(self.style.WARNING("No data found for the specified period"))
            sys.exit(0)

        # Show sample data
        sample_data = data_query.first()
        if sample_data:
            self.stdout.write(f"\nSample data point:")
            self.stdout.write(f"  Variable: {sample_data.variable.name}")
            self.stdout.write(f"  Date: {sample_data.start_date}")
            self.stdout.write(f"  Location: {sample_data.gid.name if sample_data.gid else 'N/A'}")
            value = getattr(sample_data, config.get("headline_field", "value"), "")
            if value:
                self.stdout.write(f"  Headline: {str(value)[:100]}...")

        # Initialize and run detector
        self.stdout.write(f"\n{self.style.WARNING('Initializing detector...')}")

        try:
            # Import the detector class
            from alert_framework.detectors.dataminr_bert_detector import DataminrBertDetector

            # Initialize detector instance
            detector_instance = DataminrBertDetector(detector)

            self.stdout.write(self.style.SUCCESS("Detector initialized successfully"))
            self.stdout.write(f"Model path: {detector_instance.model_path}")
            self.stdout.write(f"Confidence threshold: {detector_instance.confidence_threshold}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to initialize detector: {str(e)}"))
            import traceback

            traceback.print_exc()
            sys.exit(1)

        # Run detection
        self.stdout.write(f"\n{self.style.WARNING('Running detection...')}")

        try:
            detections = detector_instance.detect(start_date, end_date)

            self.stdout.write(self.style.SUCCESS(f"\nDetection completed!"))
            self.stdout.write(f"Total detections: {len(detections)}")

            if data_count > 0:
                detection_rate = len(detections) / data_count * 100
                self.stdout.write(f"Detection rate: {detection_rate:.1f}% ({len(detections)}/{data_count})")

            # Show detection summary
            if detections:
                shock_types = {}
                confidence_scores = []
                locations = {}

                for detection in detections:
                    # Count shock types
                    shock_type = detection.get("shock_type_name", "Unknown")
                    shock_types[shock_type] = shock_types.get(shock_type, 0) + 1

                    # Collect confidence scores
                    if detection.get("confidence_score"):
                        confidence_scores.append(detection["confidence_score"])

                    # Count locations
                    for loc in detection.get("locations", []):
                        loc_name = loc.name if hasattr(loc, "name") else str(loc)
                        locations[loc_name] = locations.get(loc_name, 0) + 1

                self.stdout.write(f"\n{self.style.SUCCESS('Detection Summary:')}")

                # Shock type distribution
                self.stdout.write(f"\nShock type distribution:")
                for shock_type, count in sorted(shock_types.items(), key=lambda x: x[1], reverse=True):
                    percentage = count / len(detections) * 100
                    self.stdout.write(f"  - {shock_type}: {count} ({percentage:.1f}%)")

                # Confidence statistics
                if confidence_scores:
                    avg_conf = sum(confidence_scores) / len(confidence_scores)
                    min_conf = min(confidence_scores)
                    max_conf = max(confidence_scores)
                    self.stdout.write(f"\nConfidence scores:")
                    self.stdout.write(f"  - Average: {avg_conf:.3f}")
                    self.stdout.write(f"  - Range: {min_conf:.3f} to {max_conf:.3f}")

                # Top locations
                if locations:
                    self.stdout.write(f"\nTop locations:")
                    for loc_name, count in sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]:
                        self.stdout.write(f"  - {loc_name}: {count}")

                # Show individual detections if requested
                if options["show_detections"]:
                    self.stdout.write(f"\n{self.style.SUCCESS('Individual Detections:')}")
                    for i, detection in enumerate(detections[:10], 1):  # Show first 10
                        self.stdout.write(f"\n{i}. Detection:")
                        self.stdout.write(f"   Timestamp: {detection['detection_timestamp']}")
                        self.stdout.write(f"   Shock Type: {detection['shock_type_name']}")
                        self.stdout.write(f"   Confidence: {detection['confidence_score']:.3f}")

                        locs = detection.get("locations", [])
                        if locs:
                            loc_names = [loc.name if hasattr(loc, "name") else str(loc) for loc in locs]
                            self.stdout.write(f"   Locations: {', '.join(loc_names)}")

                        detection_data = detection.get("detection_data", {})
                        if detection_data.get("headline"):
                            headline = detection_data["headline"][:100]
                            self.stdout.write(f"   Headline: {headline}...")

                    if len(detections) > 10:
                        self.stdout.write(f"\n   ... and {len(detections) - 10} more detections")

            # Save detections if not dry run
            if not options["dry_run"] and detections:
                self.stdout.write(f"\n{self.style.WARNING('Saving detections to database...')}")
                try:
                    from alert_framework.models import Detection

                    saved_count = 0
                    skipped_count = 0
                    for detection_data in detections:
                        # Use get_or_create to handle duplicates gracefully
                        detection, created = Detection.objects.get_or_create(
                            detector=detector,
                            title=detection_data.get("title", "Untitled Detection"),
                            detection_timestamp=detection_data["detection_timestamp"],
                            defaults={
                                "confidence_score": detection_data.get("confidence_score"),
                                "shock_type_id": None,  # Will be set by signal handler
                                "detection_data": detection_data.get("detection_data", {}),
                            },
                        )

                        if created:
                            # Add locations (M2M relationship) only for new detections
                            if detection_data.get("locations"):
                                detection.locations.set(detection_data["locations"])
                            saved_count += 1
                        else:
                            skipped_count += 1

                    self.stdout.write(self.style.SUCCESS(f"Saved {saved_count} new detections to database"))
                    if skipped_count > 0:
                        self.stdout.write(self.style.WARNING(f"Skipped {skipped_count} duplicate detections"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to save detections: {str(e)}"))
                    import traceback

                    traceback.print_exc()

            elif options["dry_run"]:
                self.stdout.write(self.style.WARNING("\nDry run mode - detections not saved to database"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Detection failed: {str(e)}"))
            import traceback

            traceback.print_exc()
            sys.exit(1)

        self.stdout.write(f"\n{self.style.SUCCESS('Test completed!')}")
