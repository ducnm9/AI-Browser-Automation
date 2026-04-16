"""End-to-end integration tests for the AIBrowserAutomation pipeline.

Tests exercise the full facade with mocked external boundaries
(LLM providers and browser engine) while using real internal
components (SecurityLayer, NLProcessor, TaskPlanner, ActionExecutor).

Requirements: 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from ai_browser_automation.app import AIBrowserAutomation
from ai_browser_automation.browser.base import BrowserEngine, PageContext
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.models.config import AppConfig, LLMProvider


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_parse_response(
    intent_type: str = "navigate",
    target: str = "google.com",
    confidence: float = 0.95,
) -> str:
    """Build a JSON string mimicking an NL-parse LLM response."""
    return json.dumps(
        {
            "intents": [
                {
                    "intent_type": intent_type,
                    "target_description": target,
                    "parameters": {},
                    "confidence": confidence,
                    "sub_intents": [],
                },
            ],
        },
    )


def _make_plan_response(
    action_type: str = "navigate",
    selector_value: str = "http://google.com",
) -> str:
    """Build a JSON string mimicking a task-planner LLM response."""
    return json.dumps(
        {
            "steps": [
                {
                    "action_type": action_type,
                    "selector_strategy": "css",
                    "selector_value": selector_value,
                    "input_value": None,
                    "wait_condition": None,
                    "timeout_ms": 5000,
                    "retry_count": 0,
                },
            ],
            "description": "Navigate to target",
            "estimated_duration_ms": 3000,
        },
    )



def _make_low_confidence_parse_response() -> str:
    """Build a parse response with confidence below the 0.7 threshold."""
    return json.dumps(
        {
            "intents": [
                {
                    "intent_type": "click",
                    "target_description": "some button",
                    "parameters": {},
                    "confidence": 0.3,
                    "sub_intents": [],
                },
            ],
        },
    )


# ------------------------------------------------------------------ #
# Mock LLM provider that returns controlled responses
# ------------------------------------------------------------------ #


class _FakeLLMProvider(BaseLLMProvider):
    """LLM provider stub that returns pre-configured responses.

    Args:
        responses: Ordered list of content strings to return.
        provider_type: Which provider this stub represents.
    """

    def __init__(
        self,
        responses: list[str],
        provider_type: LLMProvider = LLMProvider.LM_STUDIO,
    ) -> None:
        self._responses = list(responses)
        self._call_index = 0
        self._provider_type = provider_type

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the next pre-configured response.

        Args:
            request: The incoming LLM request.

        Returns:
            LLMResponse with the next queued content string.
        """
        content = self._responses[
            min(self._call_index, len(self._responses) - 1)
        ]
        self._call_index += 1
        return LLMResponse(
            content=content,
            provider_used=self._provider_type,
            tokens_used=10,
            latency_ms=5.0,
        )

    async def health_check(self) -> bool:
        """Always healthy.

        Returns:
            True.
        """
        return True


# ------------------------------------------------------------------ #
# Mock browser engine
# ------------------------------------------------------------------ #


class _FakeBrowserEngine(BrowserEngine):
    """Minimal browser engine stub for integration tests."""

    def __init__(self) -> None:
        self.launched = False
        self.closed = False
        self.navigated_urls: list[str] = []

    async def launch(self, headless: bool = False) -> None:
        """Record launch."""
        self.launched = True

    async def navigate(self, url: str) -> None:
        """Record navigation."""
        self.navigated_urls.append(url)

    async def click(
        self, selector: str, strategy: str = "css",
    ) -> None:
        """No-op click."""

    async def type_text(
        self, selector: str, text: str, strategy: str = "css",
    ) -> None:
        """No-op type."""

    async def extract_text(
        self, selector: str, strategy: str = "css",
    ) -> str:
        """Return placeholder extracted text."""
        return "extracted content"

    async def screenshot(self) -> bytes:
        """Return fake screenshot bytes."""
        return b"fake-png"

    async def get_page_context(self) -> PageContext:
        """Return a minimal page context."""
        return PageContext(
            url="http://example.com",
            title="Example",
            dom_summary="<button id='btn'>Click</button>",
            visible_elements=[
                {"tag": "button", "text": "Click", "id": "btn"},
            ],
        )

    async def extract_table(
        self, selector: str, strategy: str = "css",
    ) -> list[list[str]]:
        """Return a placeholder table."""
        return [["Header1", "Header2"], ["Cell1", "Cell2"]]

    async def close(self) -> None:
        """Record close."""
        self.closed = True



# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture()
def fake_browser() -> _FakeBrowserEngine:
    """A fake browser engine for integration tests."""
    return _FakeBrowserEngine()


@pytest.fixture()
def config() -> AppConfig:
    """Minimal AppConfig with no real API keys."""
    return AppConfig(
        default_llm=LLMProvider.LM_STUDIO,
        lm_studio_url="http://localhost:1234/v1",
        action_timeout_ms=5000,
        max_retries=1,
    )


async def _init_app(
    config: AppConfig,
    fake_browser: _FakeBrowserEngine,
    llm_responses: list[str],
) -> AIBrowserAutomation:
    """Create and initialize an AIBrowserAutomation with fakes.

    Args:
        config: Application configuration.
        fake_browser: Fake browser engine to inject.
        llm_responses: Ordered LLM response strings.

    Returns:
        An initialized AIBrowserAutomation instance.
    """
    app = AIBrowserAutomation(config)

    fake_provider = _FakeLLMProvider(llm_responses)

    with patch(
        "ai_browser_automation.app.BrowserEngineFactory.create",
        return_value=fake_browser,
    ), patch(
        "ai_browser_automation.app.LLMProviderFactory.create",
        return_value=fake_provider,
    ):
        await app.initialize()

    return app


