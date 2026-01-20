"""Views for scheduled task management."""

import json
from datetime import datetime

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

from data_pipeline.models import Source, Variable

from .models import TaskExecution, TaskType
from .utils import format_time_until, get_next_run_time, get_readable_schedule


class TaskExecutionListView(LoginRequiredMixin, ListView):
    """List view for task executions with filtering and pagination."""

    model = TaskExecution
    template_name = "task_monitoring/task_execution_list.html"
    context_object_name = "executions"
    paginate_by = 20

    def get_queryset(self):
        """Get filtered queryset based on request parameters."""
        queryset = TaskExecution.objects.select_related("task_type", "source", "variable").order_by("-created_at")

        # Filter by status
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # Filter by task type
        task_type = self.request.GET.get("task_type")
        if task_type:
            queryset = queryset.filter(task_type__id=task_type)

        # Filter by source
        source = self.request.GET.get("source")
        if source:
            queryset = queryset.filter(source__id=source)

        # Filter by date range
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")

        if date_from:
            try:
                from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
                queryset = queryset.filter(created_at__date__gte=from_date)
            except ValueError:
                pass

        if date_to:
            try:
                to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
                queryset = queryset.filter(created_at__date__lte=to_date)
            except ValueError:
                pass

        # Search in task IDs and error messages
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(Q(task_id__icontains=search) | Q(error_message__icontains=search) | Q(source__name__icontains=search) | Q(variable__name__icontains=search))

        return queryset

    def get_context_data(self, **kwargs):
        """Add additional context for the template."""
        context = super().get_context_data(**kwargs)

        # Add filter options
        context["task_types"] = TaskType.objects.all()
        context["sources"] = Source.objects.all()
        context["status_choices"] = TaskExecution.STATUS_CHOICES

        # Preserve current filters
        context["current_filters"] = {
            "status": self.request.GET.get("status", ""),
            "task_type": self.request.GET.get("task_type", ""),
            "source": self.request.GET.get("source", ""),
            "date_from": self.request.GET.get("date_from", ""),
            "date_to": self.request.GET.get("date_to", ""),
            "search": self.request.GET.get("search", ""),
        }

        return context


