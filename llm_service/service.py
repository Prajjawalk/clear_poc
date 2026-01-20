"""Main LLM service implementation."""

import hashlib
import logging
import time
from typing import Any, Dict, Generator, Optional

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from .cache import LLMCache
from .exceptions import LLMServiceError, ProviderNotFoundError, QueryError
from .models import QueryLog
from .rate_limiter import LLMRateLimiter
from .registry import get_registry

logger = logging.getLogger(__name__)


class LLMService:
    """Main service interface for LLM queries."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the LLM service.

        Args:
            config: Service configuration override
        """
        # Get configuration from Django settings
        default_config = {"DEFAULT_PROVIDER": "litellm", "PROVIDERS": {}, "CACHE": {"ENABLED": True}, "RATE_LIMITS": {"ENABLED": True}}

        llm_config = getattr(settings, "LLM_SERVICE", {})
        self.config = {**default_config, **llm_config, **(config or {})}

        # Initialize components
        self.cache = LLMCache(self.config.get("CACHE"))
        self.rate_limiter = LLMRateLimiter(self.config.get("RATE_LIMITS"))
        self.registry = get_registry()

    def query(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        user: Optional[User] = None,
        application: str = "default",
        cache: bool = True,
        **kwargs,
    ) -> str:
        """Send a query to an LLM and return the response.

        Args:
            prompt: The input prompt
            provider: Provider name (uses default if None)
            model: Model name (uses provider default if None)
            user: User making the request
            application: Application identifier
            cache: Whether to use caching
            **kwargs: Additional provider-specific parameters

        Returns:
            The LLM response

        Raises:
            RateLimitError: If rate limits exceeded
            ProviderNotFoundError: If provider not found
            QueryError: If query fails
        """
        start_time = time.time()
        provider_name = provider or self._get_default_provider()
        cache_hit = False

        try:
            # Get provider configuration from database
            provider_config_obj, provider_config = self._get_provider_config_with_obj(provider_name)
            actual_model = model or provider_config.get("MODEL", "default")

            # Generate cache key
            cache_key = self.cache.generate_cache_key(prompt, provider_name, actual_model, **kwargs) if cache else None

            # Check cache first
            cached_response = None
            if cache and cache_key:
                cached_response = self.cache.get_cached_response(cache_key)
                if cached_response:
                    cache_hit = True
                    response = cached_response

            if not cached_response:
                # Check rate limits
                estimated_tokens = self._estimate_request_tokens(prompt, **kwargs)
                self.rate_limiter.check_all_limits(tokens=estimated_tokens, user=user)

                # Get provider instance
                provider_type = provider_config.get('PROVIDER_TYPE', 'litellm')
                provider_instance = self.registry.get_provider_instance(provider_type, provider_config)

                # Execute query
                response = provider_instance.query(prompt, model=actual_model, **kwargs)

                # Cache response if enabled
                if cache and cache_key:
                    response_metadata = {
                        "model": actual_model,
                        "provider": provider_name,
                        "tokens_estimated": estimated_tokens,
                        "user_id": user.id if user else None,
                        "application": application,
                    }
                    self.cache.cache_response(cache_key, response, provider_name, actual_model, response_metadata)

            # Log the query
            self._log_query(
                prompt=prompt,
                response=response,
                provider=provider_name,
                model=actual_model,
                user=user,
                application=application,
                response_time_ms=int((time.time() - start_time) * 1000),
                cache_hit=cache_hit,
                success=True,
                **kwargs,
            )

            return response

        except Exception as e:
            # Log failed query
            self._log_query(
                prompt=prompt,
                response="",
                provider=provider_name,
                model=model or "unknown",
                user=user,
                application=application,
                response_time_ms=int((time.time() - start_time) * 1000),
                cache_hit=False,
                success=False,
                error=str(e),
                **kwargs,
            )
            raise

    def stream_query(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        user: Optional[User] = None,
        application: str = "default",
        **kwargs,
    ) -> Generator[str, None, None]:
        """Stream a response from an LLM.

        Args:
            prompt: The input prompt
            provider: Provider name
            model: Model name
            user: User making the request
            application: Application identifier
            **kwargs: Additional parameters

        Yields:
            Response chunks
        """
        start_time = time.time()
        provider_name = provider or self._get_default_provider()

        try:
            # Get provider configuration from database
            provider_config_obj, provider_config = self._get_provider_config_with_obj(provider_name)
            actual_model = model or provider_config.get("MODEL", "default")

            # Check rate limits
            estimated_tokens = self._estimate_request_tokens(prompt, **kwargs)
            self.rate_limiter.check_all_limits(tokens=estimated_tokens, user=user)

            # Get provider instance
            provider_type = provider_config.get('PROVIDER_TYPE', 'litellm')
            provider_instance = self.registry.get_provider_instance(provider_type, provider_config)

            # Stream response
            full_response = ""
            for chunk in provider_instance.stream_query(prompt, model=actual_model, **kwargs):
                full_response += chunk
                yield chunk

            # Log the query
            self._log_query(
                prompt=prompt,
                response=full_response,
                provider=provider_name,
                model=actual_model,
                user=user,
                application=application,
                response_time_ms=int((time.time() - start_time) * 1000),
                cache_hit=False,
                success=True,
                **kwargs,
            )

        except Exception as e:
            # Log failed query
            self._log_query(
                prompt=prompt,
                response="",
                provider=provider_name,
                model=model or "unknown",
                user=user,
                application=application,
                response_time_ms=int((time.time() - start_time) * 1000),
                cache_hit=False,
                success=False,
                error=str(e),
                **kwargs,
            )
            raise

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers from database.

        Returns:
            Dictionary with provider status information
        """
        from .models import ProviderConfig

        status = {"providers": []}

        # Get all active providers from database
        for provider_config in ProviderConfig.objects.filter(is_active=True).order_by('-priority'):
            provider_name = provider_config.provider_name

            try:
                # Get the provider type from config or default to 'litellm'
                provider_type = provider_config.config.get('PROVIDER_TYPE', 'litellm')

                # Get provider instance
                provider_instance = self.registry.get_provider_instance(provider_type, provider_config.config)
                provider_info = provider_instance.get_info()

                # Update with database config info
                provider_info.update({
                    "name": provider_name,
                    "type": provider_type,
                    "active": provider_config.is_active,
                    "configured": True,
                    "priority": provider_config.priority,
                    "rate_limit": provider_config.rate_limit,
                    "token_limit": provider_config.token_limit,
                    "model": provider_config.config.get('MODEL', 'Unknown'),
                })

                status["providers"].append(provider_info)

            except Exception as e:
                logger.error(f"Error getting status for provider {provider_name}: {e}")
                status["providers"].append({
                    "name": provider_name,
                    "type": provider_config.config.get('PROVIDER_TYPE', 'unknown'),
                    "active": False,
                    "configured": False,
                    "error": str(e),
                    "model": provider_config.config.get('MODEL', 'Unknown'),
                })

        return status

    def get_service_stats(self, period: str = "day") -> Dict[str, Any]:
        """Get service usage statistics.

        Args:
            period: Time period (day, week, month)

        Returns:
            Dictionary with usage statistics
        """
        try:
            from django.db.models import Count, Sum, Avg, Q
            from datetime import timedelta

            now = timezone.now()
            if period == "day":
                since = now - timedelta(days=1)
            elif period == "week":
                since = now - timedelta(weeks=1)
            elif period == "month":
                since = now - timedelta(days=30)
            else:
                since = now - timedelta(days=1)

            stats = QueryLog.objects.filter(created_at__gte=since).aggregate(
                total_queries=Count("id"),
                successful_queries=Count("id", filter=Q(success=True)),
                total_tokens=Sum("total_tokens"),
                avg_response_time_ms=Avg("response_time_ms"),
            )

            # Add cache statistics
            cache_stats = self.cache.get_cache_stats()
            stats.update({"cache": cache_stats})

            # Add provider breakdown
            provider_stats = (
                QueryLog.objects.filter(created_at__gte=since).values("provider").annotate(queries=Count("id"), avg_time=Avg("response_time_ms"))
            )

            stats.update({"providers": list(provider_stats), "period": period})

            return stats

        except Exception as e:
            logger.error(f"Error getting service stats: {e}")
            return {"error": str(e)}

    def _get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """Get configuration for a provider from database.

        Args:
            provider_name: Provider name

        Returns:
            Provider configuration

        Raises:
            ProviderNotFoundError: If provider not configured
        """
        from .models import ProviderConfig

        try:
            provider_config = ProviderConfig.objects.get(provider_name=provider_name, is_active=True)
            return provider_config.config
        except ProviderConfig.DoesNotExist:
            raise ProviderNotFoundError(f"Provider '{provider_name}' not found or not active")

    def _get_provider_config_with_obj(self, provider_name: str):
        """Get provider configuration and object from database.

        Args:
            provider_name: Provider name

        Returns:
            Tuple of (ProviderConfig object, config dict)

        Raises:
            ProviderNotFoundError: If provider not configured
        """
        from .models import ProviderConfig

        try:
            provider_config_obj = ProviderConfig.objects.get(provider_name=provider_name, is_active=True)
            return provider_config_obj, provider_config_obj.config
        except ProviderConfig.DoesNotExist:
            raise ProviderNotFoundError(f"Provider '{provider_name}' not found or not active")

    def _get_default_provider(self) -> str:
        """Get the default provider from database (highest priority active provider).

        Returns:
            Provider name

        Raises:
            ProviderNotFoundError: If no active providers
        """
        from .models import ProviderConfig

        try:
            default_provider = ProviderConfig.objects.filter(is_active=True).order_by('-priority').first()
            if not default_provider:
                raise ProviderNotFoundError("No active providers configured")
            return default_provider.provider_name
        except Exception as e:
            raise ProviderNotFoundError(f"Error getting default provider: {str(e)}")

    def _estimate_request_tokens(self, prompt: str, **kwargs) -> int:
        """Estimate tokens for rate limiting.

        Args:
            prompt: The prompt text
            **kwargs: Additional parameters

        Returns:
            Estimated token count
        """
        # Simple estimation (will be overridden by provider-specific estimation)
        base_tokens = len(prompt) // 4

        # Add system message tokens if present
        system = kwargs.get("system")
        if system:
            base_tokens += len(system) // 4

        # Add max_tokens for output if specified
        max_tokens = kwargs.get("max_tokens", 0)
        if max_tokens:
            base_tokens += max_tokens

        return max(base_tokens, 1)

    def _log_query(
        self,
        prompt: str,
        response: str,
        provider: str,
        model: str,
        user: Optional[User],
        application: str,
        response_time_ms: int,
        cache_hit: bool,
        success: bool,
        error: Optional[str] = None,
        **kwargs,
    ):
        """Log a query for audit and analysis.

        Args:
            prompt: The prompt
            response: The response
            provider: Provider name
            model: Model name
            user: User who made the request
            application: Application identifier
            response_time_ms: Response time in milliseconds
            cache_hit: Whether this was a cache hit
            success: Whether the query succeeded
            error: Error message if failed
            **kwargs: Additional metadata
        """
        try:
            # Generate prompt hash for privacy
            prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

            # Estimate tokens (simplified)
            tokens_input = len(prompt) // 4
            tokens_output = len(response) // 4 if response else 0
            total_tokens = tokens_input + tokens_output

            # Get logging settings from config
            log_content = self.config.get("LOG_CONTENT", True)  # Default to True for now

            # Create log entry
            QueryLog.objects.create(
                provider=provider,
                model=model,
                prompt_hash=prompt_hash,
                prompt_text=prompt if log_content else None,
                response_text=response if log_content and success else None,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                total_tokens=total_tokens,
                response_time_ms=response_time_ms,
                success=success,
                error_message=error,
                user=user,
                application=application,
                metadata={
                    "cache_hit": cache_hit,
                    "kwargs": {k: v for k, v in kwargs.items() if k not in ["prompt", "response"]},
                },
            )

        except Exception as e:
            # Don't fail the main request if logging fails
            logger.error(f"Failed to log query: {e}")