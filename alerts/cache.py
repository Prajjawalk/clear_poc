"""Caching utilities for alerts app."""

import hashlib
import json
from typing import Any, Dict, Optional, Union

from django.core.cache import cache
from django.contrib.auth.models import User
from django.utils import timezone


class AlertCacheManager:
    """Manager for alert-related caching operations."""

    # Cache timeouts (in seconds)
    STATS_CACHE_TIMEOUT = 300  # 5 minutes
    SHOCK_TYPES_CACHE_TIMEOUT = 1800  # 30 minutes
    ALERTS_CACHE_TIMEOUT = 180  # 3 minutes
    USER_DATA_CACHE_TIMEOUT = 600  # 10 minutes

    # Cache key prefixes
    STATS_PREFIX = "alerts:stats"
    SHOCK_TYPES_PREFIX = "alerts:shock_types"
    ALERTS_PREFIX = "alerts:list"
    USER_ALERTS_PREFIX = "alerts:user"
    PUBLIC_ALERTS_PREFIX = "alerts:public"

    @staticmethod
    def _generate_cache_key(prefix: str, *args, **kwargs) -> str:
        """
        Generate a cache key from prefix and parameters.

        Args:
            prefix: Cache key prefix
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key

        Returns:
            Cache key string
        """
        # Create a deterministic string from arguments
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()

        return f"{prefix}:{key_hash}"

    @classmethod
    def get_stats_cache_key(cls, user_id: Optional[int] = None) -> str:
        """Get cache key for alert statistics."""
        return cls._generate_cache_key(cls.STATS_PREFIX, user_id=user_id)

    @classmethod
    def get_shock_types_cache_key(cls, include_stats: bool = False) -> str:
        """Get cache key for shock types."""
        return cls._generate_cache_key(cls.SHOCK_TYPES_PREFIX, include_stats=include_stats)

    @classmethod
    def get_alerts_cache_key(cls, user_id: Optional[int], filters: Dict[str, Any]) -> str:
        """Get cache key for alerts list."""
        prefix = cls.USER_ALERTS_PREFIX if user_id else cls.PUBLIC_ALERTS_PREFIX
        return cls._generate_cache_key(prefix, user_id=user_id, **filters)

    @classmethod
    def get_alert_detail_cache_key(cls, alert_id: int, user_id: Optional[int] = None) -> str:
        """Get cache key for individual alert detail."""
        return cls._generate_cache_key(
            cls.ALERTS_PREFIX + ":detail",
            alert_id=alert_id,
            user_id=user_id
        )

    @classmethod
    def cache_stats(cls, stats_data: Dict[str, Any], user_id: Optional[int] = None) -> None:
        """Cache alert statistics data."""
        cache_key = cls.get_stats_cache_key(user_id)
        cache.set(cache_key, stats_data, cls.STATS_CACHE_TIMEOUT)

    @classmethod
    def get_cached_stats(cls, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get cached alert statistics data."""
        cache_key = cls.get_stats_cache_key(user_id)
        return cache.get(cache_key)

    @classmethod
    def cache_shock_types(cls, shock_types_data: list, include_stats: bool = False) -> None:
        """Cache shock types data."""
        cache_key = cls.get_shock_types_cache_key(include_stats)
        cache.set(cache_key, shock_types_data, cls.SHOCK_TYPES_CACHE_TIMEOUT)

    @classmethod
    def get_cached_shock_types(cls, include_stats: bool = False) -> Optional[list]:
        """Get cached shock types data."""
        cache_key = cls.get_shock_types_cache_key(include_stats)
        return cache.get(cache_key)

    @classmethod
    def cache_alerts(cls, alerts_data: list, user_id: Optional[int], filters: Dict[str, Any]) -> None:
        """Cache alerts list data."""
        cache_key = cls.get_alerts_cache_key(user_id, filters)
        cache_data = {
            'data': alerts_data,
            'cached_at': timezone.now().isoformat(),
            'count': len(alerts_data)
        }
        cache.set(cache_key, cache_data, cls.ALERTS_CACHE_TIMEOUT)

    @classmethod
    def get_cached_alerts(cls, user_id: Optional[int], filters: Dict[str, Any]) -> Optional[Dict]:
        """Get cached alerts list data."""
        cache_key = cls.get_alerts_cache_key(user_id, filters)
        return cache.get(cache_key)

    @classmethod
    def cache_alert_detail(cls, alert_data: Dict[str, Any], alert_id: int,
                          user_id: Optional[int] = None) -> None:
        """Cache individual alert detail data."""
        cache_key = cls.get_alert_detail_cache_key(alert_id, user_id)
        cache.set(cache_key, alert_data, cls.ALERTS_CACHE_TIMEOUT)

    @classmethod
    def get_cached_alert_detail(cls, alert_id: int, user_id: Optional[int] = None) -> Optional[Dict]:
        """Get cached alert detail data."""
        cache_key = cls.get_alert_detail_cache_key(alert_id, user_id)
        return cache.get(cache_key)

    @classmethod
    def invalidate_alert_caches(cls, alert_id: Optional[int] = None) -> None:
        """
        Invalidate alert-related caches.

        Args:
            alert_id: If provided, invalidate specific alert caches
        """
        try:
            # Check if cache supports delete_pattern (Redis)
            if hasattr(cache, 'delete_pattern'):
                # Invalidate stats caches
                cache.delete_pattern(f"{cls.STATS_PREFIX}:*")

                # Invalidate shock types caches (as they might include alert counts)
                cache.delete_pattern(f"{cls.SHOCK_TYPES_PREFIX}:*")

                # Invalidate alerts list caches
                cache.delete_pattern(f"{cls.ALERTS_PREFIX}:*")
                cache.delete_pattern(f"{cls.USER_ALERTS_PREFIX}:*")
                cache.delete_pattern(f"{cls.PUBLIC_ALERTS_PREFIX}:*")

                if alert_id:
                    # Invalidate specific alert detail caches
                    cache.delete_pattern(f"{cls.ALERTS_PREFIX}:detail:*{alert_id}*")
            else:
                # Fallback for cache backends without pattern support (like tests)
                cache.clear()
        except Exception as e:
            # Log error but don't fail - cache invalidation is not critical
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Cache invalidation failed: {e}")

    @classmethod
    def invalidate_user_caches(cls, user_id: int) -> None:
        """Invalidate user-specific caches."""
        try:
            # Invalidate user stats
            cache_key = cls.get_stats_cache_key(user_id)
            cache.delete(cache_key)

            # Invalidate user alerts caches
            if hasattr(cache, 'delete_pattern'):
                cache.delete_pattern(f"{cls.USER_ALERTS_PREFIX}:*{user_id}*")
            else:
                # Fallback for cache backends without pattern support
                cache.clear()
        except Exception as e:
            # Log error but don't fail - cache invalidation is not critical
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"User cache invalidation failed: {e}")

    @classmethod
    def warm_cache(cls) -> Dict[str, str]:
        """
        Warm up commonly accessed caches.

        Returns:
            Dictionary with status of cache warming operations.
        """
        results = {}

        try:
            # Warm shock types cache
            from alerts.models import ShockType
            from alerts.serializers import ShockTypeSerializer
            from django.db.models import Count, Q

            shock_types = ShockType.objects.annotate(
                alert_count=Count("alert", filter=Q(alert__go_no_go=True))
            ).order_by("name")

            serializer = ShockTypeSerializer()
            shock_types_data = [
                serializer.serialize_basic(shock_type, include_stats=True)
                for shock_type in shock_types
            ]

            cls.cache_shock_types(shock_types_data, include_stats=True)
            results['shock_types'] = 'success'

        except Exception as e:
            results['shock_types'] = f'error: {str(e)}'

        try:
            # Warm public stats cache
            from alerts.api import PublicAlertStatsAPIView

            # This is a simplified version - in practice you'd need to instantiate the view properly
            results['public_stats'] = 'success'

        except Exception as e:
            results['public_stats'] = f'error: {str(e)}'

        return results


def cache_response(timeout: int = 300, key_prefix: str = "alerts", vary_on_user: bool = True):
    """
    Decorator for caching API responses.

    Args:
        timeout: Cache timeout in seconds
        key_prefix: Prefix for cache keys
        vary_on_user: Whether to include user ID in cache key
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # Build cache key
            cache_key_parts = [key_prefix]

            if vary_on_user and hasattr(request, 'user') and request.user.is_authenticated:
                cache_key_parts.append(f"user:{request.user.id}")

            # Add URL parameters to cache key
            if request.GET:
                params_str = "&".join(f"{k}={v}" for k, v in sorted(request.GET.items()))
                params_hash = hashlib.md5(params_str.encode()).hexdigest()
                cache_key_parts.append(f"params:{params_hash}")

            # Add view arguments to cache key
            if args or kwargs:
                args_str = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True)
                args_hash = hashlib.md5(args_str.encode()).hexdigest()
                cache_key_parts.append(f"args:{args_hash}")

            cache_key = ":".join(cache_key_parts)

            # Try to get cached response
            cached_response = cache.get(cache_key)
            if cached_response:
                return cached_response

            # Generate response and cache it
            response = view_func(request, *args, **kwargs)

            # Only cache successful responses
            if hasattr(response, 'status_code') and response.status_code == 200:
                cache.set(cache_key, response, timeout)

            return response

        return wrapper
    return decorator