@staff_member_required
def scheduled_tasks_list(request):
    """List all scheduled tasks with management capabilities."""
    # Get all periodic tasks with related schedules
    tasks = PeriodicTask.objects.select_related("interval", "crontab", "solar").order_by("name")

    # Filter by enabled status
    enabled = request.GET.get("enabled")
    if enabled:
        tasks = tasks.filter(enabled=enabled.lower() == "true")

    # Search by name or task
    search = request.GET.get("search")
    if search:
        tasks = tasks.filter(Q(name__icontains=search) | Q(task__icontains=search))

    # Pagination
    paginator = Paginator(tasks, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Add readable schedule and next run time to each task
    for task in page_obj.object_list:
        task.readable_schedule = get_readable_schedule(task)
        task.next_run = get_next_run_time(task)
        task.time_until_next = format_time_until(task.next_run)

    context = {
        "page_obj": page_obj,
        "tasks": page_obj.object_list,
        "current_filters": {
            "enabled": request.GET.get("enabled", ""),
            "search": request.GET.get("search", ""),
        },
    }

    return render(request, "task_monitoring/scheduled_tasks_list.html", context)


@staff_member_required
def scheduled_task_detail(request, task_id):
    """Show details of a specific scheduled task."""
    task = get_object_or_404(PeriodicTask, id=task_id)

    # Add readable schedule and next run time
    task.readable_schedule = get_readable_schedule(task)
    task.next_run = get_next_run_time(task)
    task.time_until_next = format_time_until(task.next_run)

    # Get recent executions for this task
    recent_executions = (
        TaskExecution.objects.filter(
            task_type__name=task.task.split(".")[-1]  # Extract task name from full path
        )
        .select_related("task_type", "source", "variable")
        .order_by("-created_at")[:10]
    )

    context = {
        "task": task,
        "recent_executions": recent_executions,
    }

    return render(request, "task_monitoring/scheduled_task_detail.html", context)


@staff_member_required
def create_scheduled_task(request):
    """Create a new scheduled task."""
    if request.method == "POST":
        try:
            name = request.POST.get("name")
            task = request.POST.get("task")
            description = request.POST.get("description", "")
            enabled = request.POST.get("enabled") == "on"

            # Parse schedule
            schedule_type = request.POST.get("schedule_type")

            if schedule_type == "interval":
                every = int(request.POST.get("every", 1))
                period = request.POST.get("period", "minutes")

                # Create or get interval schedule
                interval, created = IntervalSchedule.objects.get_or_create(every=every, period=period)

                # Create periodic task
                periodic_task = PeriodicTask.objects.create(
                    name=name,
                    task=task,
                    interval=interval,
                    description=description,
                    enabled=enabled,
                )

            elif schedule_type == "crontab":
                minute = request.POST.get("minute", "*")
                hour = request.POST.get("hour", "*")
                day_of_week = request.POST.get("day_of_week", "*")
                day_of_month = request.POST.get("day_of_month", "*")
                month_of_year = request.POST.get("month_of_year", "*")

                # Create or get crontab schedule
                crontab, created = CrontabSchedule.objects.get_or_create(
                    minute=minute,
                    hour=hour,
                    day_of_week=day_of_week,
                    day_of_month=day_of_month,
                    month_of_year=month_of_year,
                )

                # Create periodic task
                periodic_task = PeriodicTask.objects.create(
                    name=name,
                    task=task,
                    crontab=crontab,
                    description=description,
                    enabled=enabled,
                )

            # Handle task arguments if provided
            args = request.POST.get("args", "")
            kwargs = request.POST.get("kwargs", "")

            if args:
                try:
                    periodic_task.args = json.loads(args)
                except json.JSONDecodeError:
                    periodic_task.args = args

            if kwargs:
                try:
                    periodic_task.kwargs = json.loads(kwargs)
                except json.JSONDecodeError:
                    pass

            periodic_task.save()

            messages.success(request, f"Scheduled task '{name}' created successfully.")
            return redirect("task_monitoring:scheduled_tasks_list")

        except Exception as e:
            messages.error(request, f"Error creating scheduled task: {str(e)}")

    # Get available tasks from data_pipeline
    available_tasks = [
        "data_pipeline.tasks.retrieve_data",
        "data_pipeline.tasks.process_data",
        "data_pipeline.tasks.full_pipeline",
        "data_pipeline.tasks.update_task_statistics",
    ]

    # Get sources and variables for dropdown
    sources = Source.objects.all()
    variables = Variable.objects.select_related("source").all()

    context = {
        "available_tasks": available_tasks,
        "sources": sources,
        "variables": variables,
    }

    return render(request, "task_monitoring/create_scheduled_task.html", context)


@staff_member_required
@require_POST
def toggle_scheduled_task(request, task_id):
    """Toggle enabled/disabled status of a scheduled task."""
    task = get_object_or_404(PeriodicTask, id=task_id)
    task.enabled = not task.enabled
    task.save()

    status = "enabled" if task.enabled else "disabled"
    messages.success(request, f"Task '{task.name}' has been {status}.")

    return redirect("task_monitoring:scheduled_tasks_list")


@staff_member_required
@require_POST
def delete_scheduled_task(request, task_id):
    """Delete a scheduled task."""
    task = get_object_or_404(PeriodicTask, id=task_id)
    task_name = task.name
    task.delete()

    messages.success(request, f"Scheduled task '{task_name}' has been deleted.")
    return redirect("task_monitoring:scheduled_tasks_list")


@staff_member_required
@require_POST
def run_scheduled_task(request, task_id):
    """Manually run a scheduled task."""
    task = get_object_or_404(PeriodicTask, id=task_id)

    try:
        from celery import current_app

        # Get task arguments - django-celery-beat stores them as JSON strings
        args = []
        kwargs = {}

        if task.args:
            if isinstance(task.args, str):
                try:
                    args = json.loads(task.args)
                except json.JSONDecodeError:
                    args = [task.args]  # Fallback to single argument
            else:
                args = task.args

        if task.kwargs:
            if isinstance(task.kwargs, str):
                try:
                    kwargs = json.loads(task.kwargs)
                except json.JSONDecodeError:
                    kwargs = {}
            else:
                kwargs = task.kwargs

        # Send task to Celery
        result = current_app.send_task(task.task, args=args, kwargs=kwargs)

        # Update last_run_at timestamp for manual runs
        from django.utils import timezone
        task.last_run_at = timezone.now()
        task.total_run_count += 1
        task.save(update_fields=['last_run_at', 'total_run_count'])

        messages.success(request, f"Task '{task.name}' has been queued for execution. Task ID: {result.id[:8]}...")

    except Exception as e:
        messages.error(request, f"Error running task: {str(e)}")

    # Redirect back to the referring page or task list as fallback
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if next_url and any(url_part in next_url for url_part in ["/tasks/scheduled/", "/tasks/"]):
        return redirect(next_url)
    else:
        return redirect("task_monitoring:scheduled_tasks_list")
