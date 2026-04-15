"""Unit tests for NLProcessor.

Tests cover parse(), clarify(), and error handling against
Requirements 1.1, 1.2, 1.3, 1.4.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_browser_automation.core.nl_processor import NLProcessor
from ai_browser_automation.exceptions.errors import NLProcessingError
from ai_browser_automation.llm.base import LLMResponse
from ai_browser_automation.models.config import (
    LLMProvider,
    SecurityPolicy,
)
from ai_browser_automation.models.intents import IntentType, ParsedIntent
from ai_browser_automation.security.security_layer import SecurityLayer


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def security() -> SecurityLayer:
    """SecurityLayer with default policy."""
    return SecurityLayer(SecurityPolicy())


@pytest.fixture()
def mock_router() -> MagicMock:
    """LLMRouter mock with an async route method."""
    router = MagicMock()
    router.route = AsyncMock()
    return router


@pytest.fixture()
def processor(
    mock_router: MagicMock,
    security: SecurityLayer,
) -> NLProcessor:
    """NLProcessor wired with mock router and real security."""
    return NLProcessor(mock_router, security)


def _llm_response(content: str) -> LLMResponse:
    """Helper to build a fake LLMResponse."""
    return LLMResponse(
        content=content,
        provider_used=LLMProvider.LM_STUDIO,
        tokens_used=10,
        latency_ms=50.0,
    )


# ── parse: empty / whitespace input (Req 1.4) ───────────────────────


class TestParseRejectsEmptyInput:
    """Requirement 1.4: reject empty/whitespace input."""

    @pytest.mark.asyncio()
    async def test_empty_string(
        self, processor: NLProcessor,
    ) -> None:
        with pytest.raises(NLProcessingError):
            await processor.parse("")

    @pytest.mark.asyncio()
    async def test_whitespace_only(
        self, processor: NLProcessor,
    ) -> None:
        with pytest.raises(NLProcessingError):
            await processor.parse("   \t\n  ")


# ── parse: single intent (Req 1.1) ──────────────────────────────────


class TestParseSingleIntent:
    """Requirement 1.1: returns non-empty list with valid intents."""

    @pytest.mark.asyncio()
    async def test_navigate_intent(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "navigate",
                    "target_description": "Google homepage",
                    "parameters": {"url": "https://google.com"},
                    "confidence": 0.95,
                }],
            }),
        )

        result = await processor.parse("Go to Google")

        assert len(result) == 1
        assert result[0].intent_type is IntentType.NAVIGATE
        assert result[0].confidence == 0.95
        assert result[0].parameters["url"] == "https://google.com"

    @pytest.mark.asyncio()
    async def test_click_intent(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "click",
                    "target_description": "Submit button",
                    "parameters": {},
                    "confidence": 0.8,
                }],
            }),
        )

        result = await processor.parse("Click submit")

        assert len(result) == 1
        assert result[0].intent_type is IntentType.CLICK
        assert result[0].confidence == 0.8


# ── parse: composite intent (Req 1.2) ───────────────────────────────


class TestParseCompositeIntent:
    """Requirement 1.2: composite intents with sub_intents."""

    @pytest.mark.asyncio()
    async def test_composite_with_sub_intents(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "composite",
                    "target_description": "Login and read email",
                    "parameters": {},
                    "confidence": 0.9,
                    "sub_intents": [
                        {
                            "intent_type": "login",
                            "target_description": "Gmail",
                            "parameters": {},
                            "confidence": 0.9,
                        },
                        {
                            "intent_type": "extract_data",
                            "target_description": "latest email",
                            "parameters": {},
                            "confidence": 0.85,
                        },
                    ],
                }],
            }),
        )

        result = await processor.parse(
            "Login to Gmail and read latest email"
        )

        assert len(result) == 1
        intent = result[0]
        assert intent.intent_type is IntentType.COMPOSITE
        assert len(intent.sub_intents) == 2
        assert (
            intent.sub_intents[0].intent_type
            is IntentType.LOGIN
        )
        assert (
            intent.sub_intents[1].intent_type
            is IntentType.EXTRACT_DATA
        )


# ── parse: confidence clamping ───────────────────────────────────────


class TestParseConfidenceClamping:
    """Confidence values are clamped to [0.0, 1.0]."""

    @pytest.mark.asyncio()
    async def test_confidence_above_one_clamped(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "navigate",
                    "target_description": "test",
                    "parameters": {},
                    "confidence": 1.5,
                }],
            }),
        )

        result = await processor.parse("test")
        assert result[0].confidence == 1.0

    @pytest.mark.asyncio()
    async def test_confidence_below_zero_clamped(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "navigate",
                    "target_description": "test",
                    "parameters": {},
                    "confidence": -0.5,
                }],
            }),
        )

        result = await processor.parse("test")
        assert result[0].confidence == 0.0

    @pytest.mark.asyncio()
    async def test_non_numeric_confidence_defaults_zero(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "navigate",
                    "target_description": "test",
                    "parameters": {},
                    "confidence": "invalid",
                }],
            }),
        )

        result = await processor.parse("test")
        assert result[0].confidence == 0.0


# ── parse: error handling ────────────────────────────────────────────


class TestParseErrorHandling:
    """LLM failures and bad JSON are wrapped in NLProcessingError."""

    @pytest.mark.asyncio()
    async def test_llm_failure_raises(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.side_effect = RuntimeError("boom")

        with pytest.raises(NLProcessingError, match="LLM request"):
            await processor.parse("Go to Google")

    @pytest.mark.asyncio()
    async def test_invalid_json_raises(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            "not json at all",
        )

        with pytest.raises(NLProcessingError, match="JSON"):
            await processor.parse("Go to Google")

    @pytest.mark.asyncio()
    async def test_empty_intents_list_raises(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({"intents": []}),
        )

        with pytest.raises(NLProcessingError, match="non-empty"):
            await processor.parse("Go to Google")

    @pytest.mark.asyncio()
    async def test_invalid_intent_type_raises(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "unknown_action",
                    "target_description": "test",
                    "confidence": 0.5,
                }],
            }),
        )

        with pytest.raises(NLProcessingError, match="intent_type"):
            await processor.parse("do something")


# ── clarify (Req 1.3) ───────────────────────────────────────────────


class TestClarify:
    """Requirement 1.3: generate clarification questions."""

    @pytest.mark.asyncio()
    async def test_returns_clarification_string(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            "Which button do you want to click?",
        )

        result = await processor.clarify(
            "Click the button",
            ["Which button?"],
        )

        assert result == "Which button do you want to click?"

    @pytest.mark.asyncio()
    async def test_clarify_llm_failure_raises(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.side_effect = RuntimeError("down")

        with pytest.raises(
            NLProcessingError, match="Clarification",
        ):
            await processor.clarify("test", ["ambiguity"])


# ── sensitive data routing ───────────────────────────────────────────


class TestSensitiveDataRouting:
    """Sensitive input is sanitised and marked is_sensitive."""

    @pytest.mark.asyncio()
    async def test_sensitive_input_sets_is_sensitive(
        self,
        processor: NLProcessor,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "intents": [{
                    "intent_type": "login",
                    "target_description": "Gmail",
                    "parameters": {},
                    "confidence": 0.9,
                }],
            }),
        )

        await processor.parse(
            "Login with password: secret123"
        )

        call_args = mock_router.route.call_args
        request = call_args[0][0]
        assert request.is_sensitive is True
