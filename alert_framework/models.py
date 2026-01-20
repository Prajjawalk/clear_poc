"""Data models for the alert framework."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django_celery_beat.models import PeriodicTask


class Detector(models.Model):
    """Configuration and metadata for detector plugins."""

    name = models.CharField(max_length=255, unique=True, help_text="Human-readable detector identifier")
    description = models.TextField(blank=True, help_text="Detailed description of what this detector analyzes")
    class_name = models.CharField(max_length=255, help_text="Python class reference for dynamic loading (e.g., 'ConflictSurgeDetector')")
    active = models.BooleanField(default=True, help_text="Enable/disable detector execution")
    configuration = models.JSONField(default=dict, blank=True, help_text="Detector-specific configuration parameters")
    schedule = models.ForeignKey(PeriodicTask, on_delete=models.SET_NULL, null=True, blank=True, help_text="Scheduled execution task (optional for manual-only detectors)")

    # Monitoring and performance metrics
    last_run = models.DateTimeField(null=True, blank=True, help_text="Timestamp of most recent execution")
    run_count = models.PositiveIntegerField(default=0, help_text="Total number of executions")
    detection_count = models.PositiveIntegerField(default=0, help_text="Total detections created (performance metric)")

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for Detector model."""

        ordering = ["name"]
        indexes = [
            models.Index(fields=["active", "name"]),
            models.Index(fields=["last_run"]),
            models.Index(fields=["active", "last_run"]),  # Composite index for filtering active detectors by last run
            models.Index(fields=["name"]),  # For search functionality
            models.Index(fields=["class_name"]),  # For filtering by detector type
        ]

    def __str__(self):
        return self.name

    @property
    def success_rate(self):
        """Calculate success rate based on execution statistics."""
        if self.run_count == 0:
            return None
        # Calculate based on successful detections vs total runs
        # A run is considered successful if it created at least one detection
        if self.detection_count == 0:
            return 0.0
        # Estimate: runs that produce detections are successful
        # If avg detections per run >= 1, consider high success rate
        avg_detections_per_run = self.detection_count / self.run_count
        if avg_detections_per_run >= 1.0:
            return 1.0
        else:
            # Scale success rate based on detection frequency
            return avg_detections_per_run

    @property
    def average_detections_per_run(self):
        """Calculate average detections per run."""
        if self.run_count == 0:
            return 0
        return self.detection_count / self.run_count


class Detection(models.Model):
    """Individual detection results from detector analysis."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processed", "Processed"),
        ("dismissed", "Dismissed"),
    ]

    detector = models.ForeignKey(Detector, on_delete=models.CASCADE, related_name="detections", help_text="Detector that created this detection")
    title = models.CharField(max_length=255, help_text="Detection title/name for identification")
    detection_timestamp = models.DateTimeField(help_text="When the detected event/condition occurred")
    confidence_score = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)], help_text="Detection confidence score (0-1)")
    shock_type = models.ForeignKey(
        "alerts.ShockType",  # Reference to existing alerts app
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Shock type categorization",
    )
    locations = models.ManyToManyField("location.Location", blank=True, help_text="Affected locations")
    detection_data = models.JSONField(default=dict, help_text="Detector-specific data and context")

    # Processing status and workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", help_text="Processing status")
    alert = models.ForeignKey(
        "alerts.Alert",  # Reference to existing alerts app
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Generated alert (null if not processed)",
    )
    duplicate_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="duplicates", help_text="Reference to original detection if this is a duplicate"
    )

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True, help_text="When detection was created")
    processed_at = models.DateTimeField(null=True, blank=True, help_text="When detection was processed/dismissed")

    class Meta:
        """Meta configuration for Detection model."""

        ordering = ["-detection_timestamp", "-created_at"]
        indexes = [
            models.Index(fields=["detector", "status", "created_at"]),
            models.Index(fields=["detection_timestamp"]),
            models.Index(fields=["shock_type"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["detector", "detection_timestamp"]),  # For detector-specific detection queries
            models.Index(fields=["status", "detection_timestamp"]),  # For status-based time filtering
            models.Index(fields=["confidence_score"]),  # For confidence filtering
            models.Index(fields=["duplicate_of"]),  # For duplicate detection queries
            models.Index(fields=["processed_at"]),  # For processing time queries
            models.Index(fields=["title"]),  # For search functionality
        ]
        # Prevent duplicate detections for same detector/time/title (but allow different titles at same time)
        constraints = [
            models.UniqueConstraint(
                fields=["detector", "detection_timestamp", "title"], name="unique_detector_timestamp_title_alert_framework", condition=models.Q(duplicate_of__isnull=True)
            ),
        ]

    def __str__(self):
        return f"{self.detector.name} - {self.detection_timestamp.strftime('%Y-%m-%d %H:%M')}"

    @property
    def is_duplicate(self):
        """Check if this detection is marked as duplicate."""
        return self.duplicate_of is not None

    @property
    def processing_duration(self):
        """Calculate time between creation and processing."""
        if not self.processed_at:
            return None
        return self.processed_at - self.created_at


    @property
    def source_data_point(self):
        """Get the source data point (VariableData) that triggered this detection.

        Returns:
            VariableData instance or None
        """
        from data_pipeline.models import Variable, VariableData

        if not self.detection_data:
            return None

        detection_data = self.detection_data
        variable_code = detection_data.get("variable_code")
        start_date = detection_data.get("start_date")
        location_name = detection_data.get("location_name")

        if not all([variable_code, start_date]):
            return None

        try:
            variable = Variable.objects.get(code=variable_code)
            query = VariableData.objects.filter(variable=variable, start_date=start_date)
            if location_name:
                query = query.filter(gid__name=location_name)
            return query.first()
        except (Variable.DoesNotExist, Exception):
            return None

    def mark_processed(self, alert=None):
        """Mark detection as processed."""
        self.status = "processed"
        self.processed_at = timezone.now()
        if alert:
            self.alert = alert
        self.save(update_fields=["status", "processed_at", "alert"])

    def mark_dismissed(self):
        """Mark detection as dismissed without alert generation."""
        self.status = "dismissed"
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at"])

    def mark_duplicate(self, original_detection):
        """Mark this detection as duplicate of another."""
        self.duplicate_of = original_detection
        self.status = "dismissed"
        self.processed_at = timezone.now()
        self.save(update_fields=["duplicate_of", "status", "processed_at"])


class AlertTemplate(models.Model):
    """Multilingual message templates for alert generation."""

    name = models.CharField(max_length=255, unique=True, help_text="Template identifier")
    shock_type = models.ForeignKey(
        "alerts.ShockType",  # Reference to existing alerts app
        on_delete=models.CASCADE,
        related_name="alert_templates",
        help_text="Associated shock type",
    )
    title = models.CharField(max_length=255, help_text="Alert title template")
    text = models.TextField(help_text="Alert body template")
    variables = models.JSONField(default=dict, help_text="Documentation of available template variables")
    active = models.BooleanField(default=True, help_text="Template availability flag")
    detector_type = models.CharField(max_length=255, blank=True, help_text="Optional filter for specific detector types")

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for AlertTemplate model."""

        ordering = ["shock_type__name", "name"]
        indexes = [
            models.Index(fields=["shock_type", "active"]),
            models.Index(fields=["name"]),
            models.Index(fields=["active", "shock_type"]),  # For filtering active templates by shock type
            models.Index(fields=["detector_type"]),  # For detector-specific template queries
        ]

    def __str__(self):
        return f"{self.shock_type.name} - {self.name}"

    def render(self, context_data):
        """Render template with provided context data.

        Args:
            context_data: Dictionary containing template variables

        Returns:
            dict: Rendered title and text
        """
        from django.template import Context, Template

        title_template = Template(self.title)
        text_template = Template(self.text)
        context = Context(context_data)

        return {"title": title_template.render(context), "text": text_template.render(context)}


