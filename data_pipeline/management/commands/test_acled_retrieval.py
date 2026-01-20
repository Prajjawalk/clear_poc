"""Management command to test ACLED data retrieval."""

import os
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from data_pipeline.models import Source, Variable
from data_pipeline.sources.acled import ACLED


class Command(BaseCommand):
    """Test ACLED API connectivity and data retrieval."""

    help = "Test ACLED API access and data retrieval functionality"

    def add_arguments(self, parser):
        parser.add_argument(
            "--variable-id",
            type=int,
            help="Test specific variable ID (default: test first variable)",
        )
        parser.add_argument(
            "--year",
            type=int,
            help="Year to retrieve data for (default: current year)",
        )
        parser.add_argument(
            "--limit-days",
            type=int,
            default=30,
            help="Limit to last N days (default: 30)",
        )

    def handle(self, *args, **options):
        """Execute the test command."""
        self.stdout.write("Testing ACLED data retrieval...")
        self.stdout.write("=" * 50)

        # Get ACLED source
        try:
            source = Source.objects.get(name="ACLED")
        except Source.DoesNotExist:
            self.stdout.write(
                self.style.ERROR("✗ ACLED source not found. Run 'setup_acled_source' first.")
            )
            return

        # Check environment variables
        self.stdout.write("1. Checking environment variables...")
        username = os.getenv("ACLED_USERNAME")
        api_key = os.getenv("ACLED_API_KEY")

        if not username or not api_key:
            self.stdout.write(
                self.style.ERROR("✗ Missing ACLED credentials in environment")
            )
            self.stdout.write("Set ACLED_USERNAME and ACLED_API_KEY in .env file")
            return

        self.stdout.write(self.style.SUCCESS(f"✓ ACLED_USERNAME: {username}"))
        self.stdout.write(self.style.SUCCESS("✓ ACLED_API_KEY: [HIDDEN]"))

        # Get test variable
        variable_id = options.get("variable_id")
        if variable_id:
            try:
                variable = Variable.objects.get(id=variable_id, source=source)
            except Variable.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"✗ Variable with ID {variable_id} not found")
                )
                return
        else:
            variable = Variable.objects.filter(source=source).first()
            if not variable:
                self.stdout.write(
                    self.style.ERROR("✗ No variables found for ACLED source")
                )
                return

        self.stdout.write(f"\n2. Testing with variable: {variable.code}")

        # Initialize ACLED source
        acled = ACLED(source)

        # Check API status first
        self.stdout.write("\n3. Checking ACLED API status...")
        status = acled.check_api_status()
        
        if not status["base_url_accessible"]:
            self.stdout.write(self.style.ERROR(f"✗ ACLED website not accessible: {status['error_message']}"))
            return
        else:
            self.stdout.write(self.style.SUCCESS("✓ ACLED website accessible"))
            
        if status["blocked"]:
            self.stdout.write(self.style.ERROR(f"✗ {status['error_message']}"))
            self.stdout.write(self.style.WARNING("Wait some time (15-30 minutes) before retrying."))
            return
        elif not status["credentials_valid"]:
            self.stdout.write(self.style.ERROR(f"✗ Invalid credentials: {status['error_message']}"))
            return
        elif not status["api_accessible"]:
            self.stdout.write(self.style.ERROR("✗ Cannot access ACLED API endpoint"))
            return
        else:
            self.stdout.write(self.style.SUCCESS("✓ Authentication and API access working"))

        # Prepare test parameters
        year = options.get("year")
        limit_days = options.get("limit_days", 30)
        
        kwargs = {}
        if year:
            kwargs["year"] = year
            self.stdout.write(f"\n4. Testing data retrieval for year {year}...")
        else:
            # Default to recent data
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=limit_days)
            kwargs["start_date"] = start_date.strftime("%Y-%m-%d")
            kwargs["end_date"] = end_date.strftime("%Y-%m-%d")
            self.stdout.write(f"\n4. Testing data retrieval for {start_date} to {end_date}...")

        # Test data retrieval
        try:
            success = acled.get(variable, **kwargs)
            if success:
                self.stdout.write(self.style.SUCCESS("✓ Data retrieval successful"))
                
                # Show some stats about retrieved data
                latest_file = acled._get_latest_raw_data_file(variable)
                if latest_file:
                    import json
                    with open(latest_file, 'r') as f:
                        raw_data = json.load(f)
                    events = raw_data.get('events', [])
                    self.stdout.write(f"  - Retrieved {len(events)} events")
                    self.stdout.write(f"  - Raw data saved to: {latest_file}")
                    
                    # Show sample events
                    if events:
                        self.stdout.write("\n  Sample events:")
                        for i, event in enumerate(events[:3], 1):
                            location = event.get('admin1', 'Unknown')
                            date = event.get('event_date', 'Unknown')
                            event_type = event.get('event_type', 'Unknown')
                            fatalities = event.get('fatalities', 0)
                            self.stdout.write(f"    {i}. {date} - {event_type} in {location} - {fatalities} fatalities")
            else:
                self.stdout.write(self.style.ERROR("✗ Data retrieval failed"))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Data retrieval error: {str(e)}"))
            return

        # Test data processing
        self.stdout.write("\n5. Testing data processing...")
        try:
            success = acled.process(variable, **kwargs)
            if success:
                self.stdout.write(self.style.SUCCESS("✓ Data processing successful"))
                
                # Show processed data stats
                from data_pipeline.models import VariableData
                total_records = VariableData.objects.filter(
                    variable__source=source
                ).count()
                self.stdout.write(f"  - Total processed records: {total_records}")
                
                # Show records per variable
                for var in Variable.objects.filter(source=source):
                    count = VariableData.objects.filter(variable=var).count()
                    if count > 0:
                        self.stdout.write(f"  - {var.code}: {count} records")
            else:
                self.stdout.write(self.style.ERROR("✗ Data processing failed"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Data processing error: {str(e)}"))

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("ACLED Test Complete!")
        self.stdout.write("=" * 50)
        self.stdout.write("If all tests passed, ACLED integration is working correctly.")
        self.stdout.write("\nNext steps:")
        self.stdout.write("- Run full pipeline: uv run manage.py run_pipeline --source=ACLED")
        self.stdout.write("- Setup scheduled tasks: uv run manage.py create_acled_scheduled_tasks")