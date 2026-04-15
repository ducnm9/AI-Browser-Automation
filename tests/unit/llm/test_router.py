"""Unit tests for LLMRouter.

Tests cover: register_provider(), fallback chain order, sensitive routing
to local only, and all-providers-down raises LLMUnavailableError.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.config import AppConfig, LLMProvider


# ── Helpers ──────────────────────────────────────────────────────


def _mock_provider(
    provider_type: LLMProvider,
    *,
    healthy: bool = True,
) -> AsyncMock:
    """Create a mock provider with configurable health."""
    mock = AsyncMock(spec=BaseLLMProvider)
    mock.health_check.return_value = healthy
    mock.complete.return_value = LLMResponse(
        content="ok",
        provider_used=provider_type,
        tokens_used=5,
        latency_ms=1.0,
    )
    return mock


@pytest.fixture()
def config() -> AppConfig:
    """Default test config with LM_STUDIO as default."""
    return AppConfig(default_llm=LLMProvider.LM_STUDIO)


@pytest.fixture()
def router(config: AppConfig) -> LLMRouter:
    """Fresh LLMRouter instance."""
    return LLMRouter(config)


# ── register_provider() ─────────────────────────────────────────


class TestRegisterProvider:
    """Req 4.5: register_provider() adds without modifying existing."""

    def test_register_adds_provider(self, router: LLMRouter) -> None:
        """New provider appears in providers dict."""
        mock = _mock_provider(LLMProvider.OPENAI)
        router.register_provider(LLMProvider.OPENAI, mock)
        assert LLMProvider.OPENAI in router.providers

    def test_register_does_not_remove_existing(
        self, router: LLMRouter,
    ) -> None:
        """Registering a second provider keeps the first."""
        mock_a = _mock_provider(LLMProvider.OPENAI)
        mock_b = _mock_provider(LLMProvider.GEMINI)
        router.register_provider(LLMProvider.OPENAI, mock_a)
        router.register_provider(LLMProvider.GEMINI, mock_b)
        assert LLMProvider.OPENAI in router.providers
        assert LLMProvider.GEMINI in router.providers

    def test_register_overwrites_same_type(
        self, router: LLMRouter,
    ) -> None:
        """Re-registering same type replaces the instance."""
        mock_old = _mock_provider(LLMProvider.OPENAI)
        mock_new = _mock_provider(LLMProvider.OPENAI)
        router.register_provider(LLMProvider.OPENAI, mock_old)
        router.register_provider(LLMProvider.OPENAI, mock_new)
        assert router.providers[LLMProvider.OPENAI] is mock_new


# ── Sensitive routing ────────────────────────────────────────────


class TestSensitiveRouting:
    """Req 4.1: Sensitive requests route to LM_STUDIO only."""

    @pytest.mark.asyncio()
    async def test_sensitive_routes_to_local(
        self, router: LLMRouter,
    ) -> None:
        """is_sensitive=True → LM_STUDIO."""
        local = _mock_provider(LLMProvider.LM_STUDIO)
        cloud = _mock_provider(LLMProvider.OPENAI)
        router.register_provider(LLMProvider.LM_STUDIO, local)
        router.register_provider(LLMProvider.OPENAI, cloud)

        request = LLMRequest(prompt="secret", is_sensitive=True)
        response = await router.route(request)

        assert response.provider_used == LLMProvider.LM_STUDIO
        cloud.complete.assert_not_called()

    @pytest.mark.asyncio()
    async def test_sensitive_never_falls_back_to_cloud(
        self, router: LLMRouter,
    ) -> None:
        """Sensitive + local down → error, not cloud fallback."""
        local = _mock_provider(LLMProvider.LM_STUDIO, healthy=False)
        cloud = _mock_provider(LLMProvider.OPENAI)
        router.register_provider(LLMProvider.LM_STUDIO, local)
        router.register_provider(LLMProvider.OPENAI, cloud)

        request = LLMRequest(prompt="secret", is_sensitive=True)
        with pytest.raises(LLMUnavailableError):
            await router.route(request)

        cloud.health_check.assert_not_called()


# ── Fallback chain ───────────────────────────────────────────────


class TestFallbackChain:
    """Req 4.2, 4.4: Fallback chain order and uniqueness."""

    @pytest.mark.asyncio()
    async def test_fallback_to_next_provider(
        self, router: LLMRouter,
    ) -> None:
        """Default down → falls back to next registered provider."""
        local = _mock_provider(LLMProvider.LM_STUDIO, healthy=False)
        openai = _mock_provider(LLMProvider.OPENAI)
        router.register_provider(LLMProvider.LM_STUDIO, local)
        router.register_provider(LLMProvider.OPENAI, openai)

        request = LLMRequest(prompt="hello", is_sensitive=False)
        response = await router.route(request)

        assert response.provider_used == LLMProvider.OPENAI

    @pytest.mark.asyncio()
    async def test_fallback_chain_tries_all(self) -> None:
        """Falls through multiple unhealthy providers to find one."""
        config = AppConfig(default_llm=LLMProvider.OPENAI)
        router = LLMRouter(config)

        openai = _mock_provider(LLMProvider.OPENAI, healthy=False)
        gemini = _mock_provider(LLMProvider.GEMINI, healthy=False)
        bedrock = _mock_provider(LLMProvider.BEDROCK)
        router.register_provider(LLMProvider.OPENAI, openai)
        router.register_provider(LLMProvider.GEMINI, gemini)
        router.register_provider(LLMProvider.BEDROCK, bedrock)

        request = LLMRequest(prompt="hello", is_sensitive=False)
        response = await router.route(request)

        assert response.provider_used == LLMProvider.BEDROCK

    @pytest.mark.asyncio()
    async def test_default_provider_tried_first(self) -> None:
        """The configured default provider is attempted first."""
        config = AppConfig(default_llm=LLMProvider.GEMINI)
        router = LLMRouter(config)

        call_order: list[LLMProvider] = []

        for p in [
            LLMProvider.OPENAI,
            LLMProvider.GEMINI,
            LLMProvider.BEDROCK,
        ]:
            mock = _mock_provider(p, healthy=False)

            async def _track(
                _p: LLMProvider = p,
            ) -> bool:
                call_order.append(_p)
                return False

            mock.health_check.side_effect = _track
            router.register_provider(p, mock)

        request = LLMRequest(prompt="hello", is_sensitive=False)
        with pytest.raises(LLMUnavailableError):
            await router.route(request)

        assert call_order[0] == LLMProvider.GEMINI


# ── All providers down ───────────────────────────────────────────


class TestAllProvidersDown:
    """Req 4.3: All providers unavailable raises LLMUnavailableError."""

    @pytest.mark.asyncio()
    async def test_raises_unavailable_error(
        self, router: LLMRouter,
    ) -> None:
        """All unhealthy → LLMUnavailableError."""
        for p in LLMProvider:
            router.register_provider(
                p, _mock_provider(p, healthy=False),
            )

        request = LLMRequest(prompt="hello", is_sensitive=False)
        with pytest.raises(LLMUnavailableError, match="All providers"):
            await router.route(request)

    @pytest.mark.asyncio()
    async def test_error_message_lists_tried_providers(
        self, router: LLMRouter,
    ) -> None:
        """Error message includes names of tried providers."""
        local = _mock_provider(LLMProvider.LM_STUDIO, healthy=False)
        openai = _mock_provider(LLMProvider.OPENAI, healthy=False)
        router.register_provider(LLMProvider.LM_STUDIO, local)
        router.register_provider(LLMProvider.OPENAI, openai)

        request = LLMRequest(prompt="hello", is_sensitive=False)
        with pytest.raises(LLMUnavailableError) as exc_info:
            await router.route(request)

        msg = str(exc_info.value)
        assert "lm_studio" in msg
        assert "openai" in msg

    @pytest.mark.asyncio()
    async def test_no_providers_registered(
        self, router: LLMRouter,
    ) -> None:
        """No providers registered → LLMUnavailableError."""
        request = LLMRequest(prompt="hello", is_sensitive=False)
        with pytest.raises(LLMUnavailableError):
            await router.route(request)

    @pytest.mark.asyncio()
    async def test_provider_exception_triggers_fallback(
        self, router: LLMRouter,
    ) -> None:
        """Provider raising exception → router tries next."""
        local = _mock_provider(LLMProvider.LM_STUDIO)
        local.health_check.side_effect = RuntimeError("boom")
        openai = _mock_provider(LLMProvider.OPENAI)
        router.register_provider(LLMProvider.LM_STUDIO, local)
        router.register_provider(LLMProvider.OPENAI, openai)

        request = LLMRequest(prompt="hello", is_sensitive=False)
        response = await router.route(request)

        assert response.provider_used == LLMProvider.OPENAI