class PublishedAlert(models.Model):
    """Track alerts published to external systems."""

    # Publication status choices
    PUBLICATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("published", "Published"),
        ("failed", "Failed"),
        ("updated", "Updated"),
        ("cancelled", "Cancelled"),
    ]

    detection = models.ForeignKey(
        Detection,
        on_delete=models.CASCADE,
        related_name="published_alerts",
        help_text="Source detection for this alert",
    )
    template = models.ForeignKey(
        AlertTemplate,
        on_delete=models.CASCADE,
        related_name="published_alerts",
        help_text="Template used for alert formatting",
    )
    api_name = models.CharField(max_length=100, help_text="Name of the external API system")
    external_id = models.CharField(max_length=255, blank=True, help_text="Alert ID in external system")
    language = models.CharField(max_length=10, default="en", help_text="Language used for alert content")
    status = models.CharField(
        max_length=20,
        choices=PUBLICATION_STATUS_CHOICES,
        default="pending",
        help_text="Publication status",
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="When alert was successfully published")
    last_updated = models.DateTimeField(null=True, blank=True, help_text="When alert was last updated in external system")
    cancelled_at = models.DateTimeField(null=True, blank=True, help_text="When alert was cancelled")
    cancellation_reason = models.TextField(blank=True, help_text="Reason for cancellation")

    # Publication metadata
    publication_metadata = models.JSONField(default=dict, blank=True, help_text="Response data from external API")
    error_message = models.TextField(blank=True, help_text="Error details if publication failed")
    retry_count = models.PositiveIntegerField(default=0, help_text="Number of publication retry attempts")

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for PublishedAlert model."""

        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["detection", "api_name"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["external_id"]),
            models.Index(fields=["status", "published_at"]),  # For status-based time queries
            models.Index(fields=["api_name", "status"]),  # For API-specific status filtering
            models.Index(fields=["retry_count"]),  # For retry logic queries
        ]
        unique_together = [["detection", "api_name", "language"]]

    def __str__(self):
        return f"Alert {self.external_id or 'pending'} ({self.api_name})"

    def mark_published(self, external_id: str, response_data: dict = None):
        """Mark alert as successfully published."""
        self.external_id = external_id
        self.status = "published"
        self.published_at = timezone.now()
        if response_data:
            self.publication_metadata = response_data
        self.save()

    def mark_failed(self, error_message: str):
        """Mark alert publication as failed."""
        self.status = "failed"
        self.error_message = error_message
        self.retry_count += 1
        self.save()

    def mark_updated(self, response_data: dict = None):
        """Mark alert as updated in external system."""
        self.status = "updated"
        self.last_updated = timezone.now()
        if response_data:
            self.publication_metadata.update(response_data)
        self.save()

    def mark_cancelled(self, reason: str = ""):
        """Mark alert as cancelled."""
        self.status = "cancelled"
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save()
