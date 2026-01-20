"""Caching implementation for LLM responses."""

import hashlib
import logging
from datetime import timedelta
from typing import Optional, Dict, Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .exceptions import CacheError
from .models import CachedResponse

logger = logging.getLogger(__name__)


class LLMCache:
    """Cache manager for LLM responses."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the cache manager.

        Args:
            config: Cache configuration
        """
        default_config = {
            "ENABLED": True,
            "TTL_SECONDS": 3600,  # 1 hour
            "MAX_SIZE_MB": 100,
            "USE_DATABASE": True,
            "USE_REDIS": True,
        }

        # Get configuration from Django settings or use defaults
        llm_config = getattr(settings, "LLM_SERVICE", {})
        cache_config = llm_config.get("CACHE", {})

        self.config = {**default_config, **(config or {}), **cache_config}

    def generate_cache_key(self, prompt: str, provider: str, model: str, **kwargs) -> str:
        """Generate a cache key for a query.

        Args:
            prompt: The query prompt
            provider: Provider name
            model: Model name
            **kwargs: Additional parameters that affect the response

        Returns:
            SHA-256 hash as cache key
        """
        # Include all parameters that might affect the response
        cache_params = {
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens"),
            "system": kwargs.get("system"),
            # Add other relevant parameters
        }

        # Remove None values
        cache_params = {k: v for k, v in cache_params.items() if v is not None}

        # Create a consistent string representation
        cache_string = str(sorted(cache_params.items()))

        # Generate SHA-256 hash
        return hashlib.sha256(cache_string.encode("utf-8")).hexdigest()

    def get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response by key.

        Args:
            cache_key: The cache key

        Returns:
            Cached response or None if not found
        """
        if not self.config["ENABLED"]:
            return None

        try:
            # Try Redis cache first (faster)
            if self.config["USE_REDIS"]:
                cached_data = cache.get(f"llm_query:{cache_key}")
                if cached_data:
                    logger.debug(f"Cache hit (Redis): {cache_key[:8]}...")
                    return cached_data

            # Try database cache
            if self.config["USE_DATABASE"]:
                try:
                    cached_response = CachedResponse.objects.get(cache_key=cache_key)

                    # Check if expired
                    if cached_response.is_expired():
                        logger.debug(f"Cache expired: {cache_key[:8]}...")
                        cached_response.delete()
                        return None

                    # Update hit count and return response
                    cached_response.increment_hit_count()

                    # Also cache in Redis for faster future access
                    if self.config["USE_REDIS"]:
                        remaining_ttl = int((cached_response.expires_at - timezone.now()).total_seconds())
                        if remaining_ttl > 0:
                            cache.set(f"llm_query:{cache_key}", cached_response.response_text, timeout=remaining_ttl)

                    logger.debug(f"Cache hit (DB): {cache_key[:8]}...")
                    return cached_response.response_text

                except CachedResponse.DoesNotExist:
                    pass

        except Exception as e:
            logger.error(f"Cache retrieval error: {e}")

        return None

    def cache_response(
        self, cache_key: str, response: str, provider: str, model: str, metadata: Dict[str, Any] = None, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Cache a response.

        Args:
            cache_key: The cache key
            response: The response to cache
            provider: Provider name
            model: Model name
            metadata: Additional metadata to store
            ttl_seconds: Custom TTL in seconds

        Returns:
            True if caching succeeded
        """
        if not self.config["ENABLED"]:
            return False

        try:
            ttl = ttl_seconds or self.config["TTL_SECONDS"]
            expires_at = timezone.now() + timedelta(seconds=ttl)

            # Cache in Redis
            if self.config["USE_REDIS"]:
                cache.set(f"llm_query:{cache_key}", response, timeout=ttl)

            # Cache in database
            if self.config["USE_DATABASE"]:
                CachedResponse.objects.update_or_create(
                    cache_key=cache_key,
                    defaults={
                        "provider": provider,
                        "model": model,
                        "response_text": response,
                        "response_metadata": metadata or {},
                        "expires_at": expires_at,
                        "hit_count": 0,
                    },
                )

            logger.debug(f"Response cached: {cache_key[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Cache storage error: {e}")
            return False

    def invalidate_cache_key(self, cache_key: str) -> bool:
        """Invalidate a specific cache key.

        Args:
            cache_key: The cache key to invalidate

        Returns:
            True if invalidation succeeded
        """
        try:
            # Remove from Redis
            if self.config["USE_REDIS"]:
                cache.delete(f"llm_query:{cache_key}")

            # Remove from database
            if self.config["USE_DATABASE"]:
                CachedResponse.objects.filter(cache_key=cache_key).delete()

            return True

        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return False

    def clear_expired_cache(self) -> int:
        """Clear expired cache entries from database.

        Returns:
            Number of entries cleared
        """
        if not self.config["USE_DATABASE"]:
            return 0

        try:
            count = CachedResponse.objects.filter(expires_at__lt=timezone.now()).count()
            CachedResponse.objects.filter(expires_at__lt=timezone.now()).delete()
            logger.info(f"Cleared {count} expired cache entries")
            return count

        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            stats = {"enabled": self.config["ENABLED"], "use_redis": self.config["USE_REDIS"], "use_database": self.config["USE_DATABASE"]}

            if self.config["USE_DATABASE"]:
                from django.db.models import Count, Sum, Q

                db_stats = CachedResponse.objects.aggregate(
                    total_entries=Count("id"), total_hits=Sum("hit_count"), expired_entries=Count("id", filter=Q(expires_at__lt=timezone.now()))
                )

                stats.update(db_stats)

            return stats

        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {"error": str(e)}