"""Custom exceptions for the LLM service."""


class LLMServiceError(Exception):
    """Base exception for LLM service errors."""

    pass


class ProviderNotFoundError(LLMServiceError):
    """Raised when a requested provider is not found."""

    pass


class ProviderConfigError(LLMServiceError):
    """Raised when provider configuration is invalid."""

    pass


class RateLimitError(LLMServiceError):
    """Raised when rate limits are exceeded."""

    pass


class TokenLimitError(LLMServiceError):
    """Raised when token limits are exceeded."""

    pass


class CacheError(LLMServiceError):
    """Raised when cache operations fail."""

    pass


class QueryError(LLMServiceError):
    """Raised when LLM query fails."""

    pass


class ValidationError(LLMServiceError):
    """Raised when input validation fails."""

    pass