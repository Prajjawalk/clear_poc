"""LiteLLM provider implementation."""

import logging
import os
from collections.abc import Generator
from typing import Any

from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


class LiteLLMProvider(BaseLLMProvider):
    """LiteLLM provider implementation using OpenAI client library."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the LiteLLM provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)
        self._client = None
        self._async_client = None
        self._init_clients()

    def _init_clients(self):
        """Initialize LiteLLM/OpenAI clients."""
        try:
            from openai import AsyncOpenAI, OpenAI
        except ImportError:
            raise ImportError("openai library is required for LiteLLM provider. Install with: pip install openai")

        # Get API key from environment variable (always use LITELLM_API_KEY)
        api_key = os.getenv("LITELLM_API_KEY")
        if not api_key:
            from ..exceptions import ProviderConfigError
            raise ProviderConfigError("API key not found in environment variable LITELLM_API_KEY")

        # Get base URL from environment or config, with fallback
        base_url = os.getenv("LITELLM_API_BASE") or self.config.get("BASE_URL", "http://localhost:4000")

        # Get timeout from config with default
        timeout = self.config.get("TIMEOUT", 30)

        # Initialize synchronous client
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

        # Initialize async client
        self._async_client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def query(self, prompt: str, **kwargs) -> str:
        """Send a query to LiteLLM and return the response.

        Args:
            prompt: The input prompt
            **kwargs: Additional parameters

        Returns:
            The LLM response as a string
        """
        try:
            # Build messages
            messages = self._build_messages(prompt, kwargs.get("system"))

            # Get parameters
            model = kwargs.get("model", self.get_model())
            temperature = self.get_temperature(**kwargs)
            max_tokens = self.get_max_tokens(**kwargs)

            # Make API call
            params = {"model": model, "messages": messages, "temperature": temperature}

            if max_tokens:
                params["max_tokens"] = max_tokens

            # Add any additional parameters
            for key in ["top_p", "frequency_penalty", "presence_penalty", "stop"]:
                if key in kwargs:
                    params[key] = kwargs[key]

            response = self._client.chat.completions.create(**params)

            # Extract and return response text
            return response.choices[0].message.content

        except Exception as e:
            from ..exceptions import QueryError

            logger.error(f"LiteLLM query failed: {str(e)}")
            raise QueryError(f"Query failed: {str(e)}")

    async def query_async(self, prompt: str, **kwargs) -> str:
        """Send an async query to LiteLLM.

        Args:
            prompt: The input prompt
            **kwargs: Additional parameters

        Returns:
            The LLM response as a string
        """
        try:
            # Build messages
            messages = self._build_messages(prompt, kwargs.get("system"))

            # Get parameters
            model = kwargs.get("model", self.get_model())
            temperature = self.get_temperature(**kwargs)
            max_tokens = self.get_max_tokens(**kwargs)

            # Make API call
            params = {"model": model, "messages": messages, "temperature": temperature}

            if max_tokens:
                params["max_tokens"] = max_tokens

            response = await self._async_client.chat.completions.create(**params)

            # Extract and return response text
            return response.choices[0].message.content

        except Exception as e:
            from ..exceptions import QueryError

            logger.error(f"LiteLLM async query failed: {str(e)}")
            raise QueryError(f"Async query failed: {str(e)}")

    def stream_query(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Stream a response from LiteLLM.

        Args:
            prompt: The input prompt
            **kwargs: Additional parameters

        Yields:
            Response chunks as they arrive
        """
        try:
            # Build messages
            messages = self._build_messages(prompt, kwargs.get("system"))

            # Get parameters
            model = kwargs.get("model", self.get_model())
            temperature = self.get_temperature(**kwargs)
            max_tokens = self.get_max_tokens(**kwargs)

            # Make streaming API call
            params = {"model": model, "messages": messages, "temperature": temperature, "stream": True}

            if max_tokens:
                params["max_tokens"] = max_tokens

            response = self._client.chat.completions.create(**params)

            # Stream response chunks
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            from ..exceptions import QueryError

            logger.error(f"LiteLLM streaming failed: {str(e)}")
            raise QueryError(f"Streaming failed: {str(e)}")

    def validate_config(self) -> bool:
        """Validate the provider configuration.

        Returns:
            True if configuration is valid
        """
        # Check required configuration
        required_keys = ["MODEL"]
        for key in required_keys:
            if key not in self.config:
                logger.error(f"Missing required configuration: {key}")
                return False

        # Check API key environment variable (always LITELLM_API_KEY)
        if not os.getenv("LITELLM_API_KEY"):
            logger.error("API key not found in environment variable LITELLM_API_KEY")
            return False

        return True

    def get_info(self) -> dict[str, Any]:
        """Get provider information and capabilities.

        Returns:
            Dictionary containing provider metadata
        """
        return {
            "name": "litellm",
            "description": "LiteLLM unified LLM interface",
            "model": self.get_model(),
            "base_url": os.getenv("LITELLM_API_BASE") or self.config.get("BASE_URL", "http://localhost:4000"),
            "capabilities": {"streaming": True, "async": True, "token_estimation": True},
            "config": {
                "timeout": self.config.get("TIMEOUT", 30),
                "max_retries": self.config.get("MAX_RETRIES", 3),
            },
        }

    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in the text.

        Args:
            text: The text to count tokens for

        Returns:
            Estimated token count
        """
        try:
            import tiktoken

            # Try to get encoding for the model
            model = self.get_model()
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                # Fall back to cl100k_base encoding (GPT-3.5/4)
                encoding = tiktoken.get_encoding("cl100k_base")

            return len(encoding.encode(text))

        except ImportError:
            # Fallback to rough estimation (1 token ≈ 4 characters)
            return len(text) // 4

    def _build_messages(self, prompt: str, system: str | None = None) -> list:
        """Build message array for chat completion.

        Args:
            prompt: User prompt
            system: Optional system message

        Returns:
            List of message dictionaries
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        return messages
