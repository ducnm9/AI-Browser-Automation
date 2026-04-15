"""LLM request router with sensitive-data enforcement and fallback chain.

``LLMRouter`` implements the Chain of Responsibility pattern: each incoming
``LLMRequest`` is routed through a prioritised sequence of registered
providers until one succeeds.  Sensitive requests are restricted to the
local provider (LM Studio) and never forwarded to cloud backends.
"""

from __future__ import annotations

import logging

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.models.config import AppConfig, LLMProvider

logger = logging.getLogger(__name__)


class LLMRouter:
    """Route LLM requests to the appropriate provider.

    The router enforces two key policies:

    1. **Sensitive-data isolation** – requests marked ``is_sensitive``
       are sent *only* to the local LM Studio provider.
    2. **Fallback chain** – when the target provider is unavailable the
       router walks through remaining registered providers, trying each
       at most once, before raising ``LLMUnavailableError``.

    Args:
        config: Application configuration supplying the default provider.
    """

    def __init__(self, config: AppConfig) -> None:
        self.providers: dict[LLMProvider, BaseLLMProvider] = {}
        self.default_provider: LLMProvider = config.default_llm
        self.local_provider: LLMProvider = LLMProvider.LM_STUDIO

    def register_provider(
        self,
        provider_type: LLMProvider,
        provider: BaseLLMProvider,
    ) -> None:
        """Register an LLM provider instance.

        Args:
            provider_type: The ``LLMProvider`` enum value to register.
            provider: A concrete ``BaseLLMProvider`` instance.
        """
        self.providers[provider_type] = provider
        logger.info(
            "Registered provider %s",
            provider_type.value,
        )

    async def route(self, request: LLMRequest) -> LLMResponse:
        """Route *request* to the best available provider.

        Args:
            request: The LLM request to fulfil.

        Returns:
            ``LLMResponse`` from the first provider that succeeds.

        Raises:
            LLMUnavailableError: When every registered provider has
                been tried and none could fulfil the request.
        """
        if request.is_sensitive:
            target_provider = self.local_provider
        else:
            target_provider = self.default_provider

        tried_providers: set[LLMProvider] = set()

        # Build ordered fallback chain: target → default → rest.
        fallback_order: list[LLMProvider] = [
            target_provider,
            self.default_provider,
        ]
        fallback_order.extend(
            p for p in self.providers if p not in fallback_order
        )

        for provider_type in fallback_order:
            if provider_type in tried_providers:
                continue
            if provider_type not in self.providers:
                continue
            if (
                request.is_sensitive
                and provider_type != self.local_provider
            ):
                continue

            tried_providers.add(provider_type)
            provider = self.providers[provider_type]

            try:
                if await provider.health_check():
                    response = await provider.complete(request)
                    logger.info(
                        "Request fulfilled by %s",
                        provider_type.value,
                    )
                    return response
                logger.warning(
                    "Provider %s failed health check",
                    provider_type.value,
                )
            except Exception:
                logger.warning(
                    "Provider %s raised an exception, moving on",
                    provider_type.value,
                    exc_info=True,
                )
                continue

        tried_list = ", ".join(p.value for p in tried_providers)
        raise LLMUnavailableError(
            f"All providers unavailable. Tried: [{tried_list}]"
        )


__all__ = ["LLMRouter"]
