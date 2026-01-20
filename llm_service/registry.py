"""Provider registry for managing LLM providers."""

import importlib
import logging
from typing import Dict, Optional, Type

from .exceptions import ProviderConfigError, ProviderNotFoundError
from .providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class LLMProviderRegistry:
    """Registry for managing LLM providers."""

    def __init__(self):
        """Initialize the provider registry."""
        self._providers: Dict[str, Type[BaseLLMProvider]] = {}
        self._instances: Dict[str, BaseLLMProvider] = {}
        self._discover_providers()

    def _discover_providers(self):
        """Auto-discover providers in the providers package."""
        # List of provider modules to try importing
        provider_modules = ["litellm", "openai", "anthropic"]

        for module_name in provider_modules:
            try:
                module = importlib.import_module(f".providers.{module_name}", package="llm_service")

                # Look for a provider class in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BaseLLMProvider) and attr != BaseLLMProvider:
                        provider_name = module_name
                        self._providers[provider_name] = attr
                        logger.info(f"Discovered provider: {provider_name} ({attr.__name__})")

            except ImportError as e:
                logger.debug(f"Provider module {module_name} not found: {e}")
            except Exception as e:
                logger.error(f"Error discovering provider {module_name}: {e}")

    def register_provider(self, name: str, provider_class: Type[BaseLLMProvider]):
        """Register a provider class.

        Args:
            name: Provider name
            provider_class: Provider class type
        """
        if not issubclass(provider_class, BaseLLMProvider):
            raise ProviderConfigError(f"Provider class must inherit from BaseLLMProvider")

        self._providers[name] = provider_class
        logger.info(f"Registered provider: {name}")

    def get_provider_class(self, name: str) -> Type[BaseLLMProvider]:
        """Get a provider class by name.

        Args:
            name: Provider name

        Returns:
            Provider class type

        Raises:
            ProviderNotFoundError: If provider not found
        """
        if name not in self._providers:
            raise ProviderNotFoundError(f"Provider '{name}' not found")

        return self._providers[name]

    def get_provider_instance(self, name: str, config: Dict) -> BaseLLMProvider:
        """Get or create a provider instance.

        Args:
            name: Provider name
            config: Provider configuration

        Returns:
            Provider instance

        Raises:
            ProviderNotFoundError: If provider not found
        """
        # Check if instance already exists
        instance_key = f"{name}:{hash(frozenset(config.items()))}"

        if instance_key not in self._instances:
            # Create new instance
            provider_class = self.get_provider_class(name)
            self._instances[instance_key] = provider_class(config)

        return self._instances[instance_key]

    def list_providers(self) -> list:
        """List all registered providers.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def get_provider_info(self, name: str) -> Dict:
        """Get information about a provider.

        Args:
            name: Provider name

        Returns:
            Provider information dictionary
        """
        provider_class = self.get_provider_class(name)
        return {"name": name, "class": provider_class.__name__, "module": provider_class.__module__, "available": True}


# Global registry instance
_registry: Optional[LLMProviderRegistry] = None


def get_registry() -> LLMProviderRegistry:
    """Get the global provider registry instance.

    Returns:
        Provider registry instance
    """
    global _registry
    if _registry is None:
        _registry = LLMProviderRegistry()
    return _registry