"""Management command to set up ACLED scheduled data retrieval tasks."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from data_pipeline.models import Source, Variable


class Command(BaseCommand):
    """Set up ACLED scheduled data retrieval tasks."""

    help = "Set up ACLED scheduled data retrieval tasks"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset existing ACLED scheduled tasks before creating new ones",
        )
        parser.add_argument(
            "--variable",
            type=str,
            help="Set up task for specific ACLED variable code (e.g., acled_total_events)",
            default="all",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting existing ACLED scheduled tasks..."))
            PeriodicTask.objects.filter(name__startswith="ACLED").delete()
            # Also clean up unused cron schedules
            CrontabSchedule.objects.filter(periodictask__isnull=True, hour="4", minute="0", day_of_week="*", day_of_month="*", month_of_year="*").delete()

        # Get ACLED source
        try:
            acled_source = Source.objects.get(name="ACLED")
        except Source.DoesNotExist:
            self.stdout.write(self.style.ERROR("ACLED source not found. Please ensure ACLED source is set up first."))
            return

        variable_code = options["variable"].lower()

        with transaction.atomic():
            if variable_code == "all":
                # Set up tasks for all ACLED variables
                self.setup_all_acled_tasks(acled_source)
            else:
                # Set up task for specific variable
                self.setup_specific_acled_task(acled_source, variable_code)

        self.stdout.write(self.style.SUCCESS(f"Successfully set up ACLED scheduled tasks for {variable_code}"))

    def setup_all_acled_tasks(self, acled_source):
        """Set up single ACLED task that processes all variables."""
        variables = Variable.objects.filter(source=acled_source)

        if not variables.exists():
            self.stdout.write(self.style.WARNING("No ACLED variables found"))
            return

        # Create single task for all ACLED data (no variable ID specified)
        self.setup_acled_task(acled_source, None, "All Variables")

    def setup_specific_acled_task(self, acled_source, variable_code):
        """Set up task for a specific ACLED variable."""
        try:
            variable = Variable.objects.get(source=acled_source, code=variable_code)
            display_name = variable.name or variable_code.replace("acled_", "").replace("_", " ").title()
            self.setup_acled_task(acled_source, variable, display_name)
        except Variable.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"ACLED variable '{variable_code}' not found"))

    def setup_acled_task(self, source, variable, display_name):
        """Set up a scheduled task for ACLED data retrieval."""
        # Create or get crontab schedule (daily at 4 AM UTC)
        schedule, schedule_created = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="4",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        if schedule_created:
            self.stdout.write("  Created crontab schedule: daily at 4 AM UTC")

        # Create or get periodic task
        if variable is None:
            # Task for all variables (source only)
            task_name = f"ACLED Daily Update - {display_name}"
            args = f"[{source.id}]"
            description = f"Daily retrieval of all ACLED conflict event data"
        else:
            # Task for specific variable
            task_name = f"ACLED Daily Update - {display_name}"
            args = f"[{source.id}, {variable.id}]"
            description = f"Daily retrieval of ACLED conflict event data for {display_name.lower()}"

        task_config = {
            "task": "data_pipeline.tasks.full_pipeline",
            "crontab": schedule,
            "args": args,
            "kwargs": "{}",
            "enabled": True,
            "description": description,
        }

        task, task_created = PeriodicTask.objects.get_or_create(
            name=task_name,
            defaults=task_config,
        )

        # Update existing task if it was not just created
        if not task_created:
            for key, value in task_config.items():
                setattr(task, key, value)
            task.save()

        action = "Created" if task_created else "Updated"
        self.stdout.write(f"  {action} ACLED task: {task_name}")
        if variable:
            self.stdout.write(f"    Source ID: {source.id}, Variable ID: {variable.id}")
        else:
            self.stdout.write(f"    Source ID: {source.id} (all variables)")
        self.stdout.write("    Schedule: Daily at 4 AM UTC")

    def get_available_variables(self):
        """Display available ACLED variables."""
        try:
            acled_source = Source.objects.get(name="ACLED")
            variables = Variable.objects.filter(source=acled_source)

            self.stdout.write("Available ACLED variables:")
            for var in variables:
                self.stdout.write(f"  - {var.code}: {var.name}")
        except Source.DoesNotExist:
            self.stdout.write(self.style.ERROR("ACLED source not found"))
