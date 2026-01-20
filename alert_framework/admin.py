"""Django admin configuration for alert framework models."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import AlertTemplate, Detection, Detector, PublishedAlert


@admin.register(Detector)
class DetectorAdmin(admin.ModelAdmin):
    """Admin interface for Detector model."""

    list_display = [
        "name",
        "class_name_short",
        "active_status",
        "schedule",
        "last_run_display",
        "detection_count",
        "created_at",
    ]

    list_filter = [
        "active",
        "created_at",
        "last_run",
    ]

    search_fields = [
        "name",
        "description",
        "class_name",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "last_run",
        "detection_count",
        "detection_stats",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": (
                    "name",
                    "description",
                    "class_name",
                    "active",
                )
            },
        ),
        (
            "Configuration",
            {
                "fields": (
                    "configuration",
                    "schedule",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "last_run",
                    "detection_count",
                    "detection_stats",
                    "created_at",
                    "updated_at",
                ),
                "classes": ["collapse"],
            },
        ),
    ]

    actions = [
        "activate_detectors",
        "deactivate_detectors",
        "run_detectors",
    ]

    def class_name_short(self, obj):
        """Display shortened class name."""
        parts = obj.class_name.split(".")
        if len(parts) > 2:
            return f"...{parts[-2]}.{parts[-1]}"
        return obj.class_name

    class_name_short.short_description = "Class"

    def active_status(self, obj):
        """Display active status with styling."""
        if obj.active:
            return format_html('<span style="color: green; font-weight: bold;">✓ Active</span>')
        else:
            return format_html('<span style="color: red; font-weight: bold;">✗ Inactive</span>')

    active_status.short_description = "Status"

    def last_run_display(self, obj):
        """Display last run time in a user-friendly format."""
        if obj.last_run:
            return obj.last_run.strftime("%Y-%m-%d %H:%M")
        return "-"

    last_run_display.short_description = "Last Run"

    def detection_count(self, obj):
        """Display total detection count with link."""
        count = obj.detections.count()
        if count > 0:
            url = reverse("admin:alert_framework_detection_changelist")
            return format_html('<a href="{}?detector__id__exact={}">{}</a>', url, obj.id, count)
        return "0"

    detection_count.short_description = "Detections"

    def detection_stats(self, obj):
        """Display detection statistics."""
        stats = {
            "pending": obj.detections.filter(status="pending").count(),
            "processed": obj.detections.filter(status="processed").count(),
            "dismissed": obj.detections.filter(status="dismissed").count(),
        }

        if sum(stats.values()) == 0:
            return "No detections"

        parts = []
        for status, count in stats.items():
            if count > 0:
                parts.append(f"{count} {status}")

        return ", ".join(parts)

    detection_stats.short_description = "Detection Stats"

    def activate_detectors(self, request, queryset):
        """Activate selected detectors."""
        updated = queryset.update(active=True)
        self.message_user(request, f"Successfully activated {updated} detector{'s' if updated != 1 else ''}.")

    activate_detectors.short_description = "Activate selected detectors"

    def deactivate_detectors(self, request, queryset):
        """Deactivate selected detectors."""
        updated = queryset.update(active=False)
        self.message_user(request, f"Successfully deactivated {updated} detector{'s' if updated != 1 else ''}.")

    deactivate_detectors.short_description = "Deactivate selected detectors"

    def run_detectors(self, request, queryset):
        """Queue selected detectors for execution."""
        from .tasks import run_detector

        queued_count = 0
        for detector in queryset.filter(active=True):
            run_detector.delay(detector.id)
            queued_count += 1

        if queued_count > 0:
            self.message_user(request, f"Successfully queued {queued_count} detector{'s' if queued_count != 1 else ''} for execution.")
        else:
            self.message_user(request, "No active detectors were selected.", level="warning")

    run_detectors.short_description = "Run selected active detectors"


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    """Admin interface for Detection model."""

    list_display = [
        "id",
        "detector_name",
        "detection_timestamp",
        "status_display",
        "confidence_score",
        "location_count",
        "created_at",
    ]

    list_filter = [
        "status",
        "detector",
        "detection_timestamp",
        "created_at",
        "confidence_score",
    ]

    search_fields = [
        "detector__name",
        "detection_data",
    ]

    readonly_fields = [
        "created_at",
        "processed_at",
        "location_list",
        "metadata_display",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": (
                    "detector",
                    "detection_timestamp",
                    "status",
                    "confidence_score",
                )
            },
        ),
        (
            "Locations",
            {
                "fields": (
                    "locations",
                    "location_list",
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "detection_data",
                    "metadata_display",
                    "duplicate_of",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "processed_at",
                ),
                "classes": ["collapse"],
            },
        ),
    ]

    filter_horizontal = ["locations"]

    actions = [
        "mark_as_processed",
        "mark_as_dismissed",
        "mark_as_pending",
    ]

    date_hierarchy = "detection_timestamp"

    def detector_name(self, obj):
        """Display detector name with link."""
        url = reverse("admin:alert_framework_detector_change", args=[obj.detector.id])
        return format_html('<a href="{}">{}</a>', url, obj.detector.name)

    detector_name.short_description = "Detector"

    def status_display(self, obj):
        """Display status with styling."""
        colors = {
            "pending": "orange",
            "processed": "green",
            "dismissed": "gray",
        }
        color = colors.get(obj.status, "black")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = "Status"

    def location_count(self, obj):
        """Display location count."""
        count = obj.locations.count()
        return f"{count} location{'s' if count != 1 else ''}"

    location_count.short_description = "Locations"

    def location_list(self, obj):
        """Display list of locations."""
        locations = obj.locations.all()[:10]  # Show first 10
        if not locations:
            return "No locations"

        location_names = [loc.name for loc in locations]
        result = ", ".join(location_names)

        total_count = obj.locations.count()
        if total_count > 10:
            result += f" ... and {total_count - 10} more"

        return result

    location_list.short_description = "Location Names"

    def metadata_display(self, obj):
        """Display formatted detection data."""
        if not obj.detection_data:
            return "No detection data"

        import json

        try:
            formatted = json.dumps(obj.detection_data, indent=2)
            return format_html("<pre>{}</pre>", formatted)
        except (TypeError, ValueError):
            return str(obj.detection_data)

    metadata_display.short_description = "Metadata"

    def mark_as_processed(self, request, queryset):
        """Mark selected detections as processed."""
        updated = queryset.filter(status="pending").update(status="processed")
        self.message_user(request, f"Successfully marked {updated} detection{'s' if updated != 1 else ''} as processed.")

    mark_as_processed.short_description = "Mark selected as processed"

    def mark_as_dismissed(self, request, queryset):
        """Mark selected detections as dismissed."""
        updated = queryset.filter(status="pending").update(status="dismissed")
        self.message_user(request, f"Successfully marked {updated} detection{'s' if updated != 1 else ''} as dismissed.")

    mark_as_dismissed.short_description = "Mark selected as dismissed"

    def mark_as_pending(self, request, queryset):
        """Mark selected detections as pending."""
        updated = queryset.update(status="pending")
        self.message_user(request, f"Successfully marked {updated} detection{'s' if updated != 1 else ''} as pending.")

    mark_as_pending.short_description = "Mark selected as pending"


@admin.register(AlertTemplate)
class AlertTemplateAdmin(admin.ModelAdmin):
    """Admin interface for AlertTemplate model."""

    list_display = [
        "name",
        "shock_type",
        "active_status",
        "created_at",
    ]

    list_filter = [
        "active",
        "shock_type",
        "created_at",
    ]

    search_fields = [
        "name",
        "title",
        "text",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "template_preview",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": (
                    "name",
                    "shock_type",
                    "active",
                )
            },
        ),
        (
            "Template Content",
            {
                "fields": (
                    "title",
                    "text",
                    "variables",
                    "template_preview",
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ["collapse"],
            },
        ),
    ]

    actions = [
        "activate_templates",
        "deactivate_templates",
    ]

    def active_status(self, obj):
        """Display active status with styling."""
        if obj.active:
            return format_html('<span style="color: green; font-weight: bold;">✓ Active</span>')
        else:
            return format_html('<span style="color: red; font-weight: bold;">✗ Inactive</span>')

    active_status.short_description = "Status"

    def template_preview(self, obj):
        """Display template preview."""
        if not obj.title and not obj.text:
            return "No template content"

        preview_parts = []
        if obj.title:
            preview_parts.append(f"Title: {obj.title[:100]}")
        if obj.text:
            text_preview = obj.text[:200]
            if len(obj.text) > 200:
                text_preview += "..."
            preview_parts.append(f"Content: {text_preview}")

        preview_text = "\n\n".join(preview_parts)
        return format_html("<div style='max-width: 500px; white-space: pre-wrap;'>{}</div>", preview_text)

    template_preview.short_description = "Template Preview"

    def activate_templates(self, request, queryset):
        """Activate selected templates."""
        updated = queryset.update(active=True)
        self.message_user(request, f"Successfully activated {updated} template{'s' if updated != 1 else ''}.")

    activate_templates.short_description = "Activate selected templates"

    def deactivate_templates(self, request, queryset):
        """Deactivate selected templates."""
        updated = queryset.update(active=False)
        self.message_user(request, f"Successfully deactivated {updated} template{'s' if updated != 1 else ''}.")

    deactivate_templates.short_description = "Deactivate selected templates"


@admin.register(PublishedAlert)
class PublishedAlertAdmin(admin.ModelAdmin):
    """Admin interface for PublishedAlert model."""

    list_display = [
        "id",
        "detection_link",
        "api_name",
        "external_id",
        "status_display",
        "language",
        "published_at",
        "retry_count",
    ]

    list_filter = [
        "status",
        "api_name",
        "language",
        "published_at",
        "retry_count",
    ]

    search_fields = [
        "external_id",
        "detection__detector__name",
        "template__name",
        "error_message",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "published_at",
        "last_updated",
        "cancelled_at",
        "publication_metadata_display",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": (
                    "detection",
                    "template",
                    "api_name",
                    "external_id",
                    "language",
                    "status",
                )
            },
        ),
        (
            "Publication Details",
            {
                "fields": (
                    "published_at",
                    "last_updated",
                    "cancelled_at",
                    "cancellation_reason",
                    "retry_count",
                ),
            },
        ),
        (
            "Error Information",
            {
                "fields": ("error_message",),
                "classes": ["collapse"],
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "publication_metadata_display",
                    "created_at",
                    "updated_at",
                ),
                "classes": ["collapse"],
            },
        ),
    ]

    actions = [
        "retry_failed_alerts",
        "cancel_published_alerts",
    ]

    date_hierarchy = "published_at"

    def detection_link(self, obj):
        """Display detection with link to admin page."""
        url = reverse("admin:alert_framework_detection_change", args=[obj.detection.id])
        return format_html('<a href="{}">Detection #{}</a>', url, obj.detection.id)

    detection_link.short_description = "Detection"

    def status_display(self, obj):
        """Display status with styling."""
        colors = {
            "pending": "orange",
            "published": "green",
            "failed": "red",
            "updated": "blue",
            "cancelled": "gray",
        }
        color = colors.get(obj.status, "black")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    status_display.short_description = "Status"

    def publication_metadata_display(self, obj):
        """Display formatted publication metadata."""
        if not obj.publication_metadata:
            return "No metadata"

        import json

        try:
            formatted = json.dumps(obj.publication_metadata, indent=2)
            return format_html("<pre>{}</pre>", formatted)
        except (TypeError, ValueError):
            return str(obj.publication_metadata)

    publication_metadata_display.short_description = "Publication Metadata"

    def retry_failed_alerts(self, request, queryset):
        """Retry failed alert publications."""
        from .tasks import publish_alert

        failed_alerts = queryset.filter(status="failed")
        retried_count = 0

        for alert in failed_alerts:
            # Queue retry task
            publish_alert.delay(
                detection_id=alert.detection.id,
                template_id=alert.template.id,
                target_apis=[alert.api_name],
                language=alert.language,
            )
            retried_count += 1

        self.message_user(request, f"Successfully queued {retried_count} alert{'s' if retried_count != 1 else ''} for retry.")

    retry_failed_alerts.short_description = "Retry failed alert publications"

    def cancel_published_alerts(self, request, queryset):
        """Cancel published alerts in external systems."""
        from .tasks import cancel_published_alert

        published_alerts = queryset.filter(status="published").exclude(external_id="")
        cancelled_count = 0

        for alert in published_alerts:
            # Queue cancellation task
            cancel_published_alert.delay(alert.id, reason="Cancelled via admin interface")
            cancelled_count += 1

        self.message_user(request, f"Successfully queued {cancelled_count} alert{'s' if cancelled_count != 1 else ''} for cancellation.")

    cancel_published_alerts.short_description = "Cancel published alerts"
