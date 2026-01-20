"""Management command to set up all data pipeline scheduled tasks."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django_celery_beat.models import PeriodicTask, CrontabSchedule

from data_pipeline.models import Source, Variable


class Command(BaseCommand):
    """Set up all data pipeline scheduled tasks for various sources."""

    help = "Set up scheduled data retrieval tasks for all data sources"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset existing data pipeline tasks before creating new ones",
        )
        parser.add_argument(
            "--source",
            type=str,
            help="Set up tasks for specific source (IDMC, ACLED, IOM, ReliefWeb, all)",
            default="all",
        )
        parser.add_argument(
            "--list-sources",
            action="store_true",
            help="List available sources and their variables",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        if options["list_sources"]:
            self.list_sources()
            return

        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting existing data pipeline tasks..."))
            PeriodicTask.objects.filter(task="data_pipeline.tasks.full_pipeline").delete()

        source_name = options["source"].upper()

        with transaction.atomic():
            if source_name == "ALL":
                self.setup_all_sources()
            else:
                self.setup_source_tasks(source_name)

        self.stdout.write(self.style.SUCCESS(f"Successfully set up data pipeline tasks for {source_name}"))

    def setup_all_sources(self):
        """Set up tasks for all sources."""
        self.setup_source_tasks("IDMC")
        self.setup_source_tasks("ACLED")
        self.setup_source_tasks("IOM")
        self.setup_source_tasks("RELIEFWEB")

    def setup_source_tasks(self, source_name):
        """Set up tasks for a specific source."""
        try:
            source = Source.objects.get(name__iexact=source_name)
        except Source.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Source '{source_name}' not found"))
            return

        if source_name.upper() == "IDMC":
            self.setup_idmc_tasks(source)
        elif source_name.upper() == "ACLED":
            self.setup_acled_tasks(source)
        elif source_name.upper() == "IOM":
            self.setup_iom_tasks(source)
        elif source_name.upper() == "RELIEFWEB":
            self.setup_reliefweb_tasks(source)
        else:
            self.stdout.write(self.style.WARNING(f"No specific setup defined for {source_name}, using default"))
            self.setup_default_tasks(source)

    def setup_idmc_tasks(self, source):
        """Set up IDMC-specific tasks."""
        self.stdout.write(f"Setting up IDMC tasks...")

        # Monthly GIDD tasks (1st of month at 2 AM)
        monthly_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="2", day_of_week="*", day_of_month="1", month_of_year="*"
        )

        # Daily IDU tasks (6 AM)
        daily_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="6", day_of_week="*", day_of_month="*", month_of_year="*"
        )

        # GIDD variables (monthly)
        gidd_vars = source.variables.filter(code__contains="gidd")
        for var in gidd_vars:
            task_name = f"IDMC GIDD Monthly - {var.name}"
            self.create_or_update_task(task_name, source, var, monthly_schedule,
                                     f"Monthly full pipeline execution for {var.name}")

        # IDU variables (daily)
        idu_vars = source.variables.filter(code__contains="idu")
        for var in idu_vars:
            task_name = f"IDMC IDU Daily - {var.name}"
            self.create_or_update_task(task_name, source, var, daily_schedule,
                                     f"Daily full pipeline execution for {var.name}")

    def setup_acled_tasks(self, source):
        """Set up ACLED-specific tasks."""
        self.stdout.write(f"Setting up ACLED tasks...")

        # Daily at 4 AM
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="4", day_of_week="*", day_of_month="*", month_of_year="*"
        )

        # Single task for all ACLED data (source processes all variables at once)
        task_name = f"ACLED Daily Update - All Variables"
        task_config = {
            "task": "data_pipeline.tasks.full_pipeline",
            "crontab": schedule,
            "args": f"[{source.id}]",  # Only source ID, no variable ID
            "kwargs": "{}",
            "enabled": True,
            "description": f"Daily retrieval of all ACLED conflict event data"
        }

        task, created = PeriodicTask.objects.get_or_create(
            name=task_name, defaults=task_config
        )

        if not created:
            for key, value in task_config.items():
                setattr(task, key, value)
            task.save()

        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} task: {task_name}")
        self.stdout.write(f"    Source ID: {source.id} (processes all variables)")

    def setup_iom_tasks(self, source):
        """Set up IOM DTM-specific tasks."""
        self.stdout.write(f"Setting up IOM DTM tasks...")

        # Daily at 2 AM
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="2", day_of_week="*", day_of_month="*", month_of_year="*"
        )

        # IOM DTM variables
        iom_vars = source.variables.all()
        for var in iom_vars:
            task_name = f"IOM DTM Daily - {var.name}"
            self.create_or_update_task(task_name, source, var, schedule,
                                     f"Daily retrieval of IDP data from IOM's Displacement Tracking Matrix")

    def setup_reliefweb_tasks(self, source):
        """Set up ReliefWeb-specific tasks."""
        self.stdout.write(f"Setting up ReliefWeb tasks...")

        # Daily at 6 AM (same as IDMC IDU)
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="6", day_of_week="*", day_of_month="*", month_of_year="*"
        )

        task_name = f"ReliefWeb - Daily Update"
        task_config = {
            "task": "data_pipeline.tasks.full_pipeline",
            "crontab": schedule,
            "args": f"[{source.id}]",
            "kwargs": "{}",
            "enabled": True,
            "description": f"Daily retrieval of data from ReliefWeb API"
        }

        task, created = PeriodicTask.objects.get_or_create(
            name=task_name, defaults=task_config
        )

        if not created:
            for key, value in task_config.items():
                setattr(task, key, value)
            task.save()

        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} task: {task_name}")

    def setup_default_tasks(self, source):
        """Set up default daily tasks for any source."""
        self.stdout.write(f"Setting up default tasks for {source.name}...")

        # Daily at 3 AM
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="3", day_of_week="*", day_of_month="*", month_of_year="*"
        )

        variables = source.variables.all()
        for var in variables:
            task_name = f"{source.name} Daily - {var.name}"
            self.create_or_update_task(task_name, source, var, schedule,
                                     f"Daily retrieval of {var.name.lower()} data from {source.name}")

    def create_or_update_task(self, task_name, source, variable, schedule, description):
        """Create or update a periodic task."""
        task_config = {
            "task": "data_pipeline.tasks.full_pipeline",
            "crontab": schedule,
            "args": f"[{source.id}, {variable.id}]",
            "kwargs": "{}",
            "enabled": True,
            "description": description
        }

        task, created = PeriodicTask.objects.get_or_create(
            name=task_name, defaults=task_config
        )

        if not created:
            for key, value in task_config.items():
                setattr(task, key, value)
            task.save()

        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} task: {task_name}")

    def list_sources(self):
        """List all available sources and their variables."""
        sources = Source.objects.all().order_by("name")

        self.stdout.write("Available sources:")
        for source in sources:
            self.stdout.write(f"\n{source.name} (ID: {source.id})")
            variables = source.variables.all()

            if variables.exists():
                for var in variables:
                    self.stdout.write(f"  - {var.code}: {var.name} (ID: {var.id})")
            else:
                self.stdout.write("  No variables found")