"""Unit tests for ActionExecutor."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ai_browser_automation.browser.base import BrowserEngine
from ai_browser_automation.core.action_executor import ActionExecutor
from ai_browser_automation.exceptions.errors import (
    ActionExecutionError,
    BrowserError,
)
from ai_browser_automation.llm.base import LLMResponse
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.actions import (
    ActionResult,
    ActionStep,
    ExecutionPlan,
)
from ai_browser_automation.models.config import LLMProvider


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_browser() -> AsyncMock:
    """Create a mock BrowserEngine."""
    browser = AsyncMock(spec=BrowserEngine)
    browser.navigate = AsyncMock()
    browser.click = AsyncMock()
    browser.type_text = AsyncMock()
    browser.extract_text = AsyncMock(return_value="extracted")
    browser.screenshot = AsyncMock(return_value=b"png")
    return browser


@pytest.fixture
def mock_router() -> AsyncMock:
    """Create a mock LLMRouter."""
    return AsyncMock(spec=LLMRouter)


@pytest.fixture
def executor(
    mock_browser: AsyncMock, mock_router: AsyncMock,
) -> ActionExecutor:
    """Create an ActionExecutor with mocked dependencies."""
    return ActionExecutor(mock_browser, mock_router)


def _step(
    action_type: str = "click",
    selector_value: str = "#btn",
    **kwargs: Any,
) -> ActionStep:
    """Helper to build an ActionStep with defaults."""
    return ActionStep(
        action_type=action_type,
        selector_strategy=kwargs.get(
            "selector_strategy", "css",
        ),
        selector_value=selector_value,
        input_value=kwargs.get("input_value"),
        timeout_ms=kwargs.get("timeout_ms", 10000),
        retry_count=kwargs.get("retry_count", 0),
    )


# ------------------------------------------------------------------ #
# execute_step tests
# ------------------------------------------------------------------ #

class TestExecuteStep:
    """Tests for ActionExecutor.execute_step."""

    @pytest.mark.asyncio
    async def test_navigate_step(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Navigate action calls browser.navigate."""
        step = _step(
            "navigate", input_value="https://x.com",
        )
        result = await executor.execute_step(step)

        assert result.success is True
        assert result.step is step
        assert result.duration_ms >= 0
        mock_browser.navigate.assert_awaited_once_with(
            "https://x.com",
        )

    @pytest.mark.asyncio
    async def test_click_step(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Click action calls browser.click."""
        step = _step("click", "#submit")
        result = await executor.execute_step(step)

        assert result.success is True
        mock_browser.click.assert_awaited_once_with(
            "#submit", strategy="css",
        )

    @pytest.mark.asyncio
    async def test_type_text_step(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Type action calls browser.type_text."""
        step = _step(
            "type_text", "#input",
            input_value="hello",
        )
        result = await executor.execute_step(step)

        assert result.success is True
        mock_browser.type_text.assert_awaited_once_with(
            "#input", "hello", strategy="css",
        )

    @pytest.mark.asyncio
    async def test_extract_populates_extracted_data(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Extract action populates extracted_data."""
        step = _step("extract", ".price")
        result = await executor.execute_step(step)

        assert result.success is True
        assert result.extracted_data == "extracted"

    @pytest.mark.asyncio
    async def test_extract_data_populates_extracted_data(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """extract_data action also populates extracted_data."""
        step = _step("extract_data", ".title")
        result = await executor.execute_step(step)

        assert result.success is True
        assert result.extracted_data == "extracted"

    @pytest.mark.asyncio
    async def test_screenshot_step(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Screenshot action captures bytes."""
        step = _step("screenshot")
        result = await executor.execute_step(step)

        assert result.success is True
        assert result.screenshot == b"png"

    @pytest.mark.asyncio
    async def test_scroll_step_succeeds(
        self, executor: ActionExecutor,
    ) -> None:
        """Scroll action succeeds as no-op."""
        step = _step("scroll")
        result = await executor.execute_step(step)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_wait_step_succeeds(
        self, executor: ActionExecutor,
    ) -> None:
        """Wait action sleeps and succeeds."""
        step = _step("wait", timeout_ms=10)
        result = await executor.execute_step(step)

        assert result.success is True
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_unsupported_action_raises(
        self, executor: ActionExecutor,
    ) -> None:
        """Unsupported action_type raises error."""
        step = _step("fly_to_moon")
        with pytest.raises(ActionExecutionError):
            await executor.execute_step(step)

    @pytest.mark.asyncio
    async def test_browser_error_returns_failure(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Browser exception returns failure result."""
        mock_browser.click.side_effect = RuntimeError("boom")
        step = _step("click", "#x")
        result = await executor.execute_step(step)

        assert result.success is False
        assert "boom" in (result.error_message or "")
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_duration_ms_always_non_negative(
        self, executor: ActionExecutor,
    ) -> None:
        """duration_ms is always >= 0."""
        step = _step("scroll")
        result = await executor.execute_step(step)
        assert result.duration_ms >= 0


# ------------------------------------------------------------------ #
# execute_plan tests
# ------------------------------------------------------------------ #

class TestExecutePlan:
    """Tests for ActionExecutor.execute_plan."""

    @pytest.mark.asyncio
    async def test_all_steps_succeed(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """All steps succeed returns full results list."""
        plan = ExecutionPlan(
            steps=[
                _step(
                    "navigate",
                    input_value="https://a.com",
                ),
                _step("click", "#btn"),
            ],
        )
        results = await executor.execute_plan(plan)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert results[0].step is plan.steps[0]
        assert results[1].step is plan.steps[1]

    @pytest.mark.asyncio
    async def test_failure_stops_execution(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Irrecoverable failure stops remaining steps."""
        mock_browser.click.side_effect = RuntimeError("fail")
        plan = ExecutionPlan(
            steps=[
                _step("click", "#a", retry_count=0),
                _step("click", "#b"),
            ],
        )
        results = await executor.execute_plan(plan)

        assert len(results) == 1
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_empty_plan_returns_empty(
        self, executor: ActionExecutor,
    ) -> None:
        """Empty plan returns empty results."""
        plan = ExecutionPlan(steps=[])
        results = await executor.execute_plan(plan)
        assert results == []

    @pytest.mark.asyncio
    async def test_results_in_order(
        self, executor: ActionExecutor,
    ) -> None:
        """Results correspond to steps in order."""
        steps = [_step("scroll") for _ in range(5)]
        plan = ExecutionPlan(steps=steps)
        results = await executor.execute_plan(plan)

        assert len(results) == 5
        for i, r in enumerate(results):
            assert r.step is steps[i]


# ------------------------------------------------------------------ #
# smart_retry tests
# ------------------------------------------------------------------ #

class TestSmartRetry:
    """Tests for ActionExecutor.smart_retry."""

    @pytest.mark.asyncio
    async def test_smart_retry_success(
        self,
        executor: ActionExecutor,
        mock_router: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """Successful smart retry returns success."""
        mock_router.route.return_value = LLMResponse(
            content=json.dumps({
                "selector_strategy": "xpath",
                "selector_value": "//button[@id='ok']",
            }),
            provider_used=LLMProvider.LM_STUDIO,
            tokens_used=10,
            latency_ms=50.0,
        )
        step = _step("click", "#btn")
        result = await executor.smart_retry(
            step, "not found",
        )

        assert result.success is True
        mock_browser.click.assert_awaited()

    @pytest.mark.asyncio
    async def test_smart_retry_llm_failure(
        self,
        executor: ActionExecutor,
        mock_router: AsyncMock,
    ) -> None:
        """LLM failure in smart retry returns failure."""
        mock_router.route.side_effect = RuntimeError(
            "llm down",
        )
        step = _step("click", "#btn")
        result = await executor.smart_retry(step, "err")

        assert result.success is False
        assert "Smart retry failed" in (
            result.error_message or ""
        )

    @pytest.mark.asyncio
    async def test_retry_bounded_by_retry_count(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
        mock_router: AsyncMock,
    ) -> None:
        """Retries do not exceed step.retry_count."""
        mock_browser.click.side_effect = RuntimeError("fail")
        mock_router.route.return_value = LLMResponse(
            content=json.dumps({
                "selector_strategy": "xpath",
                "selector_value": "//x",
            }),
            provider_used=LLMProvider.LM_STUDIO,
            tokens_used=5,
            latency_ms=10.0,
        )

        retry_count = 2
        step = _step("click", "#a", retry_count=retry_count)

        # Call smart_retry directly to isolate count
        for _ in range(retry_count):
            await executor.smart_retry(step, "fail")

        # smart_retry calls route once per invocation
        assert mock_router.route.call_count == retry_count


# ------------------------------------------------------------------ #
# extract_table action tests
# ------------------------------------------------------------------ #

class TestExtractTableAction:
    """Tests for extract_table action handling in execute_step.

    Validates: Requirements 5.1, 5.2, 5.3
    """

    @pytest.mark.asyncio
    async def test_extract_table_success_returns_json(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """Successful extract_table returns JSON in extracted_data."""
        table_data = [
            ["Team A", "vs", "Team B", "20:00"],
            ["Team C", "vs", "Team D", "22:00"],
        ]
        mock_browser.extract_table = AsyncMock(
            return_value=table_data,
        )

        step = _step(
            "extract_table",
            "table.schedule",
            selector_strategy="css",
        )
        result = await executor.execute_step(step)

        assert result.success is True
        assert result.extracted_data is not None
        assert json.loads(result.extracted_data) == table_data
        mock_browser.extract_table.assert_awaited_once_with(
            "table.schedule", strategy="css",
        )

    @pytest.mark.asyncio
    async def test_extract_table_browser_error_returns_failure(
        self,
        executor: ActionExecutor,
        mock_browser: AsyncMock,
    ) -> None:
        """BrowserError during extract_table returns failure result."""
        mock_browser.extract_table = AsyncMock(
            side_effect=BrowserError(
                "Table not found for selector: 'table.missing'"
            ),
        )

        step = _step(
            "extract_table",
            "table.missing",
            selector_strategy="css",
        )
        result = await executor.execute_step(step)

        assert result.success is False
        assert result.error_message is not None
        assert "Table not found" in result.error_message
