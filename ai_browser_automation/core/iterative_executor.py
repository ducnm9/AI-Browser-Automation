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
from ai_browser_automation.llm.base import LLMRequest
from ai_browser_automation.llm.router import LLMRouter
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
        llm_router: Optional LLM router for content extraction
            fallback when the planner fails to extract data.
        max_iterations: Upper bound on loop iterations.
    """

    def __init__(
        self,
        task_planner: TaskPlanner,
        action_executor: ActionExecutor,
        browser_engine: BrowserEngine,
        llm_router: LLMRouter | None = None,
        max_iterations: int = 10,
    ) -> None:
        self._task_planner = task_planner
        self._action_executor = action_executor
        self._browser_engine = browser_engine
        self._llm_router = llm_router
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
                        intents=intents,
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
                reasoning = next_step_result.reasoning or ""

                # For extraction goals: always use LLM extract
                # from page text to get real data, since the
                # planner LLM often claims goal_reached without
                # including actual content in reasoning.
                if self._is_extraction_goal(intents):
                    extracted = await self._llm_extract(
                        original_goal, intents,
                    )
                    if extracted:
                        reasoning = extracted

                logger.info(
                    "Goal reached on iteration %d",
                    iteration,
                )
                if reasoning:
                    summary_step = ActionStep(
                        action_type="summary",
                        selector_strategy="none",
                        selector_value="",
                    )
                    results.append(ActionResult(
                        success=True,
                        step=summary_step,
                        extracted_data=reasoning,
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

    @staticmethod
    def _is_extraction_goal(
        intents: list[ParsedIntent],
    ) -> bool:
        """Check if intents include a data extraction goal.

        Args:
            intents: Parsed user intents.

        Returns:
            True if any intent (including sub-intents) is
            ``EXTRACT_DATA``.
        """
        from ai_browser_automation.models.intents import (
            IntentType,
        )

        for intent in intents:
            if intent.intent_type is IntentType.EXTRACT_DATA:
                return True
            for sub in intent.sub_intents:
                if sub.intent_type is IntentType.EXTRACT_DATA:
                    return True
        return False

    @staticmethod
    def _reasoning_has_data(reasoning: str) -> bool:
        """Check if reasoning contains actual extracted data.

        Looks for numbered lists or bullet points that indicate
        the LLM included real content rather than a generic
        statement.

        Args:
            reasoning: The reasoning string from the LLM.

        Returns:
            True if the reasoning appears to contain data items.
        """
        import re

        # Check for numbered items (1. ... 2. ... etc.)
        numbered = re.findall(r"\d+\.\s+\S", reasoning)
        if len(numbered) >= 2:
            return True
        # Check for bullet points or dashes
        bullets = re.findall(
            r"^[\-\*\u2022]\s+\S", reasoning, re.M,
        )
        if len(bullets) >= 2:
            return True
        # Check for URLs/links
        links = re.findall(
            r"https?://\S+|href[=:]\S+", reasoning,
        )
        if len(links) >= 2:
            return True
        return False

    async def _llm_extract(
        self,
        original_goal: str,
        intents: list[ParsedIntent],
    ) -> str:
        """Extract data from page text using an LLM call.

        Reads the full page text via ``extract_page_text()``,
        then sends it to the LLM with the user's goal to get
        a structured answer.

        Args:
            original_goal: The user's original goal string.
            intents: Parsed intents (used for limit info).

        Returns:
            LLM-generated summary, or empty string on failure.
        """
        if not self._llm_router:
            return ""

        try:
            page_text = (
                await self._browser_engine.extract_page_text(
                    max_length=15000,
                )
            )
        except BrowserError as exc:
            logger.warning(
                "extract_page_text failed: %s", exc,
            )
            return ""

        if not page_text or len(page_text) < 50:
            return ""

        # Determine limit from intents
        limit = 5
        for intent in intents:
            lim = intent.parameters.get("limit")
            if lim is not None:
                try:
                    limit = int(lim)
                except (TypeError, ValueError):
                    pass
                break
            for sub in intent.sub_intents:
                lim = sub.parameters.get("limit")
                if lim is not None:
                    try:
                        limit = int(lim)
                    except (TypeError, ValueError):
                        pass
                    break

        prompt = (
            "You are a web content extractor. Read the page "
            "text below and extract information to answer "
            "the user's goal.\n\n"
            f"GOAL: {original_goal}\n\n"
            f"Return exactly {limit} items as a numbered "
            "list. For each item include:\n"
            "- The full title\n"
            "- The URL/link (look for URLs in parentheses "
            "next to titles)\n\n"
            "Format each item as:\n"
            "N. Title\n   Link: URL\n\n"
            "Return ONLY the numbered list.\n\n"
            f"PAGE CONTENT:\n{page_text}"
        )

        try:
            response = await self._llm_router.route(
                LLMRequest(prompt=prompt),
            )
            result = response.content.strip()
            if len(result) > 50:
                return result
        except Exception as exc:
            logger.warning(
                "LLM extract fallback failed: %s", exc,
            )
        return ""

    @staticmethod
    def _extract_from_snippets(
        snippets: list[dict],
        intents: list[ParsedIntent],
    ) -> str:
        """Build a data summary directly from content snippets.

        When the LLM fails to include extracted data in its
        reasoning, this fallback reads ``content_snippets``
        from the page context and formats them as a numbered
        list matching the user's intent parameters.

        Args:
            snippets: Content snippets from ``PageContext``.
            intents: Parsed user intents (used for limit).

        Returns:
            Formatted string with extracted items, or empty
            string if snippets are insufficient.
        """
        if not snippets:
            return ""

        # Determine limit from intents
        limit = 5
        for intent in intents:
            lim = intent.parameters.get("limit")
            if lim is not None:
                try:
                    limit = int(lim)
                except (TypeError, ValueError):
                    pass
                break
            for sub in intent.sub_intents:
                lim = sub.parameters.get("limit")
                if lim is not None:
                    try:
                        limit = int(lim)
                    except (TypeError, ValueError):
                        pass
                    break

        # Filter snippets: prefer h3/article with href
        items: list[dict] = []
        for s in snippets:
            text = (s.get("text") or "").strip()
            href = s.get("href") or ""
            tag = s.get("tag") or ""
            if not text or len(text) < 10:
                continue
            if tag in ("h1", "h2") and not href:
                continue
            if href and text:
                items.append({"text": text, "href": href})

        if len(items) < 2:
            return ""

        # Deduplicate by text (keep first occurrence)
        seen: set[str] = set()
        unique: list[dict] = []
        for item in items:
            key = item["text"][:60]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        selected = unique[:limit]
        if not selected:
            return ""

        lines: list[str] = []
        for idx, item in enumerate(selected, start=1):
            lines.append(
                f"{idx}. {item['text']}\n"
                f"   Link: {item['href']}"
            )
        return "\n".join(lines)


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
