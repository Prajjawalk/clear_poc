"""Django models for the LLM service."""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ProviderConfig(models.Model):
    """Configuration for LLM providers."""

    provider_name = models.CharField(max_length=50, unique=True, help_text="Unique provider identifier")
    is_active = models.BooleanField(default=True, help_text="Whether the provider is currently active")
    priority = models.IntegerField(default=100, help_text="Provider selection priority (lower = higher priority)")
    config = models.JSONField(default=dict, help_text="Provider-specific configuration")
    rate_limit = models.IntegerField(null=True, blank=True, help_text="Requests per minute limit")
    token_limit = models.IntegerField(null=True, blank=True, help_text="Tokens per day limit")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        ordering = ["priority", "provider_name"]
        verbose_name = "Provider Configuration"
        verbose_name_plural = "Provider Configurations"

    def __str__(self):
        """String representation."""
        return f"{self.provider_name} ({'Active' if self.is_active else 'Inactive'})"


class QueryLog(models.Model):
    """Log of all LLM queries for audit and analysis."""

    # Core fields
    provider = models.CharField(max_length=50, db_index=True, help_text="Provider identifier")
    model = models.CharField(max_length=100, help_text="Model name used")
    prompt_hash = models.CharField(max_length=64, db_index=True, help_text="SHA-256 hash of prompt for privacy")

    # Query content (optional - can be disabled for privacy)
    prompt_text = models.TextField(null=True, blank=True, help_text="Original prompt text (if logging enabled)")
    response_text = models.TextField(null=True, blank=True, help_text="LLM response text (if logging enabled)")

    # Token tracking
    tokens_input = models.IntegerField(default=0, help_text="Input token count")
    tokens_output = models.IntegerField(default=0, help_text="Output token count")
    total_tokens = models.IntegerField(default=0, help_text="Total tokens used")

    # Performance metrics
    response_time_ms = models.IntegerField(help_text="Response time in milliseconds")
    success = models.BooleanField(default=True, help_text="Query success status")
    error_message = models.TextField(null=True, blank=True, help_text="Error details if failed")

    # Cost tracking
    cost_estimate = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True, help_text="Estimated cost in USD")

    # Context
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, help_text="User who made the query")
    application = models.CharField(max_length=100, db_index=True, help_text="Calling application identifier")
    metadata = models.JSONField(default=dict, help_text="Additional query metadata")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        """Model metadata."""

        ordering = ["-created_at"]
        verbose_name = "Query Log"
        verbose_name_plural = "Query Logs"
        indexes = [
            models.Index(fields=["provider", "created_at"]),
            models.Index(fields=["application", "created_at"]),
        ]

    def __str__(self):
        """String representation."""
        status = "✓" if self.success else "✗"
        return f"{self.provider}/{self.model} - {self.prompt_hash[:8]} - {self.response_time_ms}ms - {status}"


class CachedResponse(models.Model):
    """Cached LLM responses for performance optimization."""

    cache_key = models.CharField(max_length=64, unique=True, db_index=True, help_text="Unique cache identifier (SHA-256 hash)")
    provider = models.CharField(max_length=50, help_text="Provider that generated response")
    model = models.CharField(max_length=100, help_text="Model used")
    response_text = models.TextField(help_text="Cached response content")
    response_metadata = models.JSONField(default=dict, help_text="Response metadata")

    # Cache management
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True, help_text="Cache expiration time")
    hit_count = models.IntegerField(default=0, help_text="Number of cache hits")
    last_accessed = models.DateTimeField(auto_now=True, help_text="Last cache hit timestamp")

    class Meta:
        """Model metadata."""

        ordering = ["-last_accessed"]
        verbose_name = "Cached Response"
        verbose_name_plural = "Cached Responses"
        indexes = [
            models.Index(fields=["provider", "model", "created_at"]),
        ]

    def __str__(self):
        """String representation."""
        return f"{self.cache_key[:8]} ({self.provider}) - {self.hit_count} hits"

    def is_expired(self):
        """Check if the cache entry has expired."""
        return timezone.now() > self.expires_at

    def increment_hit_count(self):
        """Increment the hit count and update last accessed time."""
        self.hit_count += 1
        self.last_accessed = timezone.now()
        self.save(update_fields=["hit_count", "last_accessed"])
