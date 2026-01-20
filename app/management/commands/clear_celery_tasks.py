"""Management command to clear Celery task queues."""

from django.core.management.base import BaseCommand, CommandError
from celery import current_app


class Command(BaseCommand):
    """Management command for clearing Celery task queues."""

    help = "Clear Celery task queues and stop running tasks"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--queue",
            type=str,
            help="Clear specific queue only (e.g., 'celery', 'data_pipeline')"
        )
        
        parser.add_argument(
            "--pending",
            action="store_true",
            help="Clear only pending/queued tasks (default: clear all)"
        )
        
        parser.add_argument(
            "--active",
            action="store_true", 
            help="Revoke active/running tasks"
        )
        
        parser.add_argument(
            "--scheduled",
            action="store_true",
            help="Disable scheduled tasks (django-celery-beat)"
        )
        
        parser.add_argument(
            "--all",
            action="store_true",
            help="Clear everything (pending, active, scheduled)"
        )
        
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force clear without confirmation prompt"
        )
        
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be cleared without actually clearing"
        )

    def handle(self, *args, **options):
        """Handle command execution."""
        try:
            # Determine what to clear
            clear_pending = options.get("pending") or options.get("all") or (not any([
                options.get("pending"), options.get("active"), options.get("scheduled")
            ]))
            clear_active = options.get("active") or options.get("all")
            clear_scheduled = options.get("scheduled") or options.get("all")
            
            queue_filter = options.get("queue")
            force = options.get("force")
            dry_run = options.get("dry_run")
            
            # Get current task state
            inspect = current_app.control.inspect()
            
            # Count tasks to be affected
            counts = self._count_tasks(inspect, queue_filter, clear_pending, clear_active, clear_scheduled)
            
            # Display what will be cleared
            self._display_clear_summary(counts, queue_filter, clear_pending, clear_active, clear_scheduled)
            
            if dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN: No tasks were actually cleared"))
                return
            
            # Confirmation prompt unless forced
            if not force and (counts["pending"] + counts["active"] + counts["scheduled"] > 0):
                confirm = input("Are you sure you want to clear these tasks? [y/N]: ")
                if confirm.lower() not in ['y', 'yes']:
                    self.stdout.write("Operation cancelled")
                    return
            
            # Clear tasks
            cleared_counts = {"pending": 0, "active": 0, "scheduled": 0}
            
            if clear_pending and counts["pending"] > 0:
                cleared_counts["pending"] = self._clear_pending_tasks(inspect, queue_filter)
            
            if clear_active and counts["active"] > 0:
                cleared_counts["active"] = self._clear_active_tasks(inspect, queue_filter)
            
            if clear_scheduled and counts["scheduled"] > 0:
                cleared_counts["scheduled"] = self._clear_scheduled_tasks()
            
            # Display results
            self._display_clear_results(cleared_counts)
            
        except Exception as e:
            raise CommandError(f"Failed to clear Celery tasks: {e}")

    def _count_tasks(self, inspect, queue_filter=None, count_pending=True, count_active=True, count_scheduled=True):
        """Count tasks that would be affected by clearing."""
        counts = {"pending": 0, "active": 0, "scheduled": 0}
        
        try:
            if count_pending:
                # Count reserved and scheduled tasks
                reserved = inspect.reserved() or {}
                scheduled = inspect.scheduled() or {}
                
                for worker_name, tasks in reserved.items():
                    for task in tasks:
                        if not queue_filter or task.get("delivery_info", {}).get("routing_key") == queue_filter:
                            counts["pending"] += 1
                
                for worker_name, tasks in scheduled.items():
                    for task in tasks:
                        if not queue_filter or task.get("delivery_info", {}).get("routing_key") == queue_filter:
                            counts["pending"] += 1
            
            if count_active:
                # Count active tasks
                active = inspect.active() or {}
                for worker_name, tasks in active.items():
                    for task in tasks:
                        if not queue_filter or task.get("delivery_info", {}).get("routing_key") == queue_filter:
                            counts["active"] += 1
            
            if count_scheduled:
                # Count scheduled tasks from django-celery-beat
                try:
                    from django_celery_beat.models import PeriodicTask
                    counts["scheduled"] = PeriodicTask.objects.filter(enabled=True).count()
                except ImportError:
                    counts["scheduled"] = 0
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to count tasks: {e}"))
        
        return counts

    def _display_clear_summary(self, counts, queue_filter, clear_pending, clear_active, clear_scheduled):
        """Display summary of what will be cleared."""
        self.stdout.write(self.style.SUCCESS("Celery Task Clear Summary"))
        self.stdout.write("=" * 50)
        
        if queue_filter:
            self.stdout.write(f"Queue filter: {queue_filter}")
        
        actions = []
        if clear_pending and counts["pending"] > 0:
            actions.append(f"Clear {counts['pending']} pending tasks")
        elif clear_pending:
            actions.append("Clear 0 pending tasks")
            
        if clear_active and counts["active"] > 0:
            actions.append(f"Revoke {counts['active']} active tasks")
        elif clear_active:
            actions.append("Revoke 0 active tasks")
            
        if clear_scheduled and counts["scheduled"] > 0:
            actions.append(f"Disable {counts['scheduled']} scheduled tasks")
        elif clear_scheduled:
            actions.append("Disable 0 scheduled tasks")
        
        for action in actions:
            self.stdout.write(f"  • {action}")
        
        total_affected = counts["pending"] + counts["active"] + counts["scheduled"]
        if total_affected == 0:
            self.stdout.write(self.style.SUCCESS("\nNo tasks to clear"))

    def _clear_pending_tasks(self, inspect, queue_filter=None):
        """Clear pending/queued tasks."""
        cleared_count = 0
        
        try:
            # Get task IDs to revoke
            task_ids = []
            
            # Get reserved tasks
            reserved = inspect.reserved() or {}
            for worker_name, tasks in reserved.items():
                for task in tasks:
                    if not queue_filter or task.get("delivery_info", {}).get("routing_key") == queue_filter:
                        task_ids.append(task.get("id"))
            
            # Get scheduled tasks
            scheduled = inspect.scheduled() or {}
            for worker_name, tasks in scheduled.items():
                for task in tasks:
                    if not queue_filter or task.get("delivery_info", {}).get("routing_key") == queue_filter:
                        task_ids.append(task.get("id"))
            
            # Revoke tasks
            if task_ids:
                current_app.control.revoke(task_ids, terminate=False)
                cleared_count = len(task_ids)
                self.stdout.write(self.style.SUCCESS(f"Revoked {cleared_count} pending tasks"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to clear pending tasks: {e}"))
        
        return cleared_count

    def _clear_active_tasks(self, inspect, queue_filter=None):
        """Clear active/running tasks."""
        cleared_count = 0
        
        try:
            # Get active task IDs
            task_ids = []
            active = inspect.active() or {}
            
            for worker_name, tasks in active.items():
                for task in tasks:
                    if not queue_filter or task.get("delivery_info", {}).get("routing_key") == queue_filter:
                        task_ids.append(task.get("id"))
            
            # Revoke active tasks with termination
            if task_ids:
                current_app.control.revoke(task_ids, terminate=True)
                cleared_count = len(task_ids)
                self.stdout.write(self.style.SUCCESS(f"Terminated {cleared_count} active tasks"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to clear active tasks: {e}"))
        
        return cleared_count

    def _clear_scheduled_tasks(self):
        """Clear scheduled tasks from django-celery-beat."""
        cleared_count = 0
        
        try:
            from django_celery_beat.models import PeriodicTask
            
            # Disable all scheduled tasks
            updated = PeriodicTask.objects.filter(enabled=True).update(enabled=False)
            cleared_count = updated
            
            if cleared_count > 0:
                self.stdout.write(self.style.SUCCESS(f"Disabled {cleared_count} scheduled tasks"))
            
        except ImportError:
            self.stdout.write(self.style.WARNING("django-celery-beat not installed, cannot clear scheduled tasks"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to clear scheduled tasks: {e}"))
        
        return cleared_count

    def _display_clear_results(self, cleared_counts):
        """Display results of clearing operation."""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Clear Operation Complete"))
        
        total_cleared = sum(cleared_counts.values())
        
        if total_cleared > 0:
            self.stdout.write(f"Total tasks affected: {total_cleared}")
            if cleared_counts["pending"] > 0:
                self.stdout.write(f"  • {cleared_counts['pending']} pending tasks revoked")
            if cleared_counts["active"] > 0:
                self.stdout.write(f"  • {cleared_counts['active']} active tasks terminated")
            if cleared_counts["scheduled"] > 0:
                self.stdout.write(f"  • {cleared_counts['scheduled']} scheduled tasks disabled")
        else:
            self.stdout.write("No tasks were cleared")
        
        self.stdout.write("\nRecommendation: Restart Celery workers to ensure clean state")