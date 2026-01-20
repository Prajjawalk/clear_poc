"""Location models for geographic data and hierarchical location management."""

from django.contrib.gis.db import models
from django.core.validators import RegexValidator


class AdmLevel(models.Model):
    """Administrative level definition (country, admin1, admin2, etc.)."""

    code = models.CharField(max_length=10, unique=True, help_text="Administrative level code (e.g., '0' for country, '1' for admin1)")
    name = models.CharField(max_length=100, help_text="Name of the administrative level")

    class Meta:
        """Meta configuration for AdmLevel model."""

        ordering = ["code"]

    def __str__(self):
        return f"Admin Level {self.code}: {self.name}"


class Location(models.Model):
    """Hierarchical location model with geographic boundaries."""

    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children", help_text="Parent location in hierarchy")
    admin_level = models.ForeignKey(AdmLevel, on_delete=models.PROTECT, related_name="locations", help_text="Administrative level of this location")
    geo_id = models.CharField(
        max_length=50,
        unique=True,
        validators=[RegexValidator(regex=r"^[A-Z]{2}(_[0-9]{3,})*$", message="geo_id must follow format: XY for admin0, XY_001 for admin1, XY_001_002 for admin2, etc.")],
        help_text="Hierarchical geographic identifier (e.g., SD, SD_001, SD_001_002)",
    )
    name = models.CharField(max_length=255, help_text="Name of the location")
    boundary = models.MultiPolygonField(null=True, blank=True, help_text="Geographic boundary")
    point = models.PointField(null=True, blank=True, help_text="Representative point")

    POINT_TYPE_CHOICES = [
        ('centroid', 'Centroid'),
        ('gps', 'GPS Coordinates'),
    ]
    point_type = models.CharField(
        max_length=10,
        choices=POINT_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text="Type of point geometry - centroid calculated from boundary or actual GPS coordinates"
    )

    comment = models.TextField(null=True, blank=True, help_text="Additional information about the location")

    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        """Meta configuration for Location model."""

        ordering = ["geo_id"]
        indexes = [
            models.Index(fields=["geo_id"]),
            models.Index(fields=["admin_level"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"{self.geo_id}: {self.name}"

    @property
    def latitude(self):
        """Get latitude from point geometry."""
        return self.point.y if self.point else None

    @property
    def longitude(self):
        """Get longitude from point geometry."""
        return self.point.x if self.point else None

    def get_full_hierarchy(self):
        """Return full hierarchical path from country to this location."""
        hierarchy = [self]
        current = self.parent
        while current:
            hierarchy.insert(0, current)
            current = current.parent
        return hierarchy

    def get_children_at_level(self, admin_level_code):
        """Get all children at a specific administrative level."""
        return self.get_descendants().filter(admin_level__code=admin_level_code)

    def get_descendants(self):
        """Get all descendant locations."""

        def get_all_children(location):
            children = list(location.children.all())
            for child in list(children):
                children.extend(get_all_children(child))
            return children

        return Location.objects.filter(id__in=[loc.id for loc in get_all_children(self)])


class Gazetteer(models.Model):
    """Alternative names and codes for locations from various sources."""

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="gazetteer_entries", help_text="Location this entry refers to")
    source = models.CharField(max_length=100, help_text="Source of this name/code (e.g., 'ACLED', 'UNHCR', 'local')")
    code = models.CharField(max_length=50, blank=True, help_text="Alternative code for the location")
    name = models.CharField(max_length=255, help_text="Alternative name for the location")

    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    updated_at = models.DateTimeField(blank=True, null=True, auto_now=True)

    class Meta:
        """Meta configuration for Gazetteer model."""

        unique_together = [["location", "source", "name"], ["location", "source", "code"]]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["code"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self):
        code_part = f" ({self.code})" if self.code else ""
        return f"{self.name}{code_part} [{self.source}] -> {self.location.geo_id}"


class UnmatchedLocation(models.Model):
    """Track locations that failed to match during data processing."""

    name = models.CharField(max_length=255, help_text="Location name that failed to match")
    code = models.CharField(max_length=50, blank=True, help_text="Location code if available")
    admin_level = models.CharField(max_length=50, blank=True, help_text="Admin level if known (e.g., 'State', 'Locality')")
    source = models.CharField(max_length=100, help_text="Source that provided this location (e.g., 'IDMC GIDD')")
    context = models.TextField(blank=True, help_text="Additional context or full location string")

    # Track frequency and last occurrence
    occurrence_count = models.IntegerField(default=1, help_text="Number of times this location failed to match")
    first_seen = models.DateTimeField(auto_now_add=True, help_text="First time this location was seen")
    last_seen = models.DateTimeField(auto_now=True, help_text="Last time this location was seen")

    # Resolution status
    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("resolved", "Resolved - Added to Gazetteer"),
        ("ignored", "Ignored - Invalid/Test Data"),
        ("deferred", "Deferred - Needs More Information"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", help_text="Review status")
    resolved_location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolved_unmatched", help_text="Location this was resolved to")

    # Matching metadata
    matched_at = models.DateTimeField(null=True, blank=True, help_text="When this location was matched")
    matched_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, help_text="User who performed the matching")
    is_matched = models.BooleanField(default=False, help_text="Whether this location has been matched to a location")

    # Precomputed potential matches for performance
    potential_matches = models.JSONField(default=list, blank=True, help_text="Precomputed list of potential location matches with similarity scores")
    potential_matches_computed_at = models.DateTimeField(null=True, blank=True, help_text="When the potential matches were last computed")
    notes = models.TextField(blank=True, help_text="Admin notes about resolution")

    class Meta:
        """Meta configuration for UnmatchedLocation model."""

        ordering = ["-occurrence_count", "-last_seen"]
        unique_together = [["name", "source"]]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["source"]),
            models.Index(fields=["-occurrence_count"]),
            models.Index(fields=["-last_seen"]),
        ]

    def __str__(self):
        return f"{self.name} [{self.source}] - {self.get_status_display()} ({self.occurrence_count}x)"

    def increment_occurrence(self):
        """Increment the occurrence count when this location is seen again."""
        self.occurrence_count += 1
        self.save(update_fields=["occurrence_count", "last_seen"])

    def trigger_match_computation(self):
        """Trigger background computation of potential matches."""
        # Only compute if we haven't computed recently
        if not self.potential_matches_computed_at:
            try:
                from location.tasks import compute_potential_matches

                compute_potential_matches.delay(self.id)
            except ImportError:
                # Celery might not be available in some contexts (tests, etc.)
                pass

    def save(self, *args, **kwargs):
        """Override save to trigger match computation for new unmatched locations."""
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Trigger computation for new unmatched locations
        if is_new and self.status == "pending":
            self.trigger_match_computation()
