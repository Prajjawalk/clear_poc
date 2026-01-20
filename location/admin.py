"""Admin interface for location models."""

from django import forms
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from modeltranslation.admin import TranslationAdmin

from .models import AdmLevel, Gazetteer, Location, UnmatchedLocation


@admin.register(AdmLevel)
class AdmLevelAdmin(TranslationAdmin):
    """Admin interface for AdmLevel model."""

    list_display = ["code", "name"]
    search_fields = ["code", "name"]
    ordering = ["code"]


class LocationAdminForm(forms.ModelForm):
    """Custom form for Location admin to exclude lowest admin level from parent choices."""

    class Meta:
        model = Location
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """Initialize form with filtered parent choices."""
        super().__init__(*args, **kwargs)
        # Exclude admin level 3 (Settlement) from parent choices as they can't be parents
        self.fields['parent'].queryset = Location.objects.exclude(admin_level__code='3').select_related('admin_level').order_by('geo_id')


@admin.register(Location)
class LocationAdmin(GISModelAdmin, TranslationAdmin):
    """Admin interface for Location model with GIS support."""

    form = LocationAdminForm
    list_display = ["geo_id", "name", "admin_level", "parent"]
    list_filter = ["admin_level", "created_at"]
    search_fields = ["geo_id", "name", "comment"]
    ordering = ["geo_id"]

    fieldsets = (
        ("Basic Information", {"fields": ("geo_id", "name", "admin_level", "parent", "comment")}),
        ("Geographic Data", {"fields": ("point", "boundary"), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields = ["created_at", "updated_at"]

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("admin_level", "parent")


@admin.register(Gazetteer)
class GazetteerAdmin(admin.ModelAdmin):
    """Admin interface for Gazetteer model."""

    list_display = ["name", "code", "source", "location"]
    list_filter = ["source", "created_at"]
    search_fields = ["name", "code", "source", "location__name", "location__geo_id"]
    ordering = ["source", "name"]

    fieldsets = (("Alternative Name/Code", {"fields": ("location", "source", "name", "code")}), ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}))

    readonly_fields = ["created_at", "updated_at"]

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("location", "location__admin_level")


@admin.register(UnmatchedLocation)
class UnmatchedLocationAdmin(admin.ModelAdmin):
    """Basic admin interface for unmatched locations - use /location/unmatched/ for full management."""

    list_display = ['name', 'source', 'admin_level', 'occurrence_count', 'status', 'last_seen']
    list_filter = ['status', 'source', 'admin_level', 'last_seen']
    search_fields = ['name', 'code', 'context', 'notes']
    ordering = ['-occurrence_count', '-last_seen']
    readonly_fields = ['occurrence_count', 'first_seen', 'last_seen']

    def has_add_permission(self, request):
        """Disable adding through admin - these are created automatically."""
        return False

    def get_readonly_fields(self, request, obj=None):
        """Make most fields readonly - use the dedicated page for management."""
        if obj:  # Editing existing object
            return ['name', 'code', 'admin_level', 'source', 'context',
                   'occurrence_count', 'first_seen', 'last_seen']
        return self.readonly_fields