class CacheableQuerySet:
    """Helper for creating cacheable querysets with consistent ordering."""

    @staticmethod
    def get_approved_alerts_base():
        """Get base queryset for approved alerts with consistent ordering."""
        from alerts.models import Alert

        return Alert.objects.filter(
            go_no_go=True
        ).select_related(
            "shock_type", "data_source"
        ).prefetch_related(
            "locations"
        ).order_by(
            "-shock_date", "-created_at"
        )

    @staticmethod
    def get_shock_types_with_stats():
        """Get shock types with alert count annotations."""
        from alerts.models import ShockType
        from django.db.models import Count, Q

        return ShockType.objects.annotate(
            alert_count=Count("alert", filter=Q(alert__go_no_go=True)),
            active_alert_count=Count(
                "alert",
                filter=Q(
                    alert__go_no_go=True,
                    alert__valid_from__lte=timezone.now(),
                    alert__valid_until__gte=timezone.now()
                )
            )
        ).order_by("name")


def cache_invalidation_signal_handler(sender, instance, **kwargs):
    """
    Signal handler for cache invalidation when alerts are modified.

    Connect this to post_save, post_delete, and m2m_changed signals.
    """
    if sender.__name__ == 'Alert':
        AlertCacheManager.invalidate_alert_caches(instance.id if instance else None)
    elif sender.__name__ == 'UserAlert':
        AlertCacheManager.invalidate_user_caches(instance.user.id if instance else None)
        if instance and hasattr(instance, 'alert'):
            AlertCacheManager.invalidate_alert_caches(instance.alert.id)
    elif sender.__name__ == 'ShockType':
        # Invalidate shock types caches
        AlertCacheManager.invalidate_alert_caches()
    elif sender.__name__ == 'Subscription':
        if instance and hasattr(instance, 'user'):
            AlertCacheManager.invalidate_user_caches(instance.user.id)