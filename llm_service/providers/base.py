"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, Optional


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the provider with configuration.

        Args:
            config: Provider-specific configuration dictionary
        """
        self.config = config
        self._validate_config()

    @abstractmethod
    def query(self, prompt: str, **kwargs) -> str:
        """Send a query to the LLM and return the response.

        Args:
            prompt: The input prompt
            **kwargs: Additional provider-specific parameters

        Returns:
            The LLM response as a string
        """
        pass

    @abstractmethod
    def query_async(self, prompt: str, **kwargs) -> Any:
        """Send an async query to the LLM.

        Args:
            prompt: The input prompt
            **kwargs: Additional provider-specific parameters

        Returns:
            A future or coroutine for the response
        """
        pass

    @abstractmethod
    def stream_query(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Stream a response from the LLM.

        Args:
            prompt: The input prompt
            **kwargs: Additional provider-specific parameters

        Yields:
            Response chunks as they arrive
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate the provider configuration.

        Returns:
            True if configuration is valid

        Raises:
            ProviderConfigError: If configuration is invalid
        """
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Get provider information and capabilities.

        Returns:
            Dictionary containing provider metadata
        """
        pass

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in the text.

        Args:
            text: The text to count tokens for

        Returns:
            Estimated token count
        """
        pass

    def _validate_config(self):
        """Internal configuration validation."""
        if not self.validate_config():
            from ..exceptions import ProviderConfigError
            raise ProviderConfigError(f"Invalid configuration for provider {self.__class__.__name__}")

    def get_model(self) -> str:
        """Get the model name from configuration.

        Returns:
            Model name or default
        """
        return self.config.get("model", "default")

    def get_temperature(self, **kwargs) -> float:
        """Get temperature setting for generation.

        Args:
            **kwargs: Override parameters

        Returns:
            Temperature value between 0 and 1
        """
        return kwargs.get("temperature", self.config.get("temperature", 0.7))

    def get_max_tokens(self, **kwargs) -> Optional[int]:
        """Get max tokens setting.

        Args:
            **kwargs: Override parameters

        Returns:
            Max tokens or None for default
        """
        return kwargs.get("max_tokens", self.config.get("max_tokens"))