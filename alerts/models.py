"""Alert system models for public notification interface."""

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.template import Context, Template


class ShockType(models.Model):
    """Alert category/theme classification."""

    name = models.CharField(max_length=100, unique=True, help_text="Name of the shock type (e.g., Conflict, Natural disasters)")

    # Display configuration
    icon = models.CharField(max_length=10, default="📍", help_text="Icon/symbol to display for this shock type (emoji or symbol)")
    color = models.CharField(max_length=7, default="#6c757d", help_text="Hex color code for this shock type (e.g., #dc3545)")
    css_class = models.CharField(max_length=50, blank=True, help_text="CSS class name for this shock type (auto-generated from name if empty)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for ShockType model."""

        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Auto-generate CSS class from name if not provided."""
        if not self.css_class:
            # Convert name to lowercase, replace spaces with hyphens, remove special chars
            import re

            self.css_class = re.sub(r"[^a-z0-9-]", "", self.name.lower().replace(" ", "-"))
        super().save(*args, **kwargs)

    @property
    def background_css_class(self):
        """Get the CSS class for background styling (bg-{css_class})."""
        return f"bg-{self.css_class}"


class Subscription(models.Model):
    """User subscription preferences for alert notifications."""

    FREQUENCY_CHOICES = [
        ("immediate", "Immediate"),
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]

    METHOD_CHOICES = [
        ("email", "Email"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="User who owns this subscription")

    locations = models.ManyToManyField("location.Location", help_text="Locations user wants to receive alerts for (filtered at adm1 level)")

    shock_types = models.ManyToManyField(ShockType, help_text="Types of alerts user wants to receive")

    active = models.BooleanField(default=True, help_text="Whether this subscription is active")

    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="email", help_text="Delivery method for alerts")

    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default="immediate", help_text="How often to receive alert notifications")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for Subscription model."""

        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "active"]),
            models.Index(fields=["active", "frequency"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.method} ({self.frequency})"


class Alert(models.Model):
    """Core alert model containing notification content and metadata."""

    SEVERITY_CHOICES = [
        (1, "Low"),
        (2, "Moderate"),
        (3, "High"),
        (4, "Very High"),
        (5, "Critical"),
    ]

    title = models.CharField(max_length=255, help_text="Alert title/headline")
    text = models.TextField(help_text="Main alert content and details")
    shock_type = models.ForeignKey(ShockType, on_delete=models.PROTECT, help_text="Category/type of this alert")
    data_source = models.ForeignKey("data_pipeline.Source", on_delete=models.PROTECT, help_text="Data source that triggered this alert")
    shock_date = models.DateField(help_text="Date when the shock/event occurred")
    go_no_go = models.BooleanField(default=False, help_text="Whether this alert has been approved for distribution (GO=True)")
    go_no_go_date = models.DateTimeField(null=True, blank=True, help_text="When the go/no-go decision was made")
    valid_from = models.DateTimeField(help_text="When this alert becomes valid/active")
    valid_until = models.DateTimeField(help_text="When this alert expires")
    severity = models.IntegerField(choices=SEVERITY_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(5)], help_text="Alert severity level (1=Low, 5=Critical)")
    locations = models.ManyToManyField("location.Location", help_text="Geographic areas affected by this alert")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for Alert model."""

        ordering = ["-shock_date", "-created_at"]
        indexes = [
            models.Index(fields=["shock_type", "severity"]),
            models.Index(fields=["shock_date", "go_no_go"]),
            models.Index(fields=["valid_from", "valid_until"]),
            models.Index(fields=["go_no_go", "severity"]),
            # New indexes for common filter combinations
            models.Index(fields=["go_no_go", "valid_from", "valid_until"]),
            models.Index(fields=["shock_type", "go_no_go", "severity"]),
            models.Index(fields=["created_at", "go_no_go"]),  # For recent alerts
            models.Index(fields=["go_no_go", "shock_date", "created_at"]),  # For API ordering
        ]

    def __str__(self):
        return f"{self.title} ({self.shock_date})"

    @property
    def is_active(self):
        """Check if alert is currently active based on validity period."""
        from django.utils import timezone

        now = timezone.now()
        return self.valid_from <= now <= self.valid_until

    @property
    def severity_display(self):
        """Get human-readable severity level."""
        return dict(self.SEVERITY_CHOICES).get(self.severity, "Unknown")

    @property
    def average_rating(self):
        """Get average user rating for this alert."""
        from django.db.models import Avg

        result = self.useralert_set.filter(rating__isnull=False).aggregate(avg_rating=Avg("rating"))
        return result["avg_rating"]

    @property
    def rating_count(self):
        """Get total number of ratings for this alert."""
        return self.useralert_set.filter(rating__isnull=False).count()

    @property
    def is_flagged_false(self):
        """Check if any user has flagged this alert as false."""
        return self.useralert_set.filter(flag_false=True).exists()

    @property
    def is_flagged_incomplete(self):
        """Check if any user has flagged this alert as incomplete."""
        return self.useralert_set.filter(flag_incomplete=True).exists()

    @property
    def false_flag_count(self):
        """Get count of users who flagged this alert as false."""
        return self.useralert_set.filter(flag_false=True).count()

    @property
    def incomplete_flag_count(self):
        """Get count of users who flagged this alert as incomplete."""
        return self.useralert_set.filter(flag_incomplete=True).count()

    @property
    def source_detection(self):
        """Get the detection that generated this alert."""
        from alert_framework.models import Detection

        return Detection.objects.filter(alert=self).first()

    @property
    def source_detector(self):
        """Get the detector that generated this alert."""
        detection = self.source_detection
        return detection.detector if detection else None

    @property
    def detector_name(self):
        """Get the name of the detector that generated this alert."""
        detector = self.source_detector
        return detector.name if detector else None

    @property
    def detector_type(self):
        """Get the type/class of the detector that generated this alert."""
        detector = self.source_detector
        if detector:
            # Extract just the detector type name (e.g., "DataminrBertDetector" from "dataminr_bert_detector.DataminrBertDetector")
            class_name = detector.class_name
            if "." in class_name:
                return class_name.split(".")[-1]
            return class_name
        return None

    @property
    def source_data_point(self):
        """Get the source data point (VariableData) that triggered this alert."""
        from data_pipeline.models import Variable, VariableData

        detection = self.source_detection
        if not detection or not detection.detection_data:
            return None

        detection_data = detection.detection_data

        # Extract search criteria from detection data
        variable_code = detection_data.get("variable_code")
        start_date = detection_data.get("start_date")
        location_name = detection_data.get("location_name")

        if not all([variable_code, start_date]):
            return None

        try:
            variable = Variable.objects.get(code=variable_code)

            # Try to find matching data point
            query = VariableData.objects.filter(variable=variable, start_date=start_date)

            # Add location filter if available
            if location_name:
                query = query.filter(gid__name=location_name)

            return query.first()
        except (Variable.DoesNotExist, Exception):
            return None

    def get_all_comments(self):
        """Get all user comments for this alert."""
        return self.useralert_set.filter(comment__isnull=False, comment__gt="").select_related("user").order_by("-created_at")


class UserAlert(models.Model):
    """User-specific interactions with alerts (ratings, bookmarks, feedback)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="User who interacted with this alert")

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, help_text="Alert that was interacted with")

    received_at = models.DateTimeField(null=True, blank=True, help_text="When the user received this alert notification")

    read_at = models.DateTimeField(null=True, blank=True, help_text="When the user first viewed/read this alert")

    rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)], help_text="User's 1-5 star rating of alert accuracy")

    rating_at = models.DateTimeField(null=True, blank=True, help_text="When the user provided their rating")

    flag_false = models.BooleanField(default=False, help_text="User flagged this alert as false")

    flag_incomplete = models.BooleanField(default=False, help_text="User flagged this alert as incomplete")

    comment = models.TextField(blank=True, help_text="User's structured feedback/comment on this alert")

    bookmarked = models.BooleanField(default=False, help_text="User has bookmarked this alert")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for UserAlert model."""

        unique_together = ["user", "alert"]
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "bookmarked"]),
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["alert", "rating"]),
            models.Index(fields=["flag_false", "flag_incomplete"]),
            # New indexes for dashboard queries and API performance
            models.Index(fields=["user", "alert", "bookmarked"]),
            models.Index(fields=["user", "rating", "rating_at"]),
            models.Index(fields=["rating", "created_at"]),  # For community stats
        ]

    def __str__(self):
        return f"{self.user.username} - {self.alert.title}"

    @property
    def is_read(self):
        """Check if user has read this alert."""
        return self.read_at is not None

    @property
    def is_rated(self):
        """Check if user has rated this alert."""
        return self.rating is not None

    @property
    def is_flagged(self):
        """Check if user has flagged this alert."""
        return self.flag_false or self.flag_incomplete


class EmailTemplate(models.Model):
    """Database-stored email templates with translation support."""

    TEMPLATE_TYPES = [
        ("individual_alert", "Individual Alert"),
        ("daily_digest", "Daily Digest"),
        ("weekly_digest", "Weekly Digest"),
        ("monthly_digest", "Monthly Digest"),
        ("subscription_confirm", "Subscription Confirmation"),
        ("email_verification", "Email Verification"),
    ]

    name = models.CharField(max_length=50, choices=TEMPLATE_TYPES, unique=True, help_text="Template identifier")
    description = models.TextField(help_text="Template purpose and usage")

    # Subject line with translation support
    subject = models.CharField(max_length=255, help_text="Email subject line with variables like {{alert.title}}")

    # HTML content with translation support
    html_header = models.TextField(help_text="HTML content before main alert content")
    html_footer = models.TextField(help_text="HTML content after main alert content")
    html_wrapper = models.TextField(blank=True, help_text="Full HTML template with {{content}} placeholder")

    # Plain text content with translation support
    text_header = models.TextField(help_text="Text content before main alert content")
    text_footer = models.TextField(help_text="Text content after main alert content")
    text_wrapper = models.TextField(blank=True, help_text="Full text template with {{content}} placeholder")

    # Configuration
    active = models.BooleanField(default=True, help_text="Whether this template is active and can be used")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for EmailTemplate model."""

        ordering = ["name"]
        verbose_name = "Email Template"
        verbose_name_plural = "Email Templates"

    def __str__(self):
        return f"{self.get_name_display()} - {self.subject[:50]}"

    def render_html(self, context):
        """Render HTML version with Django template engine."""
        # Get translated fields based on user language
        user = context.get("user")
        lang = ""
        if user and hasattr(user, "profile"):
            lang = f"_{user.profile.preferred_language}"

        if self.html_wrapper:
            template_content = getattr(self, f"html_wrapper{lang}", self.html_wrapper)
            template = Template(template_content)
        else:
            header_content = getattr(self, f"html_header{lang}", self.html_header)
            footer_content = getattr(self, f"html_footer{lang}", self.html_footer)
            header = Template(header_content)
            footer = Template(footer_content)

            rendered_header = header.render(Context(context))
            rendered_footer = footer.render(Context(context))

            # If alert content needs to be inserted
            alert = context.get("alert")
            if alert:
                alert_html = f"""
                <div class="alert-content">
                    <h3>{alert.title}</h3>
                    <div>{alert.text}</div>
                </div>
                """
            else:
                alert_html = "{{content}}"

            full_content = f"{rendered_header}{alert_html}{rendered_footer}"
            return full_content

        return template.render(Context(context))

    def render_text(self, context):
        """Render plain text version with Django template engine."""
        # Get translated fields based on user language
        user = context.get("user")
        lang = ""
        if user and hasattr(user, "profile"):
            lang = f"_{user.profile.preferred_language}"

        if self.text_wrapper:
            template_content = getattr(self, f"text_wrapper{lang}", self.text_wrapper)
            template = Template(template_content)
        else:
            header_content = getattr(self, f"text_header{lang}", self.text_header)
            footer_content = getattr(self, f"text_footer{lang}", self.text_footer)
            header = Template(header_content)
            footer = Template(footer_content)

            rendered_header = header.render(Context(context))
            rendered_footer = footer.render(Context(context))

            # If alert content needs to be inserted
            alert = context.get("alert")
            if alert:
                alert_text = f"\n{alert.title}\n\n{alert.text}\n"
            else:
                alert_text = "{{content}}"

            full_content = f"{rendered_header}{alert_text}{rendered_footer}"
            return full_content

        return template.render(Context(context))

    def get_subject(self, context):
        """Get rendered subject line with proper language."""
        user = context.get("user")
        lang = ""
        if user and hasattr(user, "profile"):
            lang = f"_{user.profile.preferred_language}"

        subject_content = getattr(self, f"subject{lang}", self.subject)
        subject_template = Template(subject_content)
        return subject_template.render(Context(context))
