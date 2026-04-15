"""LLM provider factory using the registry pattern.

``LLMProviderFactory`` maintains a class-level registry mapping
``LLMProvider`` enum values to concrete provider classes.  New providers
are added via ``register()`` — no modification of existing code required.
The ``create()`` method returns the ``BaseLLMProvider`` interface type,
never a concrete type.
"""

from __future__ import annotations

import logging

from ai_browser_automation.llm.base import BaseLLMProvider
from ai_browser_automation.models.config import AppConfig, LLMProvider

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Factory for creating LLM provider instances via a registry.

    Uses the registry pattern so that new providers can be added with
    ``register()`` without modifying any existing code.

    Attributes:
        _registry: Mapping from ``LLMProvider`` enum to concrete
            provider classes.
    """

    _registry: dict[LLMProvider, type[BaseLLMProvider]] = {}

    @classmethod
    def register(
        cls,
        provider_type: LLMProvider,
        provider_class: type[BaseLLMProvider],
    ) -> None:
        """Register a provider class for a given provider type.

        Args:
            provider_type: The ``LLMProvider`` enum value to register.
            provider_class: The concrete class implementing
                ``BaseLLMProvider``.
        """
        cls._registry[provider_type] = provider_class
        logger.debug(
            "Registered LLM provider %s -> %s",
            provider_type.value,
            provider_class.__name__,
        )

    @classmethod
    def create(
        cls,
        provider_type: LLMProvider,
        config: AppConfig,
    ) -> BaseLLMProvider:
        """Create a provider instance for the given type.

        Args:
            provider_type: The ``LLMProvider`` enum value to create.
            config: Application configuration passed to the provider
                constructor.

        Returns:
            A ``BaseLLMProvider`` instance.

        Raises:
            ValueError: If ``provider_type`` is not registered.
        """
        if provider_type not in cls._registry:
            raise ValueError(f"Unknown provider: {provider_type}")
        return cls._registry[provider_type](config)


__all__ = ["LLMProviderFactory"]
