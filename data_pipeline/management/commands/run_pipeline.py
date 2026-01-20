"""Management command to run data pipeline tasks."""

import os

from django.core.management.base import BaseCommand, CommandError

from data_pipeline.models import Source, Variable
from data_pipeline.tasks import full_pipeline, process_data, retrieve_data


class Command(BaseCommand):
    """Management command for running data pipeline operations."""

    help = "Run data pipeline tasks for data retrieval and processing"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument("--source", type=str, help="Source name to process (if not specified, processes all sources)")

        parser.add_argument("--variable", type=str, help="Variable code to process (requires --source)")

        parser.add_argument("--task-type", type=str, choices=["retrieve", "process", "full"], default="full", help="Type of task to run (default: full)")

        parser.add_argument("--async", action="store_true", help="Run tasks asynchronously using Celery")

        parser.add_argument("--list-sources", action="store_true", help="List available sources and exit")

        parser.add_argument("--start-date", type=str, help="Start date for data retrieval (format: YYYY-MM-DD)")

        parser.add_argument("--end-date", type=str, help="End date for data retrieval (format: YYYY-MM-DD)")

    def handle(self, *args, **options):
        """Handle command execution."""
        if options["list_sources"]:
            self.list_sources()
            return

        source_name = options.get("source")
        variable_code = options.get("variable")
        task_type = options["task_type"]
        use_async = options.get("async", False)
        start_date = options.get("start_date")
        end_date = options.get("end_date")

        # Build kwargs for tasks
        task_kwargs = {}
        if start_date:
            task_kwargs["start_date"] = start_date
        if end_date:
            task_kwargs["end_date"] = end_date

        if source_name and source_name.lower() == "idmc" and not os.getenv("IDMC_API_KEY"):
            raise CommandError("IDMC_API_KEY environment variable not set. Please set it before running the pipeline for the IDMC source.")

        if source_name and source_name.lower() == "iom":
            if not os.getenv("IOM_API_KEY"):
                raise CommandError("IOM_API_KEY environment variable not set. Please set it before running the pipeline for the IOM source.")
            if not os.getenv("IOM_APP"):
                raise CommandError("IOM_APP environment variable not set. Please set it before running the pipeline for the IOM source.")

        try:
            if source_name:
                # Process specific source
                source = Source.objects.get(name__iexact=source_name)

                if variable_code:
                    # Process specific variable
                    variable = Variable.objects.get(code=variable_code, source=source)
                    self.run_tasks_for_variable(source, variable, task_type, use_async, task_kwargs)
                else:
                    # Process all variables for the source
                    self.run_tasks_for_source(source, task_type, use_async, task_kwargs)
            else:
                # Process all sources
                sources = Source.objects.all()
                for source in sources:
                    self.run_tasks_for_source(source, task_type, use_async, task_kwargs)

        except Source.DoesNotExist:
            raise CommandError(f"Source '{source_name}' not found")

        except Variable.DoesNotExist:
            raise CommandError(f"Variable '{variable_code}' not found for source '{source_name}'")

        except Exception as e:
            raise CommandError(f"Pipeline execution failed: {str(e)}")

    def list_sources(self):
        """List all available sources with their variables."""
        sources = Source.objects.prefetch_related("variables").all()

        if not sources.exists():
            self.stdout.write(self.style.WARNING("No sources found in database."))
            return

        self.stdout.write(self.style.SUCCESS("Available sources:"))

        for source in sources:
            self.stdout.write(f"\n{source.name} ({source.type})")
            self.stdout.write(f"  Class: {source.class_name}")

            variables = source.variables.all()
            if variables.exists():
                self.stdout.write("  Variables:")
                for variable in variables:
                    self.stdout.write(f"    - {variable.code}: {variable.name}")
            else:
                self.stdout.write("    No variables configured")

    def run_tasks_for_source(self, source: Source, task_type: str, use_async: bool, task_kwargs: dict = None):
        """Run tasks for all variables in a source."""
        self.stdout.write(f"\nProcessing source: {source.name}")

        variables = source.variables.all()
        if not variables.exists():
            self.stdout.write(self.style.WARNING(f"No variables found for source {source.name}"))
            return

        if task_kwargs is None:
            task_kwargs = {}

        for variable in variables:
            self.run_tasks_for_variable(source, variable, task_type, use_async, task_kwargs)

    def run_tasks_for_variable(self, source: Source, variable: Variable, task_type: str, use_async: bool, task_kwargs: dict = None):
        """Run tasks for a specific variable."""
        if task_kwargs is None:
            task_kwargs = {}

        # Display date range if specified
        date_info = ""
        if task_kwargs.get("start_date") or task_kwargs.get("end_date"):
            date_info = f" ({task_kwargs.get('start_date', '...')} to {task_kwargs.get('end_date', '...')})"

        self.stdout.write(f"  Processing variable: {variable.code}{date_info}")

        try:
            if use_async:
                # Run tasks asynchronously with Celery
                if task_type == "retrieve":
                    result = retrieve_data.delay(source.id, variable.id, **task_kwargs)
                    self.stdout.write(f"    Queued retrieval task: {result.id}")

                elif task_type == "process":
                    result = process_data.delay(source.id, variable.id, **task_kwargs)
                    self.stdout.write(f"    Queued processing task: {result.id}")

                elif task_type == "full":
                    result = full_pipeline.delay(source.id, variable.id, **task_kwargs)
                    self.stdout.write(f"    Queued full pipeline task: {result.id}")

            else:
                # Run tasks synchronously
                if task_type == "retrieve":
                    result = retrieve_data.apply(args=[source.id, variable.id], kwargs=task_kwargs)
                    self.print_result(result.result, "Retrieval")

                elif task_type == "process":
                    result = process_data.apply(args=[source.id, variable.id], kwargs=task_kwargs)
                    self.print_result(result.result, "Processing")

                elif task_type == "full":
                    result = full_pipeline.apply(args=[source.id, variable.id], kwargs=task_kwargs)
                    self.print_result(result.result, "Full pipeline")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    Failed: {str(e)}"))

    def print_result(self, result: dict, task_name: str):
        """Print task result in a readable format."""
        # For retrieval tasks, check 'successful_retrievals'
        if task_name == "Retrieval":
            overall_success = result and result.get("successful_retrievals", 0) > 0
        else:
            overall_success = result and result.get("success", False)

        if overall_success:
            self.stdout.write(self.style.SUCCESS(f"    {task_name}: SUCCESS"))

            # Print specific metrics based on task type
            if "successful_retrievals" in result:
                self.stdout.write(f"      Retrieved: {result['successful_retrievals']}")

            if "successful_processing" in result:
                self.stdout.write(f"      Processed: {result['successful_processing']}")

        else:
            self.stdout.write(self.style.ERROR(f"    {task_name}: FAILED"))

            if result and "message" in result:
                self.stdout.write(f"      Error: {result['message']}")
            elif result and "error" in result:
                self.stdout.write(f"      Error: {result['error']}")
            elif result and "variables" in result:
                for var_code, var_result in result.get("variables", {}).items():
                    if not var_result.get("success"):
                        self.stdout.write(f"      Variable '{var_code}': FAILED")
                        if "error" in var_result:
                            self.stdout.write(f"        Details: {var_result['error']}")
            else:
                self.stdout.write("      No detailed error message available.")
