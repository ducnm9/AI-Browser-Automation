"""Action executor that runs browser action plans with smart retry.

``ActionExecutor`` sequentially executes each ``ActionStep`` in an
``ExecutionPlan``, recording timing and extracted data.  When a step
fails it applies an AI-powered retry strategy (via ``LLMRouter``) and,
if that is also unsuccessful, asks the ``TaskPlanner`` to replan before
giving up.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from ai_browser_automation.browser.base import BrowserEngine
from ai_browser_automation.core.task_planner import TaskPlanner
from ai_browser_automation.exceptions.errors import ActionExecutionError
from ai_browser_automation.llm.base import LLMRequest
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.actions import (
    ActionResult,
    ActionStep,
    ExecutionPlan,
)

logger = logging.getLogger(__name__)

_EXTRACT_ACTIONS = {"extract", "extract_data"}

_SMART_RETRY_PROMPT = """\
A browser automation step failed. Analyse the error and suggest an \
alternative selector to achieve the same goal.

Return ONLY valid JSON (no markdown fences) with this schema:
{{
  "selector_strategy": "<css|xpath|text|ai_vision>",
  "selector_value": "<alternative selector>"
}}

Failed step:
  action_type: {action_type}
  selector_strategy: {selector_strategy}
  selector_value: {selector_value}
  input_value: {input_value}

