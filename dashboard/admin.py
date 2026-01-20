"""Admin interface for dashboard models."""

from django.contrib import admin

from .models import ColorMap, Theme, ThemeVariable


@admin.register(ColorMap)
class ColorMapAdmin(admin.ModelAdmin):
    """Admin interface for ColorMap model."""

    list_display = ['name', 'named_colormap', 'color_start', 'color_end', 'is_active']
    list_filter = ['is_active', 'named_colormap']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    fieldsets = [
        ('Basic Information', {
            'fields': ['name', 'description', 'is_active']
        }),
        ('Named ColorMap', {
            'fields': ['named_colormap'],
            'description': 'Use a predefined ColorBrewer scheme (e.g., Reds, Blues)'
        }),
        ('Custom Color Scale', {
            'fields': ['color_start', 'color_end'],
            'description': 'Or define a custom two-color linear scale using hex colors'
        }),
        ('Colorbar Image', {
            'fields': ['colorbar_image'],
            'description': 'Upload a custom colorbar image. If not provided, the system will use the default image based on the colormap name.'
        }),
    ]


class ThemeVariableInline(admin.TabularInline):
    """Inline admin for theme variables."""

    model = ThemeVariable
    extra = 1
    fields = ['variable', 'order', 'min_value', 'max_value', 'opacity']
    autocomplete_fields = ['variable']


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    """Admin interface for Theme model."""

    list_display = ['name', 'code', 'colormap', 'is_combined', 'is_active', 'order']
    list_filter = ['is_active', 'is_combined', 'colormap']
    search_fields = ['name', 'code', 'description']
    list_editable = ['is_active', 'order']
    autocomplete_fields = ['colormap']
    inlines = [ThemeVariableInline]
    fieldsets = [
        ('Basic Information', {
            'fields': ['code', 'name', 'description']
        }),
        ('Display Settings', {
            'fields': ['colormap', 'icon', 'is_combined', 'is_active', 'order']
        }),
    ]


@admin.register(ThemeVariable)
class ThemeVariableAdmin(admin.ModelAdmin):
    """Admin interface for ThemeVariable model."""

    list_display = ['theme', 'variable', 'order', 'min_value', 'max_value', 'opacity']
    list_filter = ['theme']
    search_fields = ['theme__name', 'variable__name', 'variable__code']
    autocomplete_fields = ['theme', 'variable']
    list_editable = ['order', 'opacity']
