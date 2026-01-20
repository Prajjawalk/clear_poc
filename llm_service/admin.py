"""Django admin configuration for LLM service models."""

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import ProviderConfig, QueryLog, CachedResponse


@admin.register(ProviderConfig)
class ProviderConfigAdmin(admin.ModelAdmin):
    """Admin interface for ProviderConfig model."""

    list_display = [
        'provider_name',
        'is_active_badge',
        'priority',
        'rate_limit',
        'token_limit',
        'created_at',
        'updated_at'
    ]
    list_filter = ['is_active', 'priority', 'created_at']
    search_fields = ['provider_name']
    ordering = ['priority', 'provider_name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('provider_name', 'is_active', 'priority')
        }),
        ('Configuration', {
            'fields': ('config',),
            'description': 'Provider-specific configuration in JSON format'
        }),
        ('Limits', {
            'fields': ('rate_limit', 'token_limit'),
            'description': 'Optional rate and token limits for this provider'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def is_active_badge(self, obj):
        """Display active status as a colored badge."""
        if obj.is_active:
            return format_html(
                '<span class="badge" style="background-color: #28a745; color: white;">Active</span>'
            )
        else:
            return format_html(
                '<span class="badge" style="background-color: #dc3545; color: white;">Inactive</span>'
            )
    is_active_badge.short_description = 'Status'


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    """Admin interface for QueryLog model."""

    list_display = [
        'created_at',
        'provider',
        'model',
        'user',
        'success_badge',
        'response_time_ms',
        'total_tokens',
        'application'
    ]
    list_filter = [
        'success',
        'provider',
        'model',
        'application',
        'created_at'
    ]
    search_fields = ['prompt_hash', 'user__username', 'error_message']
    ordering = ['-created_at']
    readonly_fields = [
        'prompt_hash',
        'tokens_input',
        'tokens_output',
        'total_tokens',
        'response_time_ms',
        'success',
        'error_message',
        'cost_estimate',
        'user',
        'application',
        'metadata',
        'created_at'
    ]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Query Information', {
            'fields': ('provider', 'model', 'prompt_hash', 'user', 'application')
        }),
        ('Performance Metrics', {
            'fields': ('response_time_ms', 'tokens_input', 'tokens_output', 'total_tokens', 'cost_estimate')
        }),
        ('Status', {
            'fields': ('success', 'error_message')
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def success_badge(self, obj):
        """Display success status as a colored badge."""
        if obj.success:
            return format_html(
                '<span class="badge" style="background-color: #28a745; color: white;">✓ Success</span>'
            )
        else:
            return format_html(
                '<span class="badge" style="background-color: #dc3545; color: white;">✗ Failed</span>'
            )
    success_badge.short_description = 'Result'

    def has_add_permission(self, request):
        """Disable adding new query logs manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Make query logs read-only."""
        return False


@admin.register(CachedResponse)
class CachedResponseAdmin(admin.ModelAdmin):
    """Admin interface for CachedResponse model."""

    list_display = [
        'cache_key_short',
        'provider',
        'model',
        'hit_count',
        'created_at',
        'expires_at',
        'is_expired_badge',
        'response_size'
    ]
    list_filter = ['provider', 'model', 'created_at', 'expires_at']
    search_fields = ['cache_key', 'response_text']
    ordering = ['-last_accessed']
    readonly_fields = [
        'cache_key',
        'provider',
        'model',
        'response_text',
        'response_metadata',
        'created_at',
        'expires_at',
        'hit_count',
        'last_accessed'
    ]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Cache Information', {
            'fields': ('cache_key', 'provider', 'model')
        }),
        ('Response Data', {
            'fields': ('response_text', 'response_metadata')
        }),
        ('Cache Statistics', {
            'fields': ('hit_count', 'created_at', 'last_accessed', 'expires_at')
        }),
    )

    def cache_key_short(self, obj):
        """Display shortened cache key."""
        return f"{obj.cache_key[:16]}..." if len(obj.cache_key) > 16 else obj.cache_key
    cache_key_short.short_description = 'Cache Key'

    def is_expired_badge(self, obj):
        """Display expiration status as a colored badge."""
        if obj.is_expired():
            return format_html(
                '<span class="badge" style="background-color: #dc3545; color: white;">Expired</span>'
            )
        else:
            return format_html(
                '<span class="badge" style="background-color: #28a745; color: white;">Active</span>'
            )
    is_expired_badge.short_description = 'Status'

    def response_size(self, obj):
        """Display response size in a human-readable format."""
        size = len(obj.response_text) if obj.response_text else 0
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    response_size.short_description = 'Size'

    def has_add_permission(self, request):
        """Disable adding new cache entries manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Make cache entries read-only except for deletion."""
        return False

    actions = ['delete_expired_entries', 'clear_selected_cache']

    def delete_expired_entries(self, request, queryset):
        """Custom action to delete all expired cache entries."""
        expired_count = CachedResponse.objects.filter(expires_at__lt=timezone.now()).count()
        CachedResponse.objects.filter(expires_at__lt=timezone.now()).delete()
        self.message_user(
            request,
            f"Deleted {expired_count} expired cache entries.",
            level='SUCCESS'
        )
    delete_expired_entries.short_description = "Delete all expired cache entries"

    def clear_selected_cache(self, request, queryset):
        """Custom action to clear selected cache entries."""
        count = queryset.count()
        queryset.delete()
        self.message_user(
            request,
            f"Cleared {count} cache entries.",
            level='SUCCESS'
        )
    clear_selected_cache.short_description = "Clear selected cache entries"
