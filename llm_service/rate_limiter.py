"""Rate limiting implementation for LLM queries."""

import time
import logging
from typing import Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User

from .exceptions import RateLimitError

logger = logging.getLogger(__name__)


class LLMRateLimiter:
    """Rate limiter for LLM queries."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the rate limiter.

        Args:
            config: Rate limiting configuration
        """
        default_config = {
            "ENABLED": True,
            "GLOBAL_RPM": 100,  # Global requests per minute
            "USER_RPM": 20,  # Per-user requests per minute
            "TOKEN_DAILY_LIMIT": 1000000,  # Daily token limit
            "WINDOW_SIZE": 60,  # Window size in seconds
        }

        # Get configuration from Django settings or use defaults
        llm_config = getattr(settings, "LLM_SERVICE", {})
        rate_config = llm_config.get("RATE_LIMITS", {})

        self.config = {**default_config, **(config or {}), **rate_config}

    def _get_cache_key(self, key_type: str, identifier: str) -> str:
        """Generate cache key for rate limiting.

        Args:
            key_type: Type of limit (global, user, token)
            identifier: Identifier (user_id, etc.)

        Returns:
            Cache key
        """
        return f"llm_rate_limit:{key_type}:{identifier}"

    def _get_current_window(self, window_size: int = None) -> int:
        """Get current time window.

        Args:
            window_size: Window size in seconds

        Returns:
            Current window timestamp
        """
        window_size = window_size or self.config["WINDOW_SIZE"]
        return int(time.time() // window_size)

    def check_global_limit(self) -> bool:
        """Check global rate limit.

        Returns:
            True if within limit

        Raises:
            RateLimitError: If limit exceeded
        """
        if not self.config["ENABLED"]:
            return True

        window = self._get_current_window()
        cache_key = self._get_cache_key("global", str(window))

        try:
            current_count = cache.get(cache_key, 0)

            if current_count >= self.config["GLOBAL_RPM"]:
                raise RateLimitError(f"Global rate limit exceeded ({current_count}/{self.config['GLOBAL_RPM']} requests per minute)")

            # Increment counter
            cache.set(cache_key, current_count + 1, timeout=self.config["WINDOW_SIZE"])
            return True

        except Exception as e:
            if isinstance(e, RateLimitError):
                raise
            logger.error(f"Global rate limit check error: {e}")
            return True  # Allow request if rate limiting fails

    def check_user_limit(self, user: Optional[User] = None, user_id: Optional[int] = None) -> bool:
        """Check per-user rate limit.

        Args:
            user: User instance
            user_id: User ID

        Returns:
            True if within limit

        Raises:
            RateLimitError: If limit exceeded
        """
        if not self.config["ENABLED"]:
            return True

        if not user and not user_id:
            return True  # No user context, skip user-specific limits

        user_id = user_id or (user.id if user else None)
        if not user_id:
            return True

        window = self._get_current_window()
        cache_key = self._get_cache_key("user", f"{user_id}:{window}")

        try:
            current_count = cache.get(cache_key, 0)

            if current_count >= self.config["USER_RPM"]:
                raise RateLimitError(f"User rate limit exceeded ({current_count}/{self.config['USER_RPM']} requests per minute)")

            # Increment counter
            cache.set(cache_key, current_count + 1, timeout=self.config["WINDOW_SIZE"])
            return True

        except Exception as e:
            if isinstance(e, RateLimitError):
                raise
            logger.error(f"User rate limit check error: {e}")
            return True  # Allow request if rate limiting fails

    def check_token_limit(self, tokens: int, user: Optional[User] = None, user_id: Optional[int] = None) -> bool:
        """Check daily token limit.

        Args:
            tokens: Number of tokens for this request
            user: User instance
            user_id: User ID

        Returns:
            True if within limit

        Raises:
            RateLimitError: If limit exceeded
        """
        if not self.config["ENABLED"]:
            return True

        if not user and not user_id:
            return True  # No user context, skip token limits

        user_id = user_id or (user.id if user else None)
        if not user_id:
            return True

        # Use daily window (24 hours)
        daily_window = int(time.time() // 86400)
        cache_key = self._get_cache_key("tokens", f"{user_id}:{daily_window}")

        try:
            current_tokens = cache.get(cache_key, 0)

            if current_tokens + tokens > self.config["TOKEN_DAILY_LIMIT"]:
                raise RateLimitError(
                    f"Daily token limit exceeded ({current_tokens + tokens}/{self.config['TOKEN_DAILY_LIMIT']} tokens)"
                )

            # Increment token count
            cache.set(cache_key, current_tokens + tokens, timeout=86400)  # 24 hours
            return True

        except Exception as e:
            if isinstance(e, RateLimitError):
                raise
            logger.error(f"Token limit check error: {e}")
            return True  # Allow request if rate limiting fails

    def check_all_limits(self, tokens: int = 0, user: Optional[User] = None, user_id: Optional[int] = None) -> bool:
        """Check all applicable rate limits.

        Args:
            tokens: Number of tokens for this request
            user: User instance
            user_id: User ID

        Returns:
            True if all limits are within bounds

        Raises:
            RateLimitError: If any limit exceeded
        """
        # Check limits in order of importance
        self.check_global_limit()
        self.check_user_limit(user=user, user_id=user_id)

        if tokens > 0:
            self.check_token_limit(tokens=tokens, user=user, user_id=user_id)

        return True

    def get_remaining_limits(self, user: Optional[User] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get remaining limits for monitoring.

        Args:
            user: User instance
            user_id: User ID

        Returns:
            Dictionary with remaining limits
        """
        if not self.config["ENABLED"]:
            return {"enabled": False}

        try:
            window = self._get_current_window()
            daily_window = int(time.time() // 86400)

            # Global limit
            global_key = self._get_cache_key("global", str(window))
            global_used = cache.get(global_key, 0)

            limits = {
                "enabled": True,
                "global": {"limit": self.config["GLOBAL_RPM"], "used": global_used, "remaining": max(0, self.config["GLOBAL_RPM"] - global_used)},
            }

            # User-specific limits
            if user or user_id:
                user_id = user_id or (user.id if user else None)

                if user_id:
                    user_key = self._get_cache_key("user", f"{user_id}:{window}")
                    user_used = cache.get(user_key, 0)

                    token_key = self._get_cache_key("tokens", f"{user_id}:{daily_window}")
                    tokens_used = cache.get(token_key, 0)

                    limits.update(
                        {
                            "user": {"limit": self.config["USER_RPM"], "used": user_used, "remaining": max(0, self.config["USER_RPM"] - user_used)},
                            "tokens_daily": {
                                "limit": self.config["TOKEN_DAILY_LIMIT"],
                                "used": tokens_used,
                                "remaining": max(0, self.config["TOKEN_DAILY_LIMIT"] - tokens_used),
                            },
                        }
                    )

            return limits

        except Exception as e:
            logger.error(f"Get remaining limits error: {e}")
            return {"error": str(e)}