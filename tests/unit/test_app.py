"""Unit tests for AIBrowserAutomation facade (app.py).

Tests cover __init__, initialize, chat pipeline, shutdown,
error handling, sensitive-data routing, and confidence checks.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_browser_automation.app import (
    AIBrowserAutomation,
    _format_results,
)
from ai_browser_automation.browser.base import PageContext
from ai_browser_automation.exceptions.errors import (
    AppError,
    NLProcessingError,
)
from ai_browser_automation.models.actions import (
    ActionResult,
    ActionStep,
    ExecutionPlan,
)
from ai_browser_automation.models.config import (
    AppConfig,
    LLMProvider,
)
from ai_browser_automation.models.intents import (
    IntentType,
    ParsedIntent,
)


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture()
def config() -> AppConfig:
    """Minimal config for testing."""
    return AppConfig(
        lm_studio_url="http://localhost:1234/v1",
    )


@pytest.fixture()
def app(config: AppConfig) -> AIBrowserAutomation:
    """Un-initialised facade instance."""
    return AIBrowserAutomation(config)


def _make_step(action_type: str = "click") -> ActionStep:
    return ActionStep(
        action_type=action_type,
        selector_strategy="css",
        selector_value="#btn",
    )


def _make_result(
    success: bool = True,
    action_type: str = "click",
    error_message: str | None = None,
    extracted_data: str | None = None,
) -> ActionResult:
    return ActionResult(
        success=success,
        step=_make_step(action_type),
        error_message=error_message,
        extracted_data=extracted_data,
    )


# ------------------------------------------------------------------ #
# _format_results
# ------------------------------------------------------------------ #

class TestFormatResults:
    def test_empty_results(self) -> None:
        assert _format_results([]) == "No actions were executed."

    def test_all_success(self) -> None:
        results = [_make_result(), _make_result()]
        text = _format_results(results)
        assert "Completed 2/2 actions." in text
        assert "[OK]" in text

    def test_mixed_results(self) -> None:
        results = [
            _make_result(success=True),
            _make_result(
                success=False,
                error_message="timeout",
            ),
        ]
        text = _format_results(results)
        assert "Completed 1/2 actions." in text
        assert "[FAIL]" in text
        assert "timeout" in text

    def test_extracted_data_shown(self) -> None:
        results = [
            _make_result(extracted_data="some data"),
        ]
        text = _format_results(results)
        assert "some data" in text


# ------------------------------------------------------------------ #
# __init__
# ------------------------------------------------------------------ #

class TestInit:
    def test_stores_config(
        self, app: AIBrowserAutomation, config: AppConfig,
    ) -> None:
        assert app._config is config

    def test_components_none_before_init(
        self, app: AIBrowserAutomation,
    ) -> None:
        assert app._security is None
        assert app._llm_router is None
        assert app._browser_engine is None
        assert app._nl_processor is None
        assert app._task_planner is None
        assert app._action_executor is None

    def test_not_initialized(
        self, app: AIBrowserAutomation,
    ) -> None:
        assert app._initialized is False

    def test_history_created(
        self, app: AIBrowserAutomation,
    ) -> None:
        assert app._history is not None
        assert len(app._history.turns) == 0


# ------------------------------------------------------------------ #
# initialize
# ------------------------------------------------------------------ #

class TestInitialize:
    @pytest.mark.asyncio()
    async def test_initialize_sets_all_components(
        self, app: AIBrowserAutomation,
    ) -> None:
        mock_engine = AsyncMock()
        with patch(
            "ai_browser_automation.app"
            ".BrowserEngineFactory.create",
            return_value=mock_engine,
        ):
            await app.initialize()

        assert app._initialized is True
        assert app._security is not None
        assert app._llm_router is not None
        assert app._browser_engine is mock_engine
        assert app._nl_processor is not None
        assert app._task_planner is not None
        assert app._action_executor is not None

    @pytest.mark.asyncio()
    async def test_initialize_launches_browser(
        self, app: AIBrowserAutomation,
    ) -> None:
        mock_engine = AsyncMock()
        with patch(
            "ai_browser_automation.app"
            ".BrowserEngineFactory.create",
            return_value=mock_engine,
        ):
            await app.initialize()

        mock_engine.launch.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_initialize_registers_providers(
        self, app: AIBrowserAutomation,
    ) -> None:
        mock_engine = AsyncMock()
        with patch(
            "ai_browser_automation.app"
            ".BrowserEngineFactory.create",
            return_value=mock_engine,
        ):
            await app.initialize()

        assert app._llm_router is not None
        assert len(app._llm_router.providers) > 0

    @pytest.mark.asyncio()
    async def test_initialize_browser_failure_raises(
        self, app: AIBrowserAutomation,
    ) -> None:
        with (
            patch(
                "ai_browser_automation.app"
                ".BrowserEngineFactory.create",
                side_effect=RuntimeError("no browser"),
            ),
            pytest.raises(AppError, match="browser engine"),
        ):
            await app.initialize()


# ------------------------------------------------------------------ #
# chat
# ------------------------------------------------------------------ #

def _init_app_with_mocks(
    app: AIBrowserAutomation,
) -> dict[str, AsyncMock]:
    """Wire mock components into an app instance."""
    from ai_browser_automation.models.config import SecurityPolicy
    from ai_browser_automation.security.security_layer import (
        SecurityLayer,
    )

    app._security = SecurityLayer(SecurityPolicy())
    app._llm_router = MagicMock()
    app._browser_engine = AsyncMock()
    app._nl_processor = AsyncMock()
    app._task_planner = AsyncMock()
    app._action_executor = AsyncMock()
    app._initialized = True

    return {
        "browser": app._browser_engine,
        "nl": app._nl_processor,
        "planner": app._task_planner,
        "executor": app._action_executor,
    }


class TestChat:
    @pytest.mark.asyncio()
    async def test_not_initialized_returns_error(
        self, app: AIBrowserAutomation,
    ) -> None:
        result = await app.chat("hello")
        assert "not initialized" in result

    @pytest.mark.asyncio()
    async def test_full_pipeline_success(
        self, app: AIBrowserAutomation,
    ) -> None:
        mocks = _init_app_with_mocks(app)

        intent = ParsedIntent(
            intent_type=IntentType.NAVIGATE,
            target_description="google",
            confidence=0.9,
        )
        mocks["nl"].parse.return_value = [intent]
        mocks["browser"].get_page_context.return_value = (
            PageContext(
                url="http://example.com",
                title="Example",
                dom_summary="",
            )
        )
        plan = ExecutionPlan(
            steps=[_make_step()], description="test",
        )
        mocks["planner"].plan.return_value = plan
        mocks["executor"].execute_plan.return_value = [
            _make_result(),
        ]

        result = await app.chat("Go to google.com")

        assert "Completed 1/1 actions." in result
        assert len(app._history.turns) == 2

    @pytest.mark.asyncio()
    async def test_low_confidence_returns_clarification(
        self, app: AIBrowserAutomation,
    ) -> None:
        mocks = _init_app_with_mocks(app)

        intent = ParsedIntent(
            intent_type=IntentType.CLICK,
            target_description="something",
            confidence=0.3,
        )
        mocks["nl"].parse.return_value = [intent]
        mocks["nl"].clarify.return_value = "Which button?"

        result = await app.chat("click it")

        assert result.startswith("Xin hãy làm rõ:")
        assert "Which button?" in result
        mocks["planner"].plan.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_sensitive_data_routes_to_local(
        self, app: AIBrowserAutomation,
    ) -> None:
        mocks = _init_app_with_mocks(app)

        intent = ParsedIntent(
            intent_type=IntentType.LOGIN,
            target_description="login",
            confidence=0.95,
        )
        mocks["nl"].parse.return_value = [intent]
        mocks["browser"].get_page_context.return_value = (
            PageContext(
                url="http://bank.com",
                title="Bank",
                dom_summary="",
            )
        )
        plan = ExecutionPlan(
            steps=[_make_step()], description="login",
        )
        mocks["planner"].plan.return_value = plan
        mocks["executor"].execute_plan.return_value = [
            _make_result(),
        ]

        # Input with password triggers local routing
        await app.chat("password: secret123")

        assert app._llm_router is not None
        assert (
            app._llm_router.default_provider
            == LLMProvider.LM_STUDIO
        )

    @pytest.mark.asyncio()
    async def test_pipeline_error_returns_message(
        self, app: AIBrowserAutomation,
    ) -> None:
        mocks = _init_app_with_mocks(app)
        mocks["nl"].parse.side_effect = NLProcessingError(
            "parse failed",
        )

        result = await app.chat("do something")

        assert "Error:" in result
        assert "parse failed" in result

    @pytest.mark.asyncio()
    async def test_unexpected_error_returns_message(
        self, app: AIBrowserAutomation,
    ) -> None:
        mocks = _init_app_with_mocks(app)
        mocks["nl"].parse.side_effect = RuntimeError("boom")

        result = await app.chat("do something")

        assert "Unexpected error:" in result


# ------------------------------------------------------------------ #
# shutdown
# ------------------------------------------------------------------ #

class TestShutdown:
    @pytest.mark.asyncio()
    async def test_shutdown_closes_browser(
        self, app: AIBrowserAutomation,
    ) -> None:
        mock_engine = AsyncMock()
        app._browser_engine = mock_engine
        app._initialized = True

        await app.shutdown()

        mock_engine.close.assert_awaited_once()
        assert app._initialized is False

    @pytest.mark.asyncio()
    async def test_shutdown_safe_when_not_initialized(
        self, app: AIBrowserAutomation,
    ) -> None:
        await app.shutdown()
        assert app._initialized is False

    @pytest.mark.asyncio()
    async def test_shutdown_handles_close_error(
        self, app: AIBrowserAutomation,
    ) -> None:
        mock_engine = AsyncMock()
        mock_engine.close.side_effect = RuntimeError("fail")
        app._browser_engine = mock_engine
        app._initialized = True

        await app.shutdown()

        assert app._initialized is False
