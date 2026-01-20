"""Task monitoring models for Celery task execution tracking."""

from django.db import models


class TaskType(models.Model):
    """Types of tasks that can be executed."""

    name = models.CharField(max_length=255, unique=True, help_text="Name of the task type (e.g., 'retrieval', 'processing')")

    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        """Meta configuration for TaskType model."""

        ordering = ["name"]

    def __str__(self):
        return self.name


class TaskExecution(models.Model):
    """Execution tracking for individual Celery tasks."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("started", "Started"),
        ("success", "Success"),
        ("failure", "Failure"),
        ("retry", "Retry"),
        ("revoked", "Revoked"),
    ]

    task_id = models.CharField(max_length=255, unique=True, help_text="Unique Celery task ID")
    task_type = models.ForeignKey(TaskType, on_delete=models.PROTECT, related_name="executions", help_text="Type of task being executed")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", help_text="Current status of the task execution")
    started_at = models.DateTimeField(null=True, blank=True, help_text="When the task started execution")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="When the task completed (success or failure)")
    result = models.JSONField(null=True, blank=True, help_text="Task result data (success case)")
    error_message = models.TextField(blank=True, help_text="Error message if task failed")
    retry_count = models.IntegerField(default=0, help_text="Number of times this task has been retried")
    max_retries = models.IntegerField(default=3, help_text="Maximum number of retries allowed")
    arg1 = models.BigIntegerField(null=True, blank=True, help_text="First argument/parameter for the task (e.g., source ID)")
    source = models.ForeignKey("data_pipeline.Source", on_delete=models.CASCADE, null=True, blank=True, help_text="Related data pipeline source")
    variable = models.ForeignKey("data_pipeline.Variable", on_delete=models.CASCADE, null=True, blank=True, help_text="Related data pipeline variable")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for TaskExecution model."""

        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task_id"]),
            models.Index(fields=["task_type", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["source", "task_type"]),
            models.Index(fields=["variable", "task_type"]),
        ]

    def __str__(self):
        return f"{self.task_type.name} - {self.task_id} ({self.status})"

    @property
    def duration_seconds(self):
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_completed(self):
        """Check if task has completed (success or failure)."""
        return self.status in ["success", "failure"]

    @property
    def can_retry(self):
        """Check if task can be retried."""
        return self.status == "failure" and self.retry_count < self.max_retries


class TaskLog(models.Model):
    """Log entries for task execution tracking."""

    LEVEL_CHOICES = [
        (10, "DEBUG"),
        (20, "INFO"),
        (30, "WARNING"),
        (40, "ERROR"),
        (50, "CRITICAL"),
    ]

    task_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Celery task ID this log entry belongs to"
    )
    level = models.IntegerField(
        choices=LEVEL_CHOICES,
        default=20,
        help_text="Log level (10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL)"
    )
    level_name = models.CharField(
        max_length=10,
        default="INFO",
        help_text="Human-readable log level name"
    )
    message = models.TextField(help_text="Log message content")
    module = models.CharField(
        max_length=255,
        blank=True,
        help_text="Python module that generated the log"
    )
    function_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Function name that generated the log"
    )
    line_number = models.IntegerField(
        null=True,
        blank=True,
        help_text="Line number where log was generated"
    )
    thread = models.CharField(
        max_length=100,
        blank=True,
        help_text="Thread ID/name"
    )
    process = models.CharField(
        max_length=100,
        blank=True,
        help_text="Process ID/name"
    )
    extra_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Additional structured data from the log record"
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this log entry was created"
    )

    class Meta:
        """Meta configuration for TaskLog model."""

        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["task_id", "timestamp"]),
            models.Index(fields=["task_id", "level"]),
            models.Index(fields=["level", "timestamp"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"{self.timestamp} [{self.level_name}] {self.task_id}: {self.message[:100]}"

    @property
    def level_color(self):
        """Return Bootstrap color class for the log level."""
        level_colors = {
            10: "secondary",  # DEBUG
            20: "info",       # INFO
            30: "warning",    # WARNING
            40: "danger",     # ERROR
            50: "danger",     # CRITICAL
        }
        return level_colors.get(self.level, "secondary")

    @property
    def level_icon(self):
        """Return Bootstrap icon for the log level."""
        level_icons = {
            10: "bug",           # DEBUG
            20: "info-circle",   # INFO
            30: "exclamation-triangle",  # WARNING
            40: "x-circle",      # ERROR
            50: "x-octagon",     # CRITICAL
        }
        return level_icons.get(self.level, "info-circle")
