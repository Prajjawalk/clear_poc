"""Management command to setup ACLED data source and variables."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from data_pipeline.models import Source, Variable


class Command(BaseCommand):
    """Setup ACLED data source and create variables."""

    help = "Setup ACLED data source and create conflict event variables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recreation of existing source and variables",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        force = options.get("force", False)
        
        self.stdout.write("Setting up ACLED data source...")

        # Create or get ACLED source
        source, created = Source.objects.get_or_create(
            name="ACLED",
            defaults={
                "class_name": "ACLED",
                "base_url": "https://acleddata.com/api/acled/read",
                "type": "api",
                "is_active": True,
                "description": "Armed Conflict Location & Event Data Project - Conflict event data for Sudan",
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Created ACLED source: {source.name}")
            )
        else:
            if force:
                source.class_name = "ACLED"
                source.base_url = "https://acleddata.com/api/acled/read"
                source.description = "Armed Conflict Location & Event Data Project - Conflict event data for Sudan"
                source.updated_at = timezone.now()
                source.save()
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Updated ACLED source: {source.name}")
                )
            else:
                self.stdout.write(f"ACLED source already exists: {source.name}")

        # Define ACLED variables
        variables_config = [
            {
                "code": "acled_total_events",
                "name": "Total Conflict Events",
                "text": "Total number of conflict events reported by ACLED for Sudan",
                "type": "quantitative",
                "period": "day",
                "adm_level": 2,
                "unit": "events",
            },
            {
                "code": "acled_fatalities",
                "name": "Conflict Fatalities",
                "text": "Total fatalities from conflict events reported by ACLED",
                "type": "quantitative",
                "period": "day",
                "adm_level": 2,
                "unit": "persons",
            },
            {
                "code": "acled_battles",
                "name": "Battle Events",
                "text": "Number of battles and armed clashes",
                "type": "quantitative",
                "period": "day",
                "adm_level": 2,
                "unit": "events",
            },
            {
                "code": "acled_violence_civilians",
                "name": "Violence Against Civilians",
                "text": "Number of violence against civilians events",
                "type": "quantitative",
                "period": "day",
                "adm_level": 2,
                "unit": "events",
            },
            {
                "code": "acled_explosions",
                "name": "Explosions and Remote Violence",
                "text": "Number of explosion and remote violence events",
                "type": "quantitative",
                "period": "day",
                "adm_level": 2,
                "unit": "events",
            },
            {
                "code": "acled_riots",
                "name": "Riots and Demonstrations",
                "text": "Number of riots, protests and demonstration events",
                "type": "quantitative",
                "period": "day",
                "adm_level": 2,
                "unit": "events",
            },
            {
                "code": "acled_strategic_developments",
                "name": "Strategic Developments",
                "text": "Number of strategic development events",
                "type": "quantitative",
                "period": "day",
                "adm_level": 2,
                "unit": "events",
            },
        ]

        # Create variables
        created_count = 0
        updated_count = 0

        for var_config in variables_config:
            variable, var_created = Variable.objects.get_or_create(
                source=source,
                code=var_config["code"],
                defaults={
                    "name": var_config["name"],
                    "text": var_config["text"],
                    "type": var_config["type"],
                    "period": var_config["period"],
                    "adm_level": var_config["adm_level"],
                    "unit": var_config.get("unit", ""),
                    "created_at": timezone.now(),
                    "updated_at": timezone.now(),
                },
            )

            if var_created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Created variable: {variable.code}")
                )
            else:
                if force:
                    variable.name = var_config["name"]
                    variable.text = var_config["text"]
                    variable.type = var_config["type"]
                    variable.period = var_config["period"]
                    variable.adm_level = var_config["adm_level"]
                    variable.unit = var_config.get("unit", "")
                    variable.updated_at = timezone.now()
                    variable.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Updated variable: {variable.code}")
                    )
                else:
                    self.stdout.write(f"  Variable already exists: {variable.code}")

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("ACLED Setup Complete!")
        self.stdout.write("=" * 50)
        self.stdout.write(f"Source: {source.name}")
        self.stdout.write(f"Created variables: {created_count}")
        if force:
            self.stdout.write(f"Updated variables: {updated_count}")
        self.stdout.write(f"Total variables: {Variable.objects.filter(source=source).count()}")

        # Environment check
        self.stdout.write("\n" + "-" * 30)
        self.stdout.write("Environment Check:")
        self.stdout.write("-" * 30)
        
        import os
        
        username = os.getenv("ACLED_USERNAME")
        api_key = os.getenv("ACLED_API_KEY")
        
        if username:
            self.stdout.write(self.style.SUCCESS(f"✓ ACLED_USERNAME: {username}"))
        else:
            self.stdout.write(self.style.ERROR("✗ ACLED_USERNAME not set"))
            
        if api_key:
            self.stdout.write(self.style.SUCCESS("✓ ACLED_API_KEY: [HIDDEN]"))
        else:
            self.stdout.write(self.style.ERROR("✗ ACLED_API_KEY not set"))

        if not username or not api_key:
            self.stdout.write("\n" + self.style.WARNING("⚠ Missing credentials! Set in .env file:"))
            self.stdout.write("ACLED_USERNAME=your_username")
            self.stdout.write("ACLED_API_KEY=your_api_key")

        self.stdout.write("\n" + "-" * 30)
        self.stdout.write("Next Steps:")
        self.stdout.write("-" * 30)
        self.stdout.write("1. Test API access: uv run manage.py test_acled_retrieval")
        self.stdout.write("2. Run pipeline: uv run manage.py run_pipeline --source=ACLED")
        self.stdout.write("3. Setup scheduled tasks: uv run manage.py create_acled_scheduled_tasks")