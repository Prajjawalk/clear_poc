"""Admin configuration for translation app."""

from django.contrib import admin
from django.utils.html import format_html

from .utils import clear_translation_cache


class TranslationStringAdmin(admin.ModelAdmin):
    """Admin interface for TranslationString model."""

    list_display = [
        "label",
        "value_preview",
        "is_active",
        "translation_status",
        "created_at",
        "updated_at",
    ]
    list_filter = ["is_active", "created_at", "updated_at"]
    search_fields = ["label", "value", "description"]
    ordering = ["label"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("label", "is_active")}),
        ("Content", {"fields": ("value", "description")}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def value_preview(self, obj):
        """Show a preview of the value."""
        if obj.value:
            preview = obj.value[:50]
            if len(obj.value) > 50:
                preview += "..."
            return preview
        return "-"

    value_preview.short_description = "Value Preview"

    def translation_status(self, obj):
        """Show translation status for all languages."""
        from django.conf import settings

        statuses = []
        for lang_code, _lang_name in settings.LANGUAGES:
            if lang_code == settings.LANGUAGE_CODE:
                # Default language
                statuses.append(f"✓ {lang_code}")
            else:
                value_field = f"value_{lang_code}"
                translated_value = getattr(obj, value_field, None)
                if translated_value and translated_value.strip():
                    statuses.append(f"✓ {lang_code}")
                else:
                    statuses.append(f"✗ {lang_code}")

        return format_html(" | ".join(statuses))

    translation_status.short_description = "Translation Status"

    def save_model(self, request, obj, form, change):
        """Override save to clear cache."""
        super().save_model(request, obj, form, change)
        clear_translation_cache(obj.label)

    def delete_model(self, request, obj):
        """Override delete to clear cache."""
        label = obj.label
        super().delete_model(request, obj)
        clear_translation_cache(label)

    def delete_queryset(self, request, queryset):
        """Override bulk delete to clear cache."""
        labels = list(queryset.values_list("label", flat=True))
        super().delete_queryset(request, queryset)
        for label in labels:
            clear_translation_cache(label)

    actions = ["make_active", "make_inactive", "clear_cache_action"]

    def make_active(self, request, queryset):
        """Mark selected translations as active."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} translation(s) marked as active.")
        # Clear cache for updated items
        for obj in queryset:
            clear_translation_cache(obj.label)

    make_active.short_description = "Mark selected translations as active"

    def make_inactive(self, request, queryset):
        """Mark selected translations as inactive."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} translation(s) marked as inactive.")
        # Clear cache for updated items
        for obj in queryset:
            clear_translation_cache(obj.label)

    make_inactive.short_description = "Mark selected translations as inactive"

    def clear_cache_action(self, request, queryset):
        """Clear cache for selected translations."""
        for obj in queryset:
            clear_translation_cache(obj.label)
        self.message_user(request, f"Cache cleared for {queryset.count()} translation(s).")

    clear_cache_action.short_description = "Clear cache for selected translations"

    class Media:
        """Add custom CSS and JS."""

        css = {"all": ("admin/css/forms.css",)}
        js = (
            "admin/js/core.js",
            "admin/js/admin/RelatedObjectLookups.js",
        )


# Admin registration is handled in apps.py ready() method