Error: {error}
"""


class ActionExecutor:
    """Execute browser action plans with smart retry and replanning.

    The executor walks through each step in an ``ExecutionPlan``
    sequentially.  On failure it first attempts AI-powered smart
    retries (bounded by ``step.retry_count``), then falls back to
    replanning via ``TaskPlanner``.  If all recovery strategies are
    exhausted the executor stops and returns results collected so far.

    Args:
        browser_engine: Browser engine used to perform actions.
        llm_router: Router for AI-powered retry analysis.
    """

    def __init__(
        self,
        browser_engine: BrowserEngine,
        llm_router: LLMRouter,
    ) -> None:
        self.browser = browser_engine
        self.llm_router = llm_router

    async def execute_plan(
        self, plan: ExecutionPlan,
    ) -> list[ActionResult]:
        """Execute all steps in *plan* sequentially.

        Each step is executed via ``execute_step``.  On failure the
        executor tries smart retry (up to ``step.retry_count`` times)
        followed by replanning.  If recovery fails the loop breaks
        and results collected so far (including the failed step) are
        returned.

        Args:
            plan: The execution plan containing ordered steps.

        Returns:
            Ordered list of ``ActionResult`` — one per executed
            step.  ``len(results) == len(steps executed)``.
        """
        results: list[ActionResult] = []
        screenshot: Optional[bytes] = None

        for step in plan.steps:
            result = await self.execute_step(step)

            if not result.success:
                # --- smart retry phase ---
                for _attempt in range(step.retry_count):
                    try:
                        screenshot = (
                            await self.browser.screenshot()
                        )
                    except Exception:
                        screenshot = None

                    retry_result = await self.smart_retry(
                        step,
                        result.error_message or "unknown error",
                    )
                    if retry_result.success:
                        result = retry_result
                        break

                # --- replan phase ---
                if not result.success:
                    try:
                        if screenshot is None:
                            screenshot = (
                                await self.browser.screenshot()
                            )
                    except Exception:
                        screenshot = b""

                    try:
                        planner = TaskPlanner(self.llm_router)
                        new_steps = await planner.replan(
                            step,
                            result.error_message
                            or "unknown error",
                            screenshot or b"",
                        )
                    except Exception as exc:
                        logger.warning(
                            "Replan failed: %s", exc,
                        )
                        new_steps = []

                    for new_step in new_steps:
                        alt_result = await self.execute_step(
                            new_step,
                        )
                        if alt_result.success:
                            result = alt_result
                            break

            results.append(result)

            if not result.success:
                logger.error(
                    "Step '%s' failed irrecoverably: %s",
                    step.action_type,
                    result.error_message,
                )
                break

        return results

    async def execute_step(
        self, step: ActionStep,
    ) -> ActionResult:
        """Execute a single action step on the browser.

        Maps ``step.action_type`` to the corresponding
        ``BrowserEngine`` method, measures wall-clock duration,
        and populates ``extracted_data`` for extract actions.

        Args:
            step: The action step to execute.

        Returns:
            ``ActionResult`` with timing and outcome information.
        """
        import asyncio

        start = time.monotonic()
        extracted_data: Optional[str] = None
        screenshot: Optional[bytes] = None

        try:
            action = step.action_type.lower()

            if action == "navigate":
                await self.browser.navigate(
                    step.input_value or step.selector_value,
                )

            elif action == "click":
                await self.browser.click(
                    step.selector_value,
                    strategy=step.selector_strategy,
                )

            elif action in {"type", "type_text"}:
                await self.browser.type_text(
                    step.selector_value,
                    step.input_value or "",
                    strategy=step.selector_strategy,
                )

            elif action in _EXTRACT_ACTIONS:
                extracted_data = (
                    await self.browser.extract_text(
                        step.selector_value,
                        strategy=step.selector_strategy,
                    )
                )

            elif action == "screenshot":
                screenshot = await self.browser.screenshot()

            elif action == "scroll":
                logger.debug(
                    "Scroll action is a no-op at engine level",
                )

            elif action == "wait":
                wait_ms = step.timeout_ms
                await asyncio.sleep(wait_ms / 1000.0)

            else:
                raise ActionExecutionError(
                    f"Unsupported action_type: "
                    f"'{step.action_type}'"
                )

            duration_ms = (
                (time.monotonic() - start) * 1000.0
            )

            return ActionResult(
                success=True,
                step=step,
                extracted_data=extracted_data,
                screenshot=screenshot,
                duration_ms=duration_ms,
            )

        except ActionExecutionError:
            raise
        except Exception as exc:
            duration_ms = (
                (time.monotonic() - start) * 1000.0
            )
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Step '%s' failed: %s",
                step.action_type,
                error_msg,
            )
            return ActionResult(
                success=False,
                step=step,
                error_message=error_msg,
                duration_ms=duration_ms,
            )

    async def smart_retry(
        self, step: ActionStep, error: str,
    ) -> ActionResult:
        """Use AI to analyse *error* and retry with alternative.

        The LLM is asked to suggest a different selector strategy
        and value.  If the suggestion is valid a new step is built
        and executed.

        Args:
            step: The step that originally failed.
            error: Human-readable error description.

        Returns:
            ``ActionResult`` from the alternative attempt, or a
            failure result when the LLM cannot help.
        """
        prompt = _SMART_RETRY_PROMPT.format(
            action_type=step.action_type,
            selector_strategy=step.selector_strategy,
            selector_value=step.selector_value,
            input_value=step.input_value,
            error=error,
        )

        try:
            response = await self.llm_router.route(
                LLMRequest(prompt=prompt),
            )
            suggestion = json.loads(
                response.content.strip(),
            )
            new_strategy = suggestion.get(
                "selector_strategy",
                step.selector_strategy,
            )
            new_value = suggestion.get(
                "selector_value",
                step.selector_value,
            )
        except Exception as exc:
            logger.warning(
                "Smart retry LLM call failed: %s", exc,
            )
            return ActionResult(
                success=False,
                step=step,
                error_message=f"Smart retry failed: {exc}",
                duration_ms=0.0,
            )

        alt_step = ActionStep(
            action_type=step.action_type,
            selector_strategy=new_strategy,
            selector_value=new_value,
            input_value=step.input_value,
            wait_condition=step.wait_condition,
            timeout_ms=step.timeout_ms,
            retry_count=step.retry_count,
        )

        logger.info(
            "Smart retry: switching selector from "
            "'%s' (%s) to '%s' (%s)",
            step.selector_value,
            step.selector_strategy,
            new_value,
            new_strategy,
        )

        return await self.execute_step(alt_step)


__all__ = ["ActionExecutor"]
