"""Tests for alerts app caching system."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from alerts.cache import AlertCacheManager
from alerts.models import Alert, ShockType, UserAlert
from data_pipeline.models import Source


class AlertCacheManagerTest(TestCase):
    """Tests for AlertCacheManager."""

    def setUp(self):
        """Set up test data."""
        # Clear cache before each test
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
            description="Test data source for cache tests",
            is_active=True
        )

        self.alert = Alert.objects.create(
            title="Test Alert",
            text="Test alert content",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=3,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=7),
            go_no_go=True
        )

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    def test_get_alerts_cache_key_anonymous(self):
        """Test cache key generation for anonymous users."""
        filters = {"severity": "3", "shock_type": "1", "page": 1}

        key = AlertCacheManager.get_alerts_cache_key(user_id=None, filters=filters)

        self.assertIn("alerts", key)

    def test_get_alerts_cache_key_authenticated(self):
        """Test cache key generation for authenticated users."""
        filters = {"severity": "4", "page": 2}
        user_id = self.user.id

        key = AlertCacheManager.get_alerts_cache_key(user_id=user_id, filters=filters)

        self.assertIn("alerts", key)

    def test_get_alerts_cache_key_no_filters(self):
        """Test cache key generation with no filters."""
        key = AlertCacheManager.get_alerts_cache_key(user_id=None, filters={})

        self.assertIn("alerts", key)
        # Key should be generated even with no filters
        self.assertIsInstance(key, str)
        self.assertGreater(len(key), 0)

    def test_get_alerts_cache_key_consistent(self):
        """Test that identical parameters generate identical cache keys."""
        filters = {"severity": "3", "search": "test", "page": 1}
        user_id = self.user.id

        key1 = AlertCacheManager.get_alerts_cache_key(user_id=user_id, filters=filters)
        key2 = AlertCacheManager.get_alerts_cache_key(user_id=user_id, filters=filters)

        self.assertEqual(key1, key2)

    def test_get_alerts_cache_key_different_for_different_params(self):
        """Test that different parameters generate different cache keys."""
        filters1 = {"severity": "3", "page": 1}
        filters2 = {"severity": "4", "page": 1}

        key1 = AlertCacheManager.get_alerts_cache_key(user_id=None, filters=filters1)
        key2 = AlertCacheManager.get_alerts_cache_key(user_id=self.user.id, filters=filters1)
        key3 = AlertCacheManager.get_alerts_cache_key(user_id=None, filters=filters2)

        self.assertNotEqual(key1, key2)
        self.assertNotEqual(key1, key3)
        self.assertNotEqual(key2, key3)

    def test_cache_alerts_stores_data(self):
        """Test that cache_alerts stores data in cache."""
        alerts_data = [
            {"id": self.alert.id, "title": "Test Alert", "severity": 3}
        ]
        filters = {"severity": "3"}

        AlertCacheManager.cache_alerts(alerts_data, None, filters)

        cached_data = AlertCacheManager.get_cached_alerts(None, filters)
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data["data"], alerts_data)

    def test_get_cached_alerts_retrieves_data(self):
        """Test that get_cached_alerts retrieves stored data."""
        alerts_data = [
            {"id": self.alert.id, "title": "Test Alert", "severity": 3}
        ]
        filters = {"severity": "3"}

        # Store data using cache_alerts method
        AlertCacheManager.cache_alerts(alerts_data, None, filters)

        # Retrieve data using get_cached_alerts method
        cached_data = AlertCacheManager.get_cached_alerts(None, filters)
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data["data"], alerts_data)

    def test_get_cached_alerts_returns_none_on_miss(self):
        """Test that get_cached_alerts returns None on cache miss."""
        filters = {"severity": "999"}  # Unlikely to exist

        cached_data = AlertCacheManager.get_cached_alerts(None, filters)
        self.assertIsNone(cached_data)

    def test_get_alert_detail_cache_key(self):
        """Test cache key generation for individual alerts."""
        key = AlertCacheManager.get_alert_detail_cache_key(self.alert.id)

        self.assertIn("alert", key)
        self.assertIn(str(self.alert.id), key)

    def test_cache_alert_detail_stores_data(self):
        """Test that cache_alert_detail stores alert data."""
        alert_data = {"id": self.alert.id, "title": "Test Alert"}

        AlertCacheManager.cache_alert_detail(alert_data, self.alert.id)

        cached_data = AlertCacheManager.get_cached_alert_detail(self.alert.id)
        self.assertEqual(cached_data, alert_data)

    def test_get_cached_alert_detail_retrieves_data(self):
        """Test that get_cached_alert_detail retrieves stored data."""
        alert_data = {"id": self.alert.id, "title": "Test Alert"}

        AlertCacheManager.cache_alert_detail(alert_data, self.alert.id)

        cached_data = AlertCacheManager.get_cached_alert_detail(self.alert.id)
        self.assertEqual(cached_data, alert_data)

    def test_get_stats_cache_key_anonymous(self):
        """Test cache key generation for statistics (anonymous)."""
        key = AlertCacheManager.get_stats_cache_key()

        self.assertIn("stats", key)

    def test_get_stats_cache_key_user_specific(self):
        """Test cache key generation for user-specific statistics."""
        key = AlertCacheManager.get_stats_cache_key(user_id=self.user.id)

        self.assertIn("stats", key)

    def test_cache_stats_stores_data(self):
        """Test that cache_stats stores statistics data."""
        stats_data = {
            "total_alerts": 10,
            "active_alerts": 8,
            "severity_distribution": {"3": 5, "4": 3, "5": 2}
        }

        AlertCacheManager.cache_stats(stats_data)

        cache_key = AlertCacheManager.get_stats_cache_key()
        cached_data = cache.get(cache_key)
        self.assertEqual(cached_data, stats_data)

    def test_cache_stats_with_user(self):
        """Test that cache_stats stores user-specific statistics."""
        stats_data = {
            "total_alerts": 5,
            "user_stats": {"bookmarked_count": 2}
        }

        AlertCacheManager.cache_stats(stats_data, user_id=self.user.id)

        cache_key = AlertCacheManager.get_stats_cache_key(user_id=self.user.id)
        cached_data = cache.get(cache_key)
        self.assertEqual(cached_data, stats_data)

    def test_get_cached_stats_retrieves_data(self):
        """Test that get_cached_stats retrieves stored data."""
        stats_data = {"total_alerts": 15}

        # Store using cache_stats method
        AlertCacheManager.cache_stats(stats_data)

        # Retrieve using get_cached_stats method
        cached_data = AlertCacheManager.get_cached_stats()
        self.assertEqual(cached_data, stats_data)

    def test_get_shock_types_cache_key(self):
        """Test cache key generation for shock types."""
        key = AlertCacheManager.get_shock_types_cache_key()

        self.assertIn("shock_types", key)

    def test_cache_shock_types_stores_data(self):
        """Test that cache_shock_types stores shock types data."""
        shock_types_data = [
            {"id": self.shock_type.id, "name": "Conflict", "icon": "fa-warning"}
        ]

        AlertCacheManager.cache_shock_types(shock_types_data)

        cache_key = AlertCacheManager.get_shock_types_cache_key()
        cached_data = cache.get(cache_key)
        self.assertEqual(cached_data, shock_types_data)

    def test_get_cached_shock_types_retrieves_data(self):
        """Test that get_cached_shock_types retrieves stored data."""
        shock_types_data = [
            {"id": self.shock_type.id, "name": "Conflict"}
        ]

        # Store using cache_shock_types method
        AlertCacheManager.cache_shock_types(shock_types_data)

        # Retrieve using get_cached_shock_types method
        cached_data = AlertCacheManager.get_cached_shock_types()
        self.assertEqual(cached_data, shock_types_data)

    def test_get_public_alerts_cache_key(self):
        """Test cache key generation for public alerts."""
        filters = {"severity": "4", "page": 3}

        key = AlertCacheManager.get_alerts_cache_key(user_id=None, filters=filters)

        self.assertIn("alerts", key)
        # Should not contain user-specific information

    def test_cache_public_alerts_stores_data(self):
        """Test that cache_alerts stores public alerts data."""
        alerts_data = [
            {"id": self.alert.id, "title": "Public Alert"}
        ]
        filters = {"severity": "3"}

        AlertCacheManager.cache_alerts(alerts_data, None, filters)

        cached_data = AlertCacheManager.get_cached_alerts(None, filters)
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data["data"], alerts_data)

    def test_get_cached_public_alerts_retrieves_data(self):
        """Test that get_cached_alerts retrieves stored public data."""
        alerts_data = [
            {"id": self.alert.id, "title": "Public Alert"}
        ]
        filters = {"shock_type": "1"}

        AlertCacheManager.cache_alerts(alerts_data, None, filters)

        cached_data = AlertCacheManager.get_cached_alerts(None, filters)
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data["data"], alerts_data)

    def test_invalidate_alert_caches(self):
        """Test that invalidate_alert_caches clears all cached data."""
        # Store data in various caches
        AlertCacheManager.cache_alerts([{"id": 1}], None, {"severity": "3"})
        AlertCacheManager.cache_stats({"total": 5})
        AlertCacheManager.cache_shock_types([{"id": 1}])
        AlertCacheManager.cache_alert_detail({"id": self.alert.id}, self.alert.id)

        # Verify data is cached
        self.assertIsNotNone(AlertCacheManager.get_cached_alerts(None, {"severity": "3"}))
        self.assertIsNotNone(AlertCacheManager.get_cached_stats())

        # Invalidate alert caches
        AlertCacheManager.invalidate_alert_caches()

        # Verify all data is cleared (due to test backend using cache.clear())
        self.assertIsNone(AlertCacheManager.get_cached_alerts(None, {"severity": "3"}))
        self.assertIsNone(AlertCacheManager.get_cached_stats())

    def test_invalidate_alert_caches_specific_alert(self):
        """Test that invalidate_alert_caches can target specific alert."""
        # Store data for specific alert
        alert_data = {"id": self.alert.id, "title": "Test Alert"}
        AlertCacheManager.cache_alert_detail(alert_data, self.alert.id)

        # Verify data is cached
        self.assertIsNotNone(AlertCacheManager.get_cached_alert_detail(self.alert.id))

        # Invalidate specific alert cache
        AlertCacheManager.invalidate_alert_caches(self.alert.id)

        # Verify alert cache is cleared (due to test backend using cache.clear())
        self.assertIsNone(AlertCacheManager.get_cached_alert_detail(self.alert.id))

    def test_invalidate_user_caches(self):
        """Test that invalidate_user_caches clears user caches."""
        # Store user-specific and general data
        user_filters = {"severity": "3"}
        general_filters = {"severity": "4"}

        AlertCacheManager.cache_alerts([{"id": 1}], self.user.id, user_filters)
        AlertCacheManager.cache_alerts([{"id": 2}], None, general_filters)
        AlertCacheManager.cache_stats({"user_total": 1}, self.user.id)

        # Verify both are cached
        self.assertIsNotNone(AlertCacheManager.get_cached_alerts(self.user.id, user_filters))
        self.assertIsNotNone(AlertCacheManager.get_cached_stats(self.user.id))

        # Invalidate user-specific caches
        AlertCacheManager.invalidate_user_caches(self.user.id)

        # Verify user-specific caches are cleared (due to test backend using cache.clear())
        self.assertIsNone(AlertCacheManager.get_cached_stats(self.user.id))

    def test_cache_timeout_configuration(self):
        """Test that cache timeouts are properly configured."""
        self.assertGreater(AlertCacheManager.ALERTS_CACHE_TIMEOUT, 0)
        self.assertGreater(AlertCacheManager.USER_DATA_CACHE_TIMEOUT, 0)
        self.assertGreater(AlertCacheManager.STATS_CACHE_TIMEOUT, 0)
        self.assertGreater(AlertCacheManager.SHOCK_TYPES_CACHE_TIMEOUT, 0)

        # Verify reasonable timeout values
        self.assertLess(AlertCacheManager.STATS_CACHE_TIMEOUT, 3600)  # Less than 1 hour
        self.assertGreater(AlertCacheManager.SHOCK_TYPES_CACHE_TIMEOUT, 600)  # More than 10 minutes

    def test_cache_key_length_reasonable(self):
        """Test that cache keys are not excessively long."""
        # Test with complex filters
        complex_filters = {
            "severity": "5",
            "shock_type": "1",
            "search": "long search term",
            "date_from": "2024-01-01",
            "date_to": "2024-12-31"
        }

        complex_filters["page"] = 999
        key = AlertCacheManager.get_alerts_cache_key(
            user_id=self.user.id,
            filters=complex_filters
        )

        # Cache keys should be reasonable length (under 250 chars for Redis)
        self.assertLess(len(key), 250)

    def test_cache_key_special_characters(self):
        """Test that cache keys handle special characters properly."""
        filters = {
            "search": "special chars: @#$%^&*()",
            "severity": "3"
        }

        # Should not raise exception
        key = AlertCacheManager.get_alerts_cache_key(user_id=None, filters=filters)
        self.assertIsInstance(key, str)
        self.assertGreater(len(key), 0)

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def test_graceful_handling_of_cache_unavailable(self):
        """Test graceful handling when cache backend is unavailable."""
        # With dummy cache, operations should not raise exceptions
        alerts_data = [{"id": 1, "title": "Test"}]
        filters = {"test": "true"}

        # These should not raise exceptions
        AlertCacheManager.cache_alerts(alerts_data, None, filters)
        result = AlertCacheManager.get_cached_alerts(None, filters)
        self.assertIsNone(result)  # Dummy cache always returns None

        AlertCacheManager.invalidate_alert_caches()  # Should not raise

    def test_filter_ordering_consistency(self):
        """Test that filter dictionary ordering doesn't affect cache keys."""
        filters1 = {"severity": "3", "shock_type": "1", "search": "test"}
        filters2 = {"search": "test", "severity": "3", "shock_type": "1"}

        key1 = AlertCacheManager.get_alerts_cache_key(user_id=None, filters=filters1)
        key2 = AlertCacheManager.get_alerts_cache_key(user_id=None, filters=filters2)

        # Keys should be identical regardless of filter ordering
        self.assertEqual(key1, key2)


