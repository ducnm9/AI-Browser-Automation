"""Iterative executor implementing the Observe-Plan-Act loop.

``IterativeExecutor`` orchestrates a loop that observes the current page
context, plans the next step via the LLM, and executes it — repeating
until the goal is reached or the iteration limit is hit.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.2
"""

from __future__ import annotations

import logging

from ai_browser_automation.browser.base import BrowserEngine
from ai_browser_automation.core.action_executor import ActionExecutor
from ai_browser_automation.core.task_planner import TaskPlanner
from ai_browser_automation.exceptions.errors import (
    BrowserError,
    IterativeExecutionError,
    PlanningError,
)
from ai_browser_automation.models.actions import (
    ActionResult,
    ActionStep,
    IterationRecord,
)
from ai_browser_automation.models.intents import ParsedIntent

logger = logging.getLogger(__name__)

_MAX_PLANNING_RETRIES = 2


class IterativeExecutor:
    """Observe-Plan-Act loop executor.

    Receives all dependencies via constructor injection and
    orchestrates the iterative pipeline: observe page context →
    plan next step → execute step, repeating until the LLM signals
    ``goal_reached`` or ``max_iterations`` is exhausted.

    Args:
        task_planner: Planner used to decide each next step.
        action_executor: Executor used to run individual steps.
        browser_engine: Browser engine for observing page context.
        max_iterations: Upper bound on loop iterations.
    """

    def __init__(
        self,
        task_planner: TaskPlanner,
        action_executor: ActionExecutor,
        browser_engine: BrowserEngine,
        max_iterations: int = 10,
    ) -> None:
        self._task_planner = task_planner
        self._action_executor = action_executor
        self._browser_engine = browser_engine
        self.max_iterations = max_iterations

    async def execute(
        self,
        original_goal: str,
        intents: list[ParsedIntent],
    ) -> list[ActionResult]:
        """Run the Observe-Plan-Act loop until completion.

        The loop iterates up to ``max_iterations`` times.  Each
        iteration observes the current page context, asks the
        ``TaskPlanner`` for the next step, and executes it.  The
        loop terminates early when the planner signals
        ``goal_reached=True``.

        Args:
            original_goal: The user's original natural-language
                goal.
            intents: Parsed intents from the NL processor.

        Returns:
            List of ``ActionResult`` objects — one per executed
            step.

        Raises:
            IterativeExecutionError: When a ``BrowserError``
                occurs during ``get_page_context()`` or
                ``execute_step()``.
        """
        results: list[ActionResult] = []
        history: list[IterationRecord] = []
        planning_retries = 0

        logger.info(
            "Starting iterative execution for goal: %s",
            _mask_sensitive(original_goal),
        )

        for iteration in range(1, self.max_iterations + 1):
            logger.debug(
                "Iteration %d/%d",
                iteration,
                self.max_iterations,
            )

            # --- OBSERVE ---
            try:
                page_context = (
                    await self._browser_engine.get_page_context()
                )
            except BrowserError as exc:
                raise IterativeExecutionError(
                    f"BrowserError during get_page_context "
                    f"on iteration {iteration}: {exc}"
                ) from exc

            # --- PLAN ---
            try:
                next_step_result = (
                    await self._task_planner.plan_next_step(
                        original_goal=original_goal,
                        page_context=page_context,
                        history=history,
                    )
                )
                # Reset retry counter on successful planning
                planning_retries = 0
            except PlanningError as exc:
                planning_retries += 1
                logger.warning(
                    "PlanningError on iteration %d "
                    "(retry %d/%d): %s",
                    iteration,
                    planning_retries,
                    _MAX_PLANNING_RETRIES,
                    exc,
                )
                if planning_retries >= _MAX_PLANNING_RETRIES:
                    logger.error(
                        "Max planning retries reached, "
                        "stopping loop",
                    )
                    break
                continue

            # --- CHECK goal_reached ---
            if next_step_result.goal_reached:
                logger.info(
                    "Goal reached on iteration %d: %s",
                    iteration,
                    next_step_result.reasoning,
                )
                if next_step_result.reasoning:
                    summary_step = ActionStep(
                        action_type="summary",
                        selector_strategy="none",
                        selector_value="",
                    )
                    results.append(ActionResult(
                        success=True,
                        step=summary_step,
                        extracted_data=(
                            next_step_result.reasoning
                        ),
                    ))
                break

            step = next_step_result.step

            # --- ACT ---
            try:
                result = (
                    await self._action_executor.execute_step(
                        step,
                    )
                )
            except BrowserError as exc:
                raise IterativeExecutionError(
                    f"BrowserError during execute_step "
                    f"on iteration {iteration}: {exc}"
                ) from exc

            # --- RECORD ---
            record = IterationRecord(
                step=step,
                result=result,
                page_context_before=page_context,
            )
            history.append(record)
            results.append(result)

            if not result.success:
                logger.warning(
                    "Iteration %d failed: %s "
                    "— continuing loop",
                    iteration,
                    result.error_message,
                )

        logger.info(
            "Iterative execution finished with %d results",
            len(results),
        )
        return results


def _mask_sensitive(text: str) -> str:
    """Mask potentially sensitive data for logging.

    Truncates long strings to avoid leaking sensitive content
    into log files.

    Args:
        text: Raw text that may contain sensitive data.

    Returns:
        Masked version safe for log output.
    """
    if len(text) > 200:
        return text[:200] + "..."
    return text


__all__ = ["IterativeExecutor"]
