"""Property-based tests for LLMRouter routing logic.

Uses hypothesis to verify correctness properties 7–8 from the design
document against Requirements 4.1–4.4 and 9.4.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.config import AppConfig, LLMProvider


# ── Helpers ──────────────────────────────────────────────────────

_ALL_PROVIDERS = list(LLMProvider)
_CLOUD_PROVIDERS = [p for p in LLMProvider if p != LLMProvider.LM_STUDIO]


def _make_provider(
    provider_type: LLMProvider,
    *,
    healthy: bool = True,
) -> AsyncMock:
    """Create a mock BaseLLMProvider with configurable health."""
    mock = AsyncMock(spec=BaseLLMProvider)
    mock.health_check.return_value = healthy
    mock.complete.return_value = LLMResponse(
        content="response",
        provider_used=provider_type,
        tokens_used=10,
        latency_ms=5.0,
    )
    return mock


# ── Strategies ───────────────────────────────────────────────────

_sensitive_request_st = st.builds(
    LLMRequest,
    prompt=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    context=st.one_of(st.none(), st.text(min_size=1, max_size=30)),
    max_tokens=st.integers(min_value=1, max_value=4096),
    temperature=st.floats(min_value=0.0, max_value=2.0),
    is_sensitive=st.just(True),
)

_provider_subset_st = st.lists(
    st.sampled_from(_ALL_PROVIDERS),
    min_size=1,
    max_size=len(_ALL_PROVIDERS),
    unique=True,
)

_default_provider_st = st.sampled_from(_ALL_PROVIDERS)


# ── Property 7: Sensitive Data Routes to Local LLM ───────────────


class TestSensitiveDataRoutesToLocal:
    """**Validates: Requirements 4.1, 9.4**

    For any LLMRequest with is_sensitive=True, the LLM_Router SHALL
    route exclusively to LM_STUDIO. No cloud provider SHALL be called.
    """

    @given(request=_sensitive_request_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_sensitive_always_uses_lm_studio(
        self, request: LLMRequest,
    ) -> None:
        """Sensitive requests always route to LM_STUDIO."""
        config = AppConfig(default_llm=LLMProvider.LM_STUDIO)
        router = LLMRouter(config)

        local_mock = _make_provider(LLMProvider.LM_STUDIO, healthy=True)
        router.register_provider(LLMProvider.LM_STUDIO, local_mock)

        cloud_mocks: dict[LLMProvider, AsyncMock] = {}
        for cp in _CLOUD_PROVIDERS:
            mock = _make_provider(cp, healthy=True)
            router.register_provider(cp, mock)
            cloud_mocks[cp] = mock

        response = await router.route(request)

        assert response.provider_used == LLMProvider.LM_STUDIO
        local_mock.complete.assert_called_once()
        for mock in cloud_mocks.values():
            mock.complete.assert_not_called()

    @given(
        request=_sensitive_request_st,
        default=st.sampled_from(_CLOUD_PROVIDERS),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_sensitive_ignores_cloud_default(
        self, request: LLMRequest, default: LLMProvider,
    ) -> None:
        """Even when default is a cloud provider, sensitive → LM_STUDIO."""
        config = AppConfig(default_llm=default)
        router = LLMRouter(config)

        local_mock = _make_provider(LLMProvider.LM_STUDIO, healthy=True)
        router.register_provider(LLMProvider.LM_STUDIO, local_mock)

        cloud_mock = _make_provider(default, healthy=True)
        router.register_provider(default, cloud_mock)

        response = await router.route(request)

        assert response.provider_used == LLMProvider.LM_STUDIO
        cloud_mock.complete.assert_not_called()

    @given(request=_sensitive_request_st)
    @settings(max_examples=30)
    @pytest.mark.asyncio()
    async def test_sensitive_raises_when_local_unavailable(
        self, request: LLMRequest,
    ) -> None:
        """Sensitive request raises LLMUnavailableError when LM_STUDIO down."""
        config = AppConfig(default_llm=LLMProvider.LM_STUDIO)
        router = LLMRouter(config)

        local_mock = _make_provider(LLMProvider.LM_STUDIO, healthy=False)
        router.register_provider(LLMProvider.LM_STUDIO, local_mock)

        cloud_mock = _make_provider(LLMProvider.OPENAI, healthy=True)
        router.register_provider(LLMProvider.OPENAI, cloud_mock)

        with pytest.raises(LLMUnavailableError):
            await router.route(request)

        cloud_mock.complete.assert_not_called()
        cloud_mock.health_check.assert_not_called()



# ── Property 8: Fallback Exhaustion and Provider Uniqueness ──────


class TestFallbackExhaustionAndUniqueness:
    """**Validates: Requirements 4.2, 4.3, 4.4**

    For any set of registered providers where all fail, the router SHALL
    try each at most once, raise LLMUnavailableError, and the tried set
    SHALL contain no duplicates.
    """

    @given(providers=_provider_subset_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_all_fail_raises_unavailable(
        self, providers: list[LLMProvider],
    ) -> None:
        """LLMUnavailableError raised when every provider fails."""
        config = AppConfig(default_llm=providers[0])
        router = LLMRouter(config)

        for p in providers:
            router.register_provider(p, _make_provider(p, healthy=False))

        request = LLMRequest(prompt="test", is_sensitive=False)
        with pytest.raises(LLMUnavailableError):
            await router.route(request)

    @given(providers=_provider_subset_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_each_provider_tried_at_most_once(
        self, providers: list[LLMProvider],
    ) -> None:
        """Each provider's health_check is called at most once."""
        config = AppConfig(default_llm=providers[0])
        router = LLMRouter(config)

        mocks: dict[LLMProvider, AsyncMock] = {}
        for p in providers:
            mock = _make_provider(p, healthy=False)
            router.register_provider(p, mock)
            mocks[p] = mock

        request = LLMRequest(prompt="test", is_sensitive=False)
        with pytest.raises(LLMUnavailableError):
            await router.route(request)

        for p, mock in mocks.items():
            assert mock.health_check.call_count <= 1, (
                f"Provider {p.value} tried more than once"
            )

    @given(
        providers=_provider_subset_st,
        healthy_idx=st.integers(min_value=0),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_fallback_finds_healthy_provider(
        self,
        providers: list[LLMProvider],
        healthy_idx: int,
    ) -> None:
        """Router finds a healthy provider via fallback chain."""
        config = AppConfig(default_llm=providers[0])
        router = LLMRouter(config)

        target_idx = healthy_idx % len(providers)
        for i, p in enumerate(providers):
            healthy = i == target_idx
            router.register_provider(
                p, _make_provider(p, healthy=healthy),
            )

        request = LLMRequest(prompt="test", is_sensitive=False)
        response = await router.route(request)

        assert response.provider_used == providers[target_idx]

    @given(providers=_provider_subset_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_no_duplicate_providers_tried(
        self, providers: list[LLMProvider],
    ) -> None:
        """The set of tried providers has no duplicates."""
        config = AppConfig(default_llm=providers[0])
        router = LLMRouter(config)

        call_log: list[LLMProvider] = []
        for p in providers:
            mock = _make_provider(p, healthy=False)

            async def _track_health(
                _p: LLMProvider = p,
            ) -> bool:
                call_log.append(_p)
                return False

            mock.health_check.side_effect = _track_health
            router.register_provider(p, mock)

        request = LLMRequest(prompt="test", is_sensitive=False)
        with pytest.raises(LLMUnavailableError):
            await router.route(request)

        assert len(call_log) == len(set(call_log)), (
            f"Duplicate providers tried: {call_log}"
        )