# ------------------------------------------------------------------ #
# Test 1: Full pipeline success (Req 9.1)
# ------------------------------------------------------------------ #


class TestFullPipelineSuccess:
    """Full pipeline: command -> parse -> plan -> execute -> result."""

    @pytest.mark.asyncio()
    async def test_chat_returns_action_summary(
        self,
        config: AppConfig,
        fake_browser: _FakeBrowserEngine,
    ) -> None:
        """A valid command flows through the entire pipeline and
        returns a summary containing action results.
        """
        parse_resp = _make_parse_response()
        plan_resp = _make_plan_response()

        app = await _init_app(
            config, fake_browser, [parse_resp, plan_resp],
        )

        result = await app.chat("Go to google.com")

        assert "Completed" in result
        assert "1/1 actions" in result
        assert "[OK]" in result


# ------------------------------------------------------------------ #
# Test 2: Sensitive data auto-routes to local LLM (Req 9.4)
# ------------------------------------------------------------------ #


class TestSensitiveDataRouting:
    """Input with sensitive data triggers local LLM routing."""

    @pytest.mark.asyncio()
    async def test_password_input_routes_to_local(
        self,
        config: AppConfig,
        fake_browser: _FakeBrowserEngine,
    ) -> None:
        """When the user command contains a password pattern,
        the router's default_provider switches to LM_STUDIO.
        """
        parse_resp = _make_parse_response(
            intent_type="login",
            target="bank login",
        )
        plan_resp = _make_plan_response(
            action_type="navigate",
            selector_value="http://bank.com",
        )

        app = await _init_app(
            config, fake_browser, [parse_resp, plan_resp],
        )

        await app.chat("password: secret123")

        assert app._llm_router is not None
        assert (
            app._llm_router.default_provider
            == LLMProvider.LM_STUDIO
        )


# ------------------------------------------------------------------ #
# Test 3: Pipeline failure returns error, browser stable (Req 9.3)
# ------------------------------------------------------------------ #


class TestPipelineFailure:
    """NL parse failure returns error message; browser stays stable."""

    @pytest.mark.asyncio()
    async def test_parse_failure_returns_error_message(
        self,
        config: AppConfig,
        fake_browser: _FakeBrowserEngine,
    ) -> None:
        """When the LLM returns unparseable JSON for the NL step,
        the facade returns an error string and the browser is
        still usable.
        """
        bad_parse = "this is not valid json at all"

        app = await _init_app(
            config, fake_browser, [bad_parse],
        )

        result = await app.chat("do something")

        assert "Error" in result

        # Browser should still be responsive (stable)
        ctx = await fake_browser.get_page_context()
        assert ctx.url == "http://example.com"
        assert not fake_browser.closed


# ------------------------------------------------------------------ #
# Test 4: Conversation history updated (Req 9.2)
# ------------------------------------------------------------------ #


class TestConversationHistory:
    """After chat(), history has user + assistant turns."""

    @pytest.mark.asyncio()
    async def test_history_updated_after_chat(
        self,
        config: AppConfig,
        fake_browser: _FakeBrowserEngine,
    ) -> None:
        """Successful chat adds both a user and assistant turn."""
        parse_resp = _make_parse_response()
        plan_resp = _make_plan_response()

        app = await _init_app(
            config, fake_browser, [parse_resp, plan_resp],
        )

        await app.chat("Go to google.com")

        turns = app._history.turns
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content == "Go to google.com"
        assert turns[1].role == "assistant"
        assert "Completed" in turns[1].content


# ------------------------------------------------------------------ #
# Test 5: Low confidence triggers clarification (Req 9.1)
# ------------------------------------------------------------------ #


class TestLowConfidenceClarification:
    """Low-confidence intent triggers a clarification response."""

    @pytest.mark.asyncio()
    async def test_low_confidence_returns_clarification(
        self,
        config: AppConfig,
        fake_browser: _FakeBrowserEngine,
    ) -> None:
        """When the LLM returns a low-confidence intent, the
        facade asks for clarification instead of executing.
        """
        low_conf_parse = _make_low_confidence_parse_response()
        clarify_resp = "Which button do you want to click?"

        app = await _init_app(
            config,
            fake_browser,
            [low_conf_parse, clarify_resp],
        )

        result = await app.chat("click it")

        assert "Xin hãy làm rõ:" in result
        assert "Which button" in result


# ------------------------------------------------------------------ #
# Test 6: Shutdown cleans up (Req 9.3)
# ------------------------------------------------------------------ #


class TestShutdownCleanup:
    """Verify browser.close() called on shutdown."""

    @pytest.mark.asyncio()
    async def test_shutdown_closes_browser(
        self,
        config: AppConfig,
        fake_browser: _FakeBrowserEngine,
    ) -> None:
        """After shutdown, the browser engine is closed."""
        parse_resp = _make_parse_response()
        plan_resp = _make_plan_response()

        app = await _init_app(
            config, fake_browser, [parse_resp, plan_resp],
        )

        assert not fake_browser.closed

        await app.shutdown()

        assert fake_browser.closed
        assert not app._initialized