class CacheInvalidationSignalsTest(TestCase):
    """Tests for cache invalidation signals."""

    def setUp(self):
        """Set up test data."""
        cache.clear()

        self.shock_type = ShockType.objects.create(
            name="Conflict",
            icon="fa-warning",
            color="#ff0000"
        )

        self.data_source = Source.objects.create(
            name="Test Source",
            description="Test data source for signal tests",
            is_active=True
        )

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    @patch('alerts.cache.AlertCacheManager.invalidate_alert_caches')
    def test_alert_creation_triggers_invalidation(self, mock_invalidate):
        """Test that creating an alert triggers cache invalidation."""
        # Create an alert (should trigger post_save signal)
        Alert.objects.create(
            title="New Alert",
            text="New alert content",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=3,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            go_no_go=True
        )

        # Verify invalidation was called
        mock_invalidate.assert_called_once()

    @patch('alerts.cache.AlertCacheManager.invalidate_alert_caches')
    def test_alert_update_triggers_invalidation(self, mock_invalidate):
        """Test that updating an alert triggers cache invalidation."""
        # Create alert first
        alert = Alert.objects.create(
            title="Original Alert",
            text="Original content",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=2,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=4),
            go_no_go=True
        )

        # Clear previous calls
        mock_invalidate.reset_mock()

        # Update alert (should trigger post_save signal)
        alert.title = "Updated Alert"
        alert.save()

        # Verify invalidation was called
        mock_invalidate.assert_called_once()

    @patch('alerts.cache.AlertCacheManager.invalidate_alert_caches')
    def test_alert_deletion_triggers_invalidation(self, mock_invalidate):
        """Test that deleting an alert triggers cache invalidation."""
        # Create alert
        alert = Alert.objects.create(
            title="To Delete",
            text="Will be deleted",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=1,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=2),
            go_no_go=True
        )

        # Clear previous calls
        mock_invalidate.reset_mock()

        # Delete alert (should trigger post_delete signal)
        alert.delete()

        # Verify invalidation was called
        mock_invalidate.assert_called_once()

    @patch('alerts.cache.AlertCacheManager.invalidate_alert_caches')
    def test_shock_type_update_triggers_invalidation(self, mock_invalidate):
        """Test that updating a shock type triggers cache invalidation."""
        # Update shock type (should trigger post_save signal)
        self.shock_type.name = "Updated Conflict"
        self.shock_type.save()

        # Verify invalidation was called
        mock_invalidate.assert_called_once()

    @patch('alerts.cache.AlertCacheManager.invalidate_user_caches')
    def test_user_alert_update_triggers_user_cache_invalidation(self, mock_invalidate_user):
        """Test that updating UserAlert triggers user-specific cache invalidation."""
        user = User.objects.create_user(username="testuser", password="pass123")
        alert = Alert.objects.create(
            title="Test Alert",
            text="Test content",
            shock_type=self.shock_type,
            data_source=self.data_source,
            severity=3,
            shock_date=timezone.now(),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=5),
            go_no_go=True
        )

        # Create UserAlert (should trigger post_save signal)
        UserAlert.objects.create(
            user=user,
            alert=alert,
            rating=4,
            received_at=timezone.now()
        )

        # Verify user-specific invalidation was called
        mock_invalidate_user.assert_called_with(user.id)

    def test_signal_handlers_registered(self):
        """Test that signal handlers are properly registered."""
        from django.db.models.signals import post_delete, post_save

        # Check that signals have listeners
        post_save_receivers = post_save._live_receivers(sender=Alert)
        post_delete_receivers = post_delete._live_receivers(sender=Alert)

        # Should have at least one receiver for each signal
        self.assertGreater(len(post_save_receivers), 0)
        self.assertGreater(len(post_delete_receivers), 0)

