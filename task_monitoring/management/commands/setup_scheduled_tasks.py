"""Management command to set up scheduled tasks for data pipeline operations."""

from django.core.management.base import BaseCommand, CommandError
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from data_pipeline.models import Source


class Command(BaseCommand):
    """Management command for setting up scheduled data pipeline tasks."""

    help = "Set up scheduled tasks for IDMC and other data pipeline operations"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--source",
            type=str,
            help="Set up tasks for specific source only (e.g., 'IDMC')"
        )
        
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what tasks would be created without actually creating them"
        )
        
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing scheduled tasks"
        )

    def handle(self, *args, **options):
        """Handle command execution."""
        source_filter = options.get("source")
        dry_run = options.get("dry_run", False)
        overwrite = options.get("overwrite", False)

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No tasks will be created")
            )

        try:
            # Get sources to process
            if source_filter:
                sources = Source.objects.filter(name__iexact=source_filter)
                if not sources.exists():
                    raise CommandError(f"Source '{source_filter}' not found")
            else:
                sources = Source.objects.all()

            if not sources.exists():
                self.stdout.write(
                    self.style.WARNING("No sources found in database.")
                )
                return

            # Set up general maintenance tasks
            self.setup_maintenance_tasks(dry_run, overwrite)

            # Set up source-specific tasks
            for source in sources:
                self.setup_source_tasks(source, dry_run, overwrite)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully {'would set up' if dry_run else 'set up'} "
                    f"scheduled tasks for {sources.count()} source(s)"
                )
            )

        except Exception as e:
            raise CommandError(f"Failed to set up scheduled tasks: {str(e)}")

    def setup_maintenance_tasks(self, dry_run: bool, overwrite: bool):
        """Set up general maintenance tasks."""
        self.stdout.write("\nSetting up maintenance tasks...")

        # Daily statistics update
        task_name = "Daily Task Statistics Update"
        task_path = "data_pipeline.tasks.update_task_statistics"
        
        # Create daily schedule at 1:00 AM
        crontab, created = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="1", 
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        if dry_run:
            self.stdout.write(f"  Would create: {task_name}")
            return

        # Check if task already exists
        existing_task = PeriodicTask.objects.filter(name=task_name).first()
        if existing_task:
            if overwrite:
                existing_task.delete()
                self.stdout.write(f"  Deleted existing task: {task_name}")
            else:
                self.stdout.write(f"  Task already exists: {task_name}")
                return

        # Create the task
        PeriodicTask.objects.create(
            name=task_name,
            task=task_path,
            crontab=crontab,
            description="Update daily task execution statistics",
            enabled=True,
        )
        
        self.stdout.write(
            self.style.SUCCESS(f"  Created maintenance task: {task_name}")
        )

    def setup_source_tasks(self, source: Source, dry_run: bool, overwrite: bool):
        """Set up scheduled tasks for a specific source."""
        self.stdout.write(f"\nSetting up tasks for source: {source.name}")

        # Get variables for this source
        variables = source.variables.all()
        if not variables.exists():
            self.stdout.write(
                self.style.WARNING(f"  No variables found for source {source.name}")
            )
            return

        # Set up different schedules based on source type
        if source.name.upper() == "IDMC":
            self.setup_idmc_tasks(source, variables, dry_run, overwrite)
        else:
            self.setup_generic_source_tasks(source, variables, dry_run, overwrite)

    def setup_idmc_tasks(self, source: Source, variables, dry_run: bool, overwrite: bool):
        """Set up IDMC-specific scheduled tasks."""
        # IDMC full pipeline - daily at 6:00 AM UTC
        crontab_daily, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="6",
            day_of_week="*", 
            day_of_month="*",
            month_of_year="*",
        )

        for variable in variables:
            task_name = f"IDMC Daily Pipeline - {variable.name}"
            task_path = "data_pipeline.tasks.full_pipeline"
            
            if dry_run:
                self.stdout.write(f"  Would create: {task_name}")
                continue

            # Check if task already exists
            existing_task = PeriodicTask.objects.filter(name=task_name).first()
            if existing_task:
                if overwrite:
                    existing_task.delete()
                    self.stdout.write(f"  Deleted existing task: {task_name}")
                else:
                    self.stdout.write(f"  Task already exists: {task_name}")
                    continue

            # Create the task with source and variable arguments
            PeriodicTask.objects.create(
                name=task_name,
                task=task_path,
                crontab=crontab_daily,
                args=[source.id, variable.id],
                description=f"Daily full pipeline execution for IDMC {variable.name} data",
                enabled=True,
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"  Created IDMC task: {task_name}")
            )

        # Weekly data retrieval check - Mondays at 5:00 AM UTC
        crontab_weekly, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="5",
            day_of_week="1",  # Monday
            day_of_month="*",
            month_of_year="*",
        )

        weekly_task_name = "IDMC Weekly Data Check"
        task_path = "data_pipeline.tasks.retrieve_data"
        
        if dry_run:
            self.stdout.write(f"  Would create: {weekly_task_name}")
            return

        existing_weekly = PeriodicTask.objects.filter(name=weekly_task_name).first()
        if existing_weekly:
            if overwrite:
                existing_weekly.delete()
                self.stdout.write(f"  Deleted existing task: {weekly_task_name}")
            else:
                self.stdout.write(f"  Task already exists: {weekly_task_name}")
                return

        # Create weekly check task for all IDMC variables
        PeriodicTask.objects.create(
            name=weekly_task_name,
            task=task_path,
            crontab=crontab_weekly,
            args=[source.id],  # Process all variables for source
            description="Weekly data availability check for IDMC sources",
            enabled=True,
        )
        
        self.stdout.write(
            self.style.SUCCESS(f"  Created weekly check task: {weekly_task_name}")
        )

    def setup_generic_source_tasks(self, source: Source, variables, dry_run: bool, overwrite: bool):
        """Set up scheduled tasks for generic sources."""
        # Generic sources - daily at 7:00 AM UTC
        crontab_daily, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="7",
            day_of_week="*",
            day_of_month="*", 
            month_of_year="*",
        )

        for variable in variables:
            task_name = f"{source.name} Daily Pipeline - {variable.name}"
            task_path = "data_pipeline.tasks.full_pipeline"
            
            if dry_run:
                self.stdout.write(f"  Would create: {task_name}")
                continue

            # Check if task already exists
            existing_task = PeriodicTask.objects.filter(name=task_name).first()
            if existing_task:
                if overwrite:
                    existing_task.delete()
                    self.stdout.write(f"  Deleted existing task: {task_name}")
                else:
                    self.stdout.write(f"  Task already exists: {task_name}")
                    continue

            # Create the task
            PeriodicTask.objects.create(
                name=task_name,
                task=task_path,
                crontab=crontab_daily,
                args=[source.id, variable.id],
                description=f"Daily pipeline execution for {source.name} {variable.name}",
                enabled=True,
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"  Created task: {task_name}")
            )

    def print_current_tasks(self):
        """Print all current scheduled tasks."""
        tasks = PeriodicTask.objects.all().order_by("name")
        
        if not tasks.exists():
            self.stdout.write("No scheduled tasks found.")
            return

        self.stdout.write(f"\nCurrent scheduled tasks ({tasks.count()}):")
        for task in tasks:
            status = "Enabled" if task.enabled else "Disabled"
            schedule_info = ""
            
            if task.interval:
                schedule_info = f"Every {task.interval.every} {task.interval.period}"
            elif task.crontab:
                schedule_info = f"Cron: {task.crontab}"
            
            self.stdout.write(f"  - {task.name} ({status}) - {schedule_info}")
            if task.description:
                self.stdout.write(f"    {task.description}")