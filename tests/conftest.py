"""Shared pytest fixtures for AI Browser Automation test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_browser_automation.browser.base import BrowserEngine, PageContext
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.config import (
    AppConfig,
    LLMProvider,
    SecurityPolicy,
)
from ai_browser_automation.security.security_layer import SecurityLayer


# ------------------------------------------------------------------ #
# pytest-asyncio configuration
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def _asyncio_mode():
    """Marker fixture — pytest-asyncio auto mode is set in pyproject."""


# ------------------------------------------------------------------ #
# AppConfig
# ------------------------------------------------------------------ #

@pytest.fixture()
def test_config() -> AppConfig:
    """AppConfig with safe test defaults (no real API keys)."""
    return AppConfig(
        default_llm=LLMProvider.LM_STUDIO,
        lm_studio_url="http://localhost:1234/v1",
        action_timeout_ms=5000,
        max_retries=1,
    )


# ------------------------------------------------------------------ #
# Mock browser engine
# ------------------------------------------------------------------ #

@pytest.fixture()
def mock_browser_engine() -> AsyncMock:
    """Fully-mocked :class:`BrowserEngine` with sensible defaults."""
    engine = AsyncMock(spec=BrowserEngine)
    engine.get_page_context.return_value = PageContext(
        url="http://example.com",
        title="Example",
        dom_summary="<button>Click me</button>",
    )
    engine.screenshot.return_value = b"fake-png"
    return engine


# ------------------------------------------------------------------ #
# Mock LLM provider
# ------------------------------------------------------------------ #

@pytest.fixture()
def mock_llm_provider() -> AsyncMock:
    """Mocked :class:`BaseLLMProvider` that always succeeds."""
    provider = AsyncMock(spec=BaseLLMProvider)
    provider.health_check.return_value = True
    provider.complete.return_value = LLMResponse(
        content="mock response",
        provider_used=LLMProvider.LM_STUDIO,
        tokens_used=10,
        latency_ms=50.0,
    )
    return provider


# ------------------------------------------------------------------ #
# Mock LLM router
# ------------------------------------------------------------------ #

@pytest.fixture()
def mock_llm_router(test_config: AppConfig) -> MagicMock:
    """Mocked :class:`LLMRouter` with an async ``route`` method."""
    router = MagicMock(spec=LLMRouter)
    router.default_provider = test_config.default_llm
    router.local_provider = LLMProvider.LM_STUDIO
    router.providers = {}
    router.route = AsyncMock(return_value=LLMResponse(
        content="mock routed response",
        provider_used=LLMProvider.LM_STUDIO,
        tokens_used=10,
        latency_ms=50.0,
    ))
    return router


# ------------------------------------------------------------------ #
# Mock security layer
# ------------------------------------------------------------------ #

@pytest.fixture()
def mock_security_layer() -> MagicMock:
    """Mocked :class:`SecurityLayer` with no-op defaults."""
    layer = MagicMock(spec=SecurityLayer)
    layer.detect_sensitive_data.return_value = []
    layer.should_use_local_llm.return_value = False
    layer.sanitize_for_cloud.side_effect = (
        lambda text: (text, {})
    )
    layer.restore_sensitive_data.side_effect = (
        lambda text, mapping: text
    )
    layer.mask_for_log.side_effect = lambda text: text
    return layer
