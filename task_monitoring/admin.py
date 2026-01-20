"""Admin interface for task monitoring models."""

from django.contrib import admin
from django.utils.html import format_html
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
from django_celery_beat.models import PeriodicTask
from modeltranslation.admin import TranslationAdmin

from .models import TaskExecution, TaskType


@admin.register(TaskType)
class TaskTypeAdmin(TranslationAdmin):
    """Admin interface for TaskType model."""

    list_display = ["name", "execution_count", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]

    def execution_count(self, obj):
        """Display count of executions for this task type."""
        return obj.executions.count()

    execution_count.short_description = "Executions"


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    """Admin interface for TaskExecution model."""

    list_display = ["task_id_short", "task_type", "status_display", "duration_display", "retry_count", "created_at", "completed_at"]
    list_filter = ["task_type", "status", "created_at", "completed_at", "source", "variable"]
    search_fields = ["task_id", "task_type__name", "error_message", "source__name", "variable__name"]
    readonly_fields = ["task_id", "duration_seconds", "is_completed", "can_retry", "created_at", "updated_at"]

    fieldsets = (
        ("Task Information", {"fields": ("task_id", "task_type", "status", "arg1")}),
        ("Timing", {"fields": ("started_at", "completed_at", "duration_seconds")}),
        ("Results", {"fields": ("result", "error_message")}),
        ("Retry Information", {"fields": ("retry_count", "max_retries", "can_retry")}),
        ("Related Objects", {"fields": ("source", "variable"), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("is_completed", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def task_id_short(self, obj):
        """Display shortened task ID."""
        return obj.task_id[:8] + "..." if len(obj.task_id) > 8 else obj.task_id

    task_id_short.short_description = "Task ID"

    def status_display(self, obj):
        """Display status with color coding."""
        colors = {"pending": "orange", "started": "blue", "success": "green", "failure": "red", "retry": "orange", "revoked": "gray"}
        color = colors.get(obj.status, "black")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())

    status_display.short_description = "Status"

    def duration_display(self, obj):
        """Display execution duration in human-readable format."""
        duration = obj.duration_seconds
        if duration is None:
            return "-"

        if duration < 60:
            return f"{duration:.1f}s"
        elif duration < 3600:
            return f"{duration / 60:.1f}m"
        else:
            return f"{duration / 3600:.1f}h"

    duration_display.short_description = "Duration"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("task_type", "source", "variable")


# Unregister the default PeriodicTask admin and register our custom one
admin.site.unregister(PeriodicTask)


@admin.register(PeriodicTask)
class PeriodicTaskAdmin(BasePeriodicTaskAdmin):
    """Custom admin interface for PeriodicTask with enhanced features."""

    list_display = [
        "name",
        "task",
        "enabled",
        "interval",
        "crontab",
        "solar",
        "last_run_at",
        "next_run_display",
        "total_run_count",
    ]

    list_filter = [
        "enabled",
        "task",
        "interval",
        "crontab",
        "solar",
        "last_run_at",
    ]

    search_fields = ["name", "task", "description"]

    readonly_fields = ["last_run_at", "total_run_count", "date_changed"]

    def next_run_display(self, obj):
        """Display next run time in a readable format."""
        if hasattr(obj, "schedule") and obj.schedule:
            try:
                from django_celery_beat.utils import make_aware
                from datetime import datetime

                next_run = obj.schedule.remaining_estimate(make_aware(datetime.now()))
                if next_run:
                    total_seconds = int(next_run.total_seconds())
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    if hours > 0:
                        return f"{hours}h {minutes}m"
                    elif minutes > 0:
                        return f"{minutes}m {seconds}s"
                    else:
                        return f"{seconds}s"
            except Exception:
                pass
        return "-"

    next_run_display.short_description = "Next Run In"
