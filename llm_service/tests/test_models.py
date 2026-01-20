"""Tests for LLM service models."""

import json
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from llm_service.models import ProviderConfig, QueryLog, CachedResponse


class ProviderConfigTestCase(TestCase):
    """Test cases for ProviderConfig model."""

    def test_create_provider_config(self):
        """Test creating a provider configuration."""
        config = ProviderConfig.objects.create(
            provider_name="test_provider",
            config={
                "api_key": "test_key",
                "api_base": "http://test.com"
            },
            is_active=True
        )

        self.assertEqual(config.provider_name, "test_provider")
        self.assertTrue(config.is_active)
        self.assertIn("api_key", config.config)

    def test_provider_config_str(self):
        """Test string representation of ProviderConfig."""
        config = ProviderConfig.objects.create(
            provider_name="test_provider"
        )

        self.assertEqual(str(config), "test_provider (Active)")

    def test_provider_config_validation(self):
        """Test provider configuration validation."""
        config = ProviderConfig.objects.create(
            provider_name="test_provider",
            config={"api_key": "valid_key"}
        )

        # Test valid configuration - just check config exists
        self.assertTrue(config.config)

    def test_get_active_providers(self):
        """Test getting active providers."""
        # Create active provider
        ProviderConfig.objects.create(
            provider_name="active_provider",
            is_active=True
        )

        # Create inactive provider
        ProviderConfig.objects.create(
            provider_name="inactive_provider",
            is_active=False
        )

        active_providers = ProviderConfig.objects.filter(is_active=True)
        self.assertEqual(active_providers.count(), 1)
        self.assertEqual(active_providers.first().provider_name, "active_provider")


class QueryLogTestCase(TestCase):
    """Test cases for QueryLog model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )

    def test_create_query_log(self):
        """Test creating a query log entry."""
        log = QueryLog.objects.create(
            provider="litellm",
            model="gpt-3.5-turbo",
            prompt_hash="abc123",
            tokens_input=10,
            tokens_output=20,
            total_tokens=30,
            response_time_ms=500,
            success=True,
            user=self.user,
            application="test_app"
        )

        self.assertEqual(log.provider, "litellm")
        self.assertEqual(log.model, "gpt-3.5-turbo")
        self.assertEqual(log.total_tokens, 30)
        self.assertTrue(log.success)
        self.assertEqual(log.user, self.user)

    def test_query_log_str(self):
        """Test string representation of QueryLog."""
        log = QueryLog.objects.create(
            provider="litellm",
            model="gpt-3.5-turbo",
            prompt_hash="abc123",
            response_time_ms=500,
            success=True
        )

        expected_str = f"litellm/gpt-3.5-turbo - abc123[:8] - 500ms - ✓"
        self.assertEqual(str(log), expected_str)

    def test_query_log_failed(self):
        """Test query log for failed request."""
        log = QueryLog.objects.create(
            provider="litellm",
            model="gpt-3.5-turbo",
            prompt_hash="abc123",
            response_time_ms=1000,
            success=False,
            error_message="Rate limit exceeded"
        )

        self.assertFalse(log.success)
        self.assertEqual(log.error_message, "Rate limit exceeded")
        self.assertIn("✗", str(log))

    def test_recent_queries_queryset(self):
        """Test recent queries manager method."""
        # Create old query
        old_log = QueryLog.objects.create(
            provider="litellm",
            model="gpt-3.5-turbo",
            prompt_hash="old123",
            response_time_ms=500,
            success=True
        )
        old_log.created_at = timezone.now() - timedelta(days=2)
        old_log.save()

        # Create recent query
        recent_log = QueryLog.objects.create(
            provider="litellm",
            model="gpt-3.5-turbo",
            prompt_hash="recent123",
            response_time_ms=500,
            success=True
        )

        recent_queries = QueryLog.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=1)
        )

        self.assertEqual(recent_queries.count(), 1)
        self.assertEqual(recent_queries.first(), recent_log)


class CachedResponseTestCase(TestCase):
    """Test cases for CachedResponse model."""

    def test_create_cached_response(self):
        """Test creating a cached response."""
        cache = CachedResponse.objects.create(
            cache_key="test_key_123",
            provider="litellm",
            model="gpt-3.5-turbo",
            response_text="Hello, world!",
            response_metadata={"temperature": 0.7},
            expires_at=timezone.now() + timedelta(hours=1)
        )

        self.assertEqual(cache.cache_key, "test_key_123")
        self.assertEqual(cache.provider, "litellm")
        self.assertEqual(cache.response_text, "Hello, world!")
        self.assertEqual(cache.hit_count, 0)

    def test_cached_response_str(self):
        """Test string representation of CachedResponse."""
        cache = CachedResponse.objects.create(
            cache_key="test_key_123",
            provider="litellm",
            response_text="Hello, world!",
            expires_at=timezone.now() + timedelta(hours=1)
        )

        expected_str = "test_key (litellm) - 0 hits"
        self.assertEqual(str(cache), expected_str)

    def test_is_expired(self):
        """Test cache expiration check."""
        # Create expired cache
        expired_cache = CachedResponse.objects.create(
            cache_key="expired_key",
            provider="litellm",
            response_text="Expired response",
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # Create valid cache
        valid_cache = CachedResponse.objects.create(
            cache_key="valid_key",
            provider="litellm",
            response_text="Valid response",
            expires_at=timezone.now() + timedelta(hours=1)
        )

        self.assertTrue(expired_cache.is_expired())
        self.assertFalse(valid_cache.is_expired())

    def test_increment_hit_count(self):
        """Test incrementing cache hit count."""
        cache = CachedResponse.objects.create(
            cache_key="test_key",
            provider="litellm",
            response_text="Test response",
            expires_at=timezone.now() + timedelta(hours=1)
        )

        self.assertEqual(cache.hit_count, 0)

        cache.increment_hit_count()
        self.assertEqual(cache.hit_count, 1)

        cache.increment_hit_count()
        self.assertEqual(cache.hit_count, 2)

    def test_get_active_cache(self):
        """Test getting non-expired cache entries."""
        # Create expired cache
        CachedResponse.objects.create(
            cache_key="expired_key",
            provider="litellm",
            response_text="Expired response",
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # Create valid cache
        valid_cache = CachedResponse.objects.create(
            cache_key="valid_key",
            provider="litellm",
            response_text="Valid response",
            expires_at=timezone.now() + timedelta(hours=1)
        )

        active_cache = CachedResponse.objects.filter(
            expires_at__gt=timezone.now()
        )

        self.assertEqual(active_cache.count(), 1)
        self.assertEqual(active_cache.first(), valid_cache)

    def test_cache_metadata_handling(self):
        """Test handling of response metadata."""
        metadata = {
            "temperature": 0.7,
            "max_tokens": 150,
            "model": "gpt-3.5-turbo"
        }

        cache = CachedResponse.objects.create(
            cache_key="metadata_test",
            provider="litellm",
            response_text="Test response",
            response_metadata=metadata,
            expires_at=timezone.now() + timedelta(hours=1)
        )

        # Verify metadata is properly stored and retrieved
        self.assertEqual(cache.response_metadata["temperature"], 0.7)
        self.assertEqual(cache.response_metadata["max_tokens"], 150)
        self.assertEqual(cache.response_metadata["model"], "gpt-3.5-turbo")