"""Data pipeline models for managing data sources, variables, and processing."""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Source(models.Model):
    """Data provider configuration for third-party data sources."""

    TYPE_CHOICES = [
        ("api", "API"),
        ("web_scraping", "Web Scraping"),
        ("file_upload", "File Upload"),
        ("ftp", "FTP"),
        ("database", "Database"),
    ]

    name = models.CharField(max_length=255, help_text="Name of the data source (e.g., ACLED, UNHCR)")
    description = models.TextField(blank=True, help_text="Description of the data source")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, help_text="Type of data retrieval method")
    info_url = models.URLField(blank=True, help_text="URL with information about the data source")
    base_url = models.URLField(blank=True, help_text="Base URL for API or website")
    class_name = models.CharField(max_length=255, help_text="Python class name for data retrieval implementation")
    comment = models.TextField(blank=True, help_text="Additional notes about the source")
    is_active = models.BooleanField(default=True, help_text="Indicates if the source is currently active")
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        """Meta configuration for Source model."""

        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self):
        return self.name


class Variable(models.Model):
    """Source variables that contain raw data for processing."""

    PERIOD_CHOICES = [
        ("day", "Daily"),
        ("week", "Weekly"),
        ("month", "Monthly"),
        ("quarter", "Quarterly"),
        ("year", "Annual"),
        ("event", "Event-based"),
    ]

    TYPE_CHOICES = [
        ("quantitative", "Quantitative"),
        ("qualitative", "Qualitative"),
        ("textual", "Textual"),
        ("categorical", "Categorical"),
    ]

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="variables", help_text="Data source this variable belongs to")
    name = models.CharField(max_length=255, help_text="Human-readable name of the variable")
    code = models.CharField(max_length=100, help_text="Unique code for the variable (e.g., acled_fatalities)")
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES, help_text="Temporal frequency of the data")
    adm_level = models.IntegerField(validators=[MinValueValidator(0)], help_text="Administrative level (0=country, 1=admin1, etc.)")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, help_text="Type of data contained in this variable")
    unit = models.CharField(max_length=50, blank=True, help_text="Unit of measurement (e.g., 'events', 'persons', 'USD')")
    text = models.TextField(blank=True, help_text="Additional description of the variable")

    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        """Meta configuration for Variable model."""

        ordering = ["source__name", "name"]
        unique_together = [["source", "code"]]
        indexes = [
            models.Index(fields=["source", "code"]),
            models.Index(fields=["period", "adm_level"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self):
        return f"{self.source.name} - {self.name}"


class VariableData(models.Model):
    """Processed data from variables in standardized format.
    
    This model stores processed data with support for hierarchical relationships
    through the parent field, enabling tracking of derived data points.
    
    Examples:
    - Original raw data points have parent=None
    - Aggregated data points reference their source data via parent
    - Processed/transformed data points reference their original data via parent
    """

    variable = models.ForeignKey(Variable, on_delete=models.CASCADE, related_name="data_records", help_text="Variable this data belongs to")
    start_date = models.DateField(help_text="Start date of the data period")
    end_date = models.DateField(help_text="End date of the data period")
    period = models.CharField(max_length=20, choices=Variable.PERIOD_CHOICES, help_text="Period type of this data record")
    adm_level = models.ForeignKey("location.AdmLevel", on_delete=models.PROTECT, help_text="Administrative level of the location")
    gid = models.ForeignKey("location.Location", on_delete=models.PROTECT, null=True, blank=True, help_text="Geographic location identifier (null if location not matched)")
    original_location_text = models.TextField(blank=True, help_text="Original location text from source data (immutable)")
    unmatched_location = models.ForeignKey("location.UnmatchedLocation", on_delete=models.SET_NULL, null=True, blank=True, help_text="Reference to unmatched location record for reprocessing")
    value = models.FloatField(null=True, blank=True, help_text="Numeric value (for quantitative data)")
    text = models.TextField(blank=True, help_text="Text content (for qualitative/textual data)")
    raw_data = models.JSONField(null=True, blank=True, help_text="Original raw data from source (complete JSON record)")
    parent = models.ForeignKey(
        "self", 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name="derived_records", 
        help_text="Reference to original data point for derived data (e.g., aggregations, transformations)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for VariableData model."""

        ordering = ["-end_date", "gid__geo_id"]
        unique_together = [["variable", "start_date", "end_date", "gid"]]
        indexes = [
            models.Index(fields=["variable", "start_date", "end_date"]),
            models.Index(fields=["gid", "variable"]),
            models.Index(fields=["adm_level", "period"]),
            models.Index(fields=["end_date"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"{self.variable.code} - {self.gid.geo_id} ({self.start_date} to {self.end_date})"
    
    @property
    def is_original(self):
        """Check if this is original data (not derived from another record)."""
        return self.parent is None
    
    @property
    def is_derived(self):
        """Check if this is derived data (has a parent record)."""
        return self.parent is not None
    
    def get_lineage(self):
        """Get the full lineage of parent records leading to this data point.
        
        Returns:
            List[VariableData]: List of records from root parent to this record
        """
        lineage = []
        current = self
        
        while current:
            lineage.insert(0, current)  # Insert at beginning to maintain order
            current = current.parent
        
        return lineage
    
    def get_root_parent(self):
        """Get the original (root) parent record.
        
        Returns:
            VariableData: The original record that this data derives from
        """
        current = self
        while current.parent:
            current = current.parent
        return current


class TaskStatistics(models.Model):
    """Statistics for task execution performance."""

    date = models.DateField(unique=True, help_text="Date for these statistics")
    check_updates_count = models.IntegerField(default=0, help_text="Number of update check tasks")
    download_data_count = models.IntegerField(default=0, help_text="Number of data download tasks")
    process_data_count = models.IntegerField(default=0, help_text="Number of data processing tasks")
    full_pipeline_count = models.IntegerField(default=0, help_text="Number of full pipeline tasks")
    reprocess_data_count = models.IntegerField(default=0, help_text="Number of data reprocessing tasks")
    success_count = models.IntegerField(default=0, help_text="Number of successful task executions")
    failure_count = models.IntegerField(default=0, help_text="Number of failed task executions")
    retry_count = models.IntegerField(default=0, help_text="Number of task retries")
    avg_duration_seconds = models.FloatField(null=True, blank=True, help_text="Average task duration in seconds")
    max_duration_seconds = models.FloatField(null=True, blank=True, help_text="Maximum task duration in seconds")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for TaskStatistics model."""

        ordering = ["-date"]
        indexes = [
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"Task Stats - {self.date}"

    @property
    def total_tasks(self):
        """Calculate total number of tasks."""
        return self.check_updates_count + self.download_data_count + self.process_data_count + self.full_pipeline_count + self.reprocess_data_count

    @property
    def success_rate(self):
        """Calculate success rate as percentage."""
        total = self.success_count + self.failure_count
        if total == 0:
            return None
        return (self.success_count / total) * 100


class SourceAuthToken(models.Model):
    """Authentication token storage for data sources.
    
    Stores access tokens, refresh tokens, and expiration times to avoid
    repeated authentication requests and comply with API rate limits.
    """
    
    source = models.OneToOneField(
        Source, 
        on_delete=models.CASCADE, 
        related_name="auth_token",
        help_text="Data source this token belongs to"
    )
    access_token = models.TextField(
        blank=True, 
        help_text="Access token for API authentication"
    )
    refresh_token = models.TextField(
        blank=True, 
        help_text="Refresh token for renewing access token"
    )
    token_type = models.CharField(
        max_length=50, 
        default='Bearer',
        help_text="Type of token (e.g., Bearer, Basic)"
    )
    expires_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the access token expires"
    )
    refresh_expires_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the refresh token expires"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional token-related metadata (scope, user info, etc.)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta configuration for SourceAuthToken model."""
        
        ordering = ["source__name"]
        indexes = [
            models.Index(fields=["source", "expires_at"]),
        ]

    def __str__(self):
        return f"Auth Token - {self.source.name}"
    
    def is_access_token_valid(self) -> bool:
        """Check if access token is still valid."""
        if not self.access_token:
            return False
        if not self.expires_at:
            return True  # No expiration set
        return timezone.now() < self.expires_at
    
    def is_refresh_token_valid(self) -> bool:
        """Check if refresh token is still valid."""
        if not self.refresh_token:
            return False
        if not self.refresh_expires_at:
            return True  # No expiration set
        return timezone.now() < self.refresh_expires_at
    
    def needs_refresh(self, buffer_minutes: int = 5) -> bool:
        """Check if token needs refreshing (accounting for buffer time)."""
        if not self.expires_at:
            return False
        buffer_time = timezone.now() + timezone.timedelta(minutes=buffer_minutes)
        return buffer_time >= self.expires_at
    
    def clear_tokens(self):
        """Clear all stored tokens."""
        self.access_token = ""
        self.refresh_token = ""
        self.expires_at = None
        self.refresh_expires_at = None
        self.metadata = {}
        self.save(update_fields=['access_token', 'refresh_token', 'expires_at', 'refresh_expires_at', 'metadata', 'updated_at'])
