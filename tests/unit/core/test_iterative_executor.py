"""Unit tests for IterativeExecutor.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.2
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ai_browser_automation.browser.base import BrowserEngine, PageContext
from ai_browser_automation.core.action_executor import ActionExecutor
from ai_browser_automation.core.iterative_executor import (
    IterativeExecutor,
)
from ai_browser_automation.core.task_planner import TaskPlanner
from ai_browser_automation.exceptions.errors import (
    BrowserError,
    IterativeExecutionError,
    PlanningError,
)
from ai_browser_automation.models.actions import (
    ActionResult,
    ActionStep,
    NextStepResult,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _page_ctx(
    url: str = "http://example.com",
) -> PageContext:
    """Build a minimal PageContext for tests."""
    return PageContext(
        url=url, title="Test", dom_summary="<div/>"
    )


def _step(
    action: str = "click", selector: str = "#btn",
) -> ActionStep:
    """Build a minimal ActionStep for tests."""
    return ActionStep(
        action_type=action,
        selector_strategy="css",
        selector_value=selector,
    )


def _ok_result(
    step: ActionStep | None = None,
) -> ActionResult:
    """Build a successful ActionResult."""
    return ActionResult(success=True, step=step or _step())


def _fail_result(
    step: ActionStep | None = None,
) -> ActionResult:
    """Build a failed ActionResult."""
    s = step or _step()
    return ActionResult(
        success=False, step=s, error_message="boom",
    )


def _goal_reached(
    reasoning: str = "done",
) -> NextStepResult:
    """Build a goal-reached NextStepResult."""
    return NextStepResult(
        step=None, goal_reached=True, reasoning=reasoning,
    )


def _next_step(
    step: ActionStep | None = None,
) -> NextStepResult:
    """Build a next-step NextStepResult."""
    return NextStepResult(
        step=step or _step(),
        goal_reached=False,
        reasoning="next",
    )


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_planner() -> AsyncMock:
    """Mocked TaskPlanner."""
    return AsyncMock(spec=TaskPlanner)


@pytest.fixture
def mock_action_executor() -> AsyncMock:
    """Mocked ActionExecutor."""
    return AsyncMock(spec=ActionExecutor)


@pytest.fixture
def mock_browser() -> AsyncMock:
    """Mocked BrowserEngine with default page context."""
    engine = AsyncMock(spec=BrowserEngine)
    engine.get_page_context.return_value = _page_ctx()
    return engine


# ------------------------------------------------------------------ #
# Tests: goal_reached stops loop
# ------------------------------------------------------------------ #


class TestGoalReached:
    """Loop terminates when planner signals goal_reached."""

    @pytest.mark.asyncio
    async def test_goal_reached_first_iteration(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """goal_reached on first iteration returns summary."""
        mock_planner.plan_next_step.return_value = (
            _goal_reached()
        )

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=10,
        )
        results = await executor.execute("goal", [])

        assert len(results) == 1
        assert results[0].step.action_type == "summary"
        assert results[0].extracted_data == "done"
        mock_action_executor.execute_step.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_goal_reached_after_three_iterations(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """goal_reached after 3 iterations returns 3+1 results."""
        steps = [_step(selector=f"#s{i}") for i in range(3)]
        plan_responses = [_next_step(s) for s in steps]
        plan_responses.append(_goal_reached())
        mock_planner.plan_next_step.side_effect = (
            plan_responses
        )

        results_list = [_ok_result(s) for s in steps]
        mock_action_executor.execute_step.side_effect = (
            results_list
        )

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=10,
        )
        results = await executor.execute("goal", [])

        # 3 action results + 1 summary from goal_reached
        assert len(results) == 4
        assert all(r.success for r in results)
        assert results[3].step.action_type == "summary"


# ------------------------------------------------------------------ #
# Tests: max_iterations stops loop
# ------------------------------------------------------------------ #


class TestMaxIterations:
    """Loop terminates at max_iterations."""

    @pytest.mark.asyncio
    async def test_max_iterations_reached(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """Returns all results when max_iterations exhausted."""
        max_iter = 5
        mock_planner.plan_next_step.return_value = (
            _next_step()
        )
        mock_action_executor.execute_step.return_value = (
            _ok_result()
        )

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=max_iter,
        )
        results = await executor.execute("goal", [])

        assert len(results) == max_iter


# ------------------------------------------------------------------ #
# Tests: step failure recorded, loop continues
# ------------------------------------------------------------------ #


class TestStepFailure:
    """Failed steps are recorded and loop continues."""

    @pytest.mark.asyncio
    async def test_step_failure_recorded_loop_continues(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """Failed step recorded in results, loop continues."""
        plan_responses = [
            _next_step(),
            _next_step(),
            _goal_reached(),
        ]
        mock_planner.plan_next_step.side_effect = (
            plan_responses
        )

        fail = _fail_result()
        ok = _ok_result()
        mock_action_executor.execute_step.side_effect = [
            fail, ok,
        ]

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=10,
        )
        results = await executor.execute("goal", [])

        # 2 action results + 1 summary from goal_reached
        assert len(results) == 3
        assert results[0].success is False
        assert results[1].success is True
        assert results[2].step.action_type == "summary"


# ------------------------------------------------------------------ #
# Tests: PlanningError retry
# ------------------------------------------------------------------ #


class TestPlanningErrorRetry:
    """PlanningError triggers retry up to 2 times."""

    @pytest.mark.asyncio
    async def test_planning_error_retry_succeeds(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """PlanningError on first try, succeeds on second."""
        mock_planner.plan_next_step.side_effect = [
            PlanningError("bad json"),
            _next_step(),
            _goal_reached(),
        ]
        mock_action_executor.execute_step.return_value = (
            _ok_result()
        )

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=10,
        )
        results = await executor.execute("goal", [])

        # 1 action result + 1 summary from goal_reached
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].step.action_type == "summary"

    @pytest.mark.asyncio
    async def test_planning_error_two_times_stops_loop(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """Two consecutive PlanningErrors stop the loop."""
        mock_planner.plan_next_step.side_effect = [
            PlanningError("fail 1"),
            PlanningError("fail 2"),
        ]

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=10,
        )
        results = await executor.execute("goal", [])

        assert results == []
        mock_action_executor.execute_step.assert_not_awaited()


# ------------------------------------------------------------------ #
# Tests: BrowserError raises IterativeExecutionError
# ------------------------------------------------------------------ #


class TestBrowserErrorHandling:
    """BrowserError raises IterativeExecutionError."""

    @pytest.mark.asyncio
    async def test_browser_error_from_get_page_context(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """BrowserError in get_page_context raises."""
        mock_browser.get_page_context.side_effect = (
            BrowserError("crash")
        )

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=10,
        )

        with pytest.raises(IterativeExecutionError):
            await executor.execute("goal", [])

    @pytest.mark.asyncio
    async def test_browser_error_from_execute_step(
        self,
        mock_planner: AsyncMock,
        mock_action_executor: AsyncMock,
        mock_browser: AsyncMock,
    ) -> None:
        """BrowserError in execute_step raises."""
        mock_planner.plan_next_step.return_value = (
            _next_step()
        )
        mock_action_executor.execute_step.side_effect = (
            BrowserError("disconnect")
        )

        executor = IterativeExecutor(
            task_planner=mock_planner,
            action_executor=mock_action_executor,
            browser_engine=mock_browser,
            max_iterations=10,
        )

        with pytest.raises(IterativeExecutionError):
            await executor.execute("goal", [])
