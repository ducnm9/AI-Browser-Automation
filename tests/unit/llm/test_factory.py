"""Unit tests for LLMProviderFactory."""

from __future__ import annotations

import pytest

from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.llm.factory import LLMProviderFactory
from ai_browser_automation.models.config import AppConfig, LLMProvider


class _StubProvider(BaseLLMProvider):
    """Minimal concrete provider for testing."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="stub",
            provider_used=LLMProvider.LM_STUDIO,
            tokens_used=0,
            latency_ms=0.0,
        )

    async def health_check(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Reset the factory registry before each test."""
    LLMProviderFactory._registry = {}


@pytest.fixture()
def config() -> AppConfig:
    return AppConfig()


class TestLLMProviderFactory:
    """Tests for LLMProviderFactory register and create."""

    def test_register_adds_to_registry(self) -> None:
        """register() stores the provider class in the registry."""
        LLMProviderFactory.register(
            LLMProvider.LM_STUDIO, _StubProvider,
        )
        assert LLMProvider.LM_STUDIO in LLMProviderFactory._registry

    def test_create_returns_base_type(
        self, config: AppConfig,
    ) -> None:
        """create() returns a BaseLLMProvider instance."""
        LLMProviderFactory.register(
            LLMProvider.LM_STUDIO, _StubProvider,
        )
        provider = LLMProviderFactory.create(
            LLMProvider.LM_STUDIO, config,
        )
        assert isinstance(provider, BaseLLMProvider)

    def test_create_raises_for_unknown_provider(
        self, config: AppConfig,
    ) -> None:
        """create() raises ValueError for unregistered provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMProviderFactory.create(LLMProvider.OPENAI, config)

    def test_create_passes_config_to_constructor(
        self, config: AppConfig,
    ) -> None:
        """create() passes AppConfig to the provider constructor."""
        LLMProviderFactory.register(
            LLMProvider.LM_STUDIO, _StubProvider,
        )
        provider = LLMProviderFactory.create(
            LLMProvider.LM_STUDIO, config,
        )
        assert provider._config is config

    def test_register_overwrites_existing(self) -> None:
        """Registering same provider type overwrites the class."""

        class _AnotherStub(BaseLLMProvider):
            def __init__(self, config: AppConfig) -> None:
                pass

            async def complete(
                self, request: LLMRequest,
            ) -> LLMResponse:
                return LLMResponse(
                    content="other",
                    provider_used=LLMProvider.LM_STUDIO,
                    tokens_used=0,
                    latency_ms=0.0,
                )

            async def health_check(self) -> bool:
                return True

        LLMProviderFactory.register(
            LLMProvider.LM_STUDIO, _StubProvider,
        )
        LLMProviderFactory.register(
            LLMProvider.LM_STUDIO, _AnotherStub,
        )
        assert (
            LLMProviderFactory._registry[LLMProvider.LM_STUDIO]
            is _AnotherStub
        )

    def test_multiple_providers_registered(
        self, config: AppConfig,
    ) -> None:
        """Multiple provider types can be registered."""
        LLMProviderFactory.register(
            LLMProvider.LM_STUDIO, _StubProvider,
        )
        LLMProviderFactory.register(
            LLMProvider.OPENAI, _StubProvider,
        )

        p1 = LLMProviderFactory.create(
            LLMProvider.LM_STUDIO, config,
        )
        p2 = LLMProviderFactory.create(LLMProvider.OPENAI, config)

        assert isinstance(p1, BaseLLMProvider)
        assert isinstance(p2, BaseLLMProvider)
