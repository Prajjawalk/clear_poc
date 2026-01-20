"""Management command to inspect Celery task queues and workers."""

import json

from celery import current_app
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Management command for inspecting Celery task queues and workers."""

    help = "Inspect Celery task queues, workers, and pending tasks"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--queue",
            type=str,
            help="Inspect specific queue only (e.g., 'celery', 'data_pipeline')",
        )

        parser.add_argument(
            "--workers",
            action="store_true",
            help="Show active workers information",
        )

        parser.add_argument(
            "--pending",
            action="store_true",
            help="Show pending/queued tasks",
        )

        parser.add_argument(
            "--active",
            action="store_true",
            help="Show currently running tasks",
        )

        parser.add_argument(
            "--scheduled",
            action="store_true",
            help="Show scheduled tasks (django-celery-beat)",
        )

        parser.add_argument(
            "--all",
            action="store_true",
            help="Show all information (workers, pending, active, scheduled)",
        )

        parser.add_argument(
            "--json",
            action="store_true",
            help="Output in JSON format",
        )

    def handle(self, *args, **options):
        """Handle command execution."""
        try:
            inspect = current_app.control.inspect()

            # Determine what to show
            show_workers = options.get("workers") or options.get("all")
            show_pending = options.get("pending") or options.get("all")
            show_active = options.get("active") or options.get("all")
            show_scheduled = options.get("scheduled") or options.get("all")

            # If nothing specified, show basic info
            if not any([show_workers, show_pending, show_active, show_scheduled]):
                show_workers = True
                show_pending = True
                show_active = True

            queue_filter = options.get("queue")
            json_output = options.get("json")

            result = {}

            if show_workers:
                result["workers"] = self._get_workers_info(inspect, json_output)

            if show_pending:
                result["pending_tasks"] = self._get_pending_tasks(inspect, queue_filter, json_output)

            if show_active:
                result["active_tasks"] = self._get_active_tasks(inspect, queue_filter, json_output)

            if show_scheduled:
                result["scheduled_tasks"] = self._get_scheduled_tasks(json_output)

            # Output results
            if json_output:
                self.stdout.write(json.dumps(result, indent=2, default=str))
            else:
                self._display_results(result)

        except Exception as e:
            raise CommandError(f"Failed to inspect Celery tasks: {e}")

    def _get_workers_info(self, inspect, json_output=False):
        """Get information about active workers."""
        try:
            stats = inspect.stats()
            active = inspect.active()

            if not stats:
                if not json_output:
                    self.stdout.write(self.style.WARNING("No active workers found"))
                return []

            workers_info = []
            for worker_name, worker_stats in stats.items():
                worker_info = {
                    "name": worker_name,
                    "status": "online",
                    "processes": worker_stats.get("pool", {}).get("processes", []),
                    "total_tasks": sum(worker_stats.get("total", {}).values()),
                    "active_tasks": len(active.get(worker_name, [])) if active else 0,
                    "load_average": worker_stats.get("rusage", {}).get("stime", 0),
                }
                workers_info.append(worker_info)

            if not json_output:
                self.stdout.write(self.style.SUCCESS("\nActive Workers:"))
                self.stdout.write("-" * 50)
                for worker in workers_info:
                    self.stdout.write(f"  {worker['name']}: {worker['active_tasks']} active tasks, {worker['total_tasks']} total processed")

            return workers_info

        except Exception as e:
            if not json_output:
                self.stdout.write(self.style.ERROR(f"Failed to get workers info: {e}"))
            return []

    def _get_pending_tasks(self, inspect, queue_filter=None, json_output=False):
        """Get information about pending/queued tasks."""
        try:
            reserved = inspect.reserved()
            scheduled = inspect.scheduled()

            pending_tasks = []

            # Process reserved tasks
            if reserved:
                for worker_name, tasks in reserved.items():
                    for task in tasks:
                        if queue_filter and task.get("delivery_info", {}).get("routing_key") != queue_filter:
                            continue
                        pending_tasks.append(
                            {
                                "worker": worker_name,
                                "task_id": task.get("id"),
                                "task_name": task.get("name"),
                                "queue": task.get("delivery_info", {}).get("routing_key"),
                                "status": "reserved",
                                "args": task.get("args"),
                                "kwargs": task.get("kwargs"),
                            }
                        )

            # Process scheduled tasks
            if scheduled:
                for worker_name, tasks in scheduled.items():
                    for task in tasks:
                        if queue_filter and task.get("delivery_info", {}).get("routing_key") != queue_filter:
                            continue
                        pending_tasks.append(
                            {
                                "worker": worker_name,
                                "task_id": task.get("id"),
                                "task_name": task.get("name"),
                                "queue": task.get("delivery_info", {}).get("routing_key"),
                                "status": "scheduled",
                                "eta": task.get("eta"),
                                "args": task.get("args"),
                                "kwargs": task.get("kwargs"),
                            }
                        )

            if not json_output:
                if pending_tasks:
                    self.stdout.write(self.style.SUCCESS(f"\nPending Tasks ({len(pending_tasks)}):"))
                    self.stdout.write("-" * 50)
                    for task in pending_tasks[:10]:  # Show first 10
                        queue_info = f" [{task['queue']}]" if task["queue"] else ""
                        self.stdout.write(f"  {task['task_name']}{queue_info} - {task['status']}")
                    if len(pending_tasks) > 10:
                        self.stdout.write(f"  ... and {len(pending_tasks) - 10} more")
                else:
                    self.stdout.write(self.style.SUCCESS("\nNo pending tasks found"))

            return pending_tasks

        except Exception as e:
            if not json_output:
                self.stdout.write(self.style.ERROR(f"Failed to get pending tasks: {e}"))
            return []

    def _get_active_tasks(self, inspect, queue_filter=None, json_output=False):
        """Get information about currently running tasks."""
        try:
            active = inspect.active()

            if not active:
                if not json_output:
                    self.stdout.write(self.style.SUCCESS("\nNo active tasks found"))
                return []

            active_tasks = []
            for worker_name, tasks in active.items():
                for task in tasks:
                    if queue_filter and task.get("delivery_info", {}).get("routing_key") != queue_filter:
                        continue
                    active_tasks.append(
                        {
                            "worker": worker_name,
                            "task_id": task.get("id"),
                            "task_name": task.get("name"),
                            "queue": task.get("delivery_info", {}).get("routing_key"),
                            "time_start": task.get("time_start"),
                            "args": task.get("args"),
                            "kwargs": task.get("kwargs"),
                        }
                    )

            if not json_output:
                if active_tasks:
                    self.stdout.write(self.style.SUCCESS(f"\nActive Tasks ({len(active_tasks)}):"))
                    self.stdout.write("-" * 50)
                    for task in active_tasks:
                        queue_info = f" [{task['queue']}]" if task["queue"] else ""
                        self.stdout.write(f"  {task['task_name']}{queue_info} - started at {task['time_start']}")
                else:
                    self.stdout.write(self.style.SUCCESS("\nNo active tasks found"))

            return active_tasks

        except Exception as e:
            if not json_output:
                self.stdout.write(self.style.ERROR(f"Failed to get active tasks: {e}"))
            return []

    def _get_scheduled_tasks(self, json_output=False):
        """Get information about scheduled tasks from django-celery-beat."""
        try:
            from django_celery_beat.models import PeriodicTask

            scheduled_tasks = []
            for task in PeriodicTask.objects.filter(enabled=True):
                scheduled_tasks.append(
                    {
                        "name": task.name,
                        "task": task.task,
                        "schedule": str(task.schedule),
                        "next_run": task.last_run_at,
                        "enabled": task.enabled,
                        "args": task.args,
                        "kwargs": task.kwargs,
                    }
                )

            if not json_output:
                if scheduled_tasks:
                    self.stdout.write(self.style.SUCCESS(f"\nScheduled Tasks ({len(scheduled_tasks)}):"))
                    self.stdout.write("-" * 50)
                    for task in scheduled_tasks:
                        self.stdout.write(f"  {task['name']} - {task['schedule']}")
                else:
                    self.stdout.write(self.style.SUCCESS("\nNo scheduled tasks found"))

            return scheduled_tasks

        except ImportError:
            if not json_output:
                self.stdout.write(self.style.WARNING("django-celery-beat not installed"))
            return []
        except Exception as e:
            if not json_output:
                self.stdout.write(self.style.ERROR(f"Failed to get scheduled tasks: {e}"))
            return []

    def _display_results(self, result):
        """Display results in human-readable format."""
        self.stdout.write(self.style.SUCCESS("Celery Task Inspection Results"))
        self.stdout.write("=" * 60)

        # Results are already displayed in individual methods
        # This is just a summary
        summary = []

        if "workers" in result:
            worker_count = len(result["workers"])
            summary.append(f"{worker_count} active workers")

        if "pending_tasks" in result:
            pending_count = len(result["pending_tasks"])
            summary.append(f"{pending_count} pending tasks")

        if "active_tasks" in result:
            active_count = len(result["active_tasks"])
            summary.append(f"{active_count} active tasks")

        if "scheduled_tasks" in result:
            scheduled_count = len(result["scheduled_tasks"])
            summary.append(f"{scheduled_count} scheduled tasks")

        if summary:
            self.stdout.write(f"\nSummary: {', '.join(summary)}")
