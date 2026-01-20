"""Integration tests for alerts app caching with API endpoints."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from alerts.models import Alert, ShockType
from data_pipeline.models import Source


class CacheIntegrationTest(TestCase):
    """Basic integration tests for caching functionality."""

    def setUp(self):
        """Set up test data."""
        cache.clear()

        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.shock_type = ShockType.objects.create(
            name="Conflict",
            icon="fa-warning",
            color="#ff0000"
        )

        # Create data source
        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source for integration tests",
            is_active=True
        )

        self.alert = Alert.objects.create(
            title="Cached Alert",
            text="This alert should be cached",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=4,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=6),
            go_no_go=True
        )

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    def test_cache_clear_functionality(self):
        """Test that cache clearing works properly."""
        # Set a test value in cache
        cache.set("test_key", "test_value", 300)
        self.assertEqual(cache.get("test_key"), "test_value")

        # Clear cache and verify it's cleared
        cache.clear()
        self.assertIsNone(cache.get("test_key"))