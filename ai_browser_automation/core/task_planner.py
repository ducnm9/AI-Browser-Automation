"""Task planner that converts parsed intents into executable action plans.

``TaskPlanner`` uses an LLM to translate high-level ``ParsedIntent`` objects
into concrete ``ExecutionPlan`` instances containing ordered ``ActionStep``
sequences.  It also supports replanning when a step fails at execution time.

Requirements: 2.1, 2.2, 2.3
"""

from __future__ import annotations

import json
import logging

from ai_browser_automation.browser.base import PageContext
from ai_browser_automation.exceptions.errors import PlanningError
from ai_browser_automation.llm.base import LLMRequest, LLMResponse
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.actions import (
    ActionStep,
    ExecutionPlan,
    IterationRecord,
    NextStepResult,
)
from ai_browser_automation.models.intents import IntentType, ParsedIntent

logger = logging.getLogger(__name__)

_VALID_ACTION_TYPES = {
    "navigate", "click", "type", "type_text", "wait",
    "extract", "extract_data", "extract_table", "scroll",
    "screenshot", "login",
}

_VALID_SELECTOR_STRATEGIES = {"css", "xpath", "text", "ai_vision"}

_MIN_TIMEOUT_MS = 1000
_MAX_TIMEOUT_MS = 60000
_DEFAULT_TIMEOUT_MS = 10000
_DEFAULT_RETRY_COUNT = 3

_MAX_ELEMENTS_JSON_CHARS = 4000


def _compact_elements_json(
    elements: list[dict],
    max_chars: int = _MAX_ELEMENTS_JSON_CHARS,
) -> str:
    """Serialize visible elements as compact JSON, capped by size.

    Uses ``separators=(",", ":")`` to minimise whitespace and
    truncates the output to *max_chars* so the LLM prompt stays
    within the model's context window.

    Args:
        elements: Visible interactable elements from the page.
        max_chars: Maximum character length for the output.

    Returns:
        Compact JSON string, possibly truncated with ``"…]"``.
    """
    raw = json.dumps(elements, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + "…]"

_PLAN_PROMPT_TEMPLATE = """\
You are a browser automation task planner.
Given user intents and the current page context, produce an execution plan.

Return ONLY valid JSON (no markdown fences) with this schema:
{{
  "steps": [
    {{
      "action_type": "<one of: navigate, click, type, type_text, \
wait, extract, extract_data, scroll, screenshot, login>",
      "selector_strategy": "<one of: css, xpath, text, ai_vision>",
      "selector_value": "<selector expression or description>",
      "input_value": "<text to type or URL, or null>",
      "wait_condition": "<JS expression or null>",
      "timeout_ms": <int 1000-60000>,
      "retry_count": <int 0-10>
    }}
  ],
  "description": "<human-readable summary>",
  "estimated_duration_ms": <int>
}}

Rules:
- Choose selector_strategy based on available page elements:
  * Use "css" when elements have unique id/class attributes.
  * Use "xpath" when the DOM structure is the best locator.
  * Use "text" when the element is best identified by visible text.
  * Use "ai_vision" as a last resort when no reliable selector exists.
- Every step MUST have a non-empty selector_value.
- timeout_ms must be between 1000 and 60000.
- Return at least one step.

Page context:
URL: {url}
Title: {title}
DOM summary: {dom_summary}
Visible elements: {visible_elements}

User intents:
{intents_json}
"""

_REPLAN_PROMPT_TEMPLATE = """\
You are a browser automation task planner.
A previous action step failed. Analyse the error and produce \
alternative steps to achieve the same goal.

Return ONLY valid JSON (no markdown fences) with this schema:
{{
  "steps": [
    {{
      "action_type": "<action type>",
      "selector_strategy": "<css|xpath|text|ai_vision>",
      "selector_value": "<selector>",
      "input_value": "<value or null>",
      "wait_condition": "<condition or null>",
      "timeout_ms": <int>,
      "retry_count": <int>
    }}
  ]
}}

Rules:
- Try a DIFFERENT selector_strategy than the one that failed.
- Return at least one alternative step.
- timeout_ms must be between 1000 and 60000.

Failed step:
  action_type: {action_type}
  selector_strategy: {selector_strategy}
  selector_value: {selector_value}
  input_value: {input_value}

Error message: {error}
Screenshot available: {has_screenshot}
"""


_PLAN_NEXT_STEP_TEMPLATE = """\
You are a browser automation assistant executing a multi-step task.
Given the original goal, current page context, and history of previous \
steps, decide the NEXT single action to take.

Return ONLY valid JSON (no markdown fences) with this schema:
{{
  "goal_reached": <true|false>,
  "reasoning": "<brief explanation of your decision>",
  "step": {{
    "action_type": "<one of: navigate, click, type, type_text, \
wait, extract, extract_data, extract_table, scroll, screenshot, login>",
    "selector_strategy": "<one of: css, xpath, text, ai_vision>",
    "selector_value": "<selector expression or description>",
    "input_value": "<text to type or URL, or null>",
    "wait_condition": "<JS expression or null>",
    "timeout_ms": <int 1000-60000>,
    "retry_count": <int 0-10>
  }}
}}

Rules:
- If the goal is fully achieved based on the page context and history, \
set "goal_reached" to true and set "step" to null.
- If more actions are needed, set "goal_reached" to false and provide \
the next single step.
- Use history to avoid repeating failed actions.
- Every step MUST have a non-empty selector_value.
- timeout_ms must be between 1000 and 60000.
- IMPORTANT: If the user's goal involves reading, searching, or \
retrieving information from a page, you MUST use an extract action \
(extract, extract_data, or extract_table) to capture the relevant \
content BEFORE setting goal_reached to true. Do NOT set goal_reached \
to true until the requested data has been extracted.
- When setting goal_reached to true, include a concise summary of \
the results or findings in the "reasoning" field.
- Use the "Content on page" section below to understand what data \
is available. Use CSS selectors from content snippets to target \
the right elements for extraction.
- For news/article extraction, prefer using a broad CSS selector \
that captures multiple items (e.g. a class shared by article \
containers) rather than extracting one item at a time.
- If the goal asks for a specific number of items (e.g. "5 tin moi \
nhat"), use extract_data with a selector that matches the article \
list container, then summarise in the goal_reached reasoning.

Original goal: {original_goal}

Current page context:
URL: {url}
Title: {title}
DOM summary: {dom_summary}
Visible elements: {visible_elements}

Content on page:
{content_snippets}

Previous steps:
{history}
"""


class TaskPlanner:
    """Convert parsed intents into an executable browser action plan.

    The planner sends structured prompts to an LLM (via ``LLMRouter``)
    to determine the concrete action steps, selector strategies, and
    timeouts required to fulfil the user's intents on the current page.

    Args:
        llm_router: Router used to send prompts to an LLM provider.
    """

    def __init__(self, llm_router: LLMRouter) -> None:
        self.llm_router = llm_router

    async def plan(
        self,
        intents: list[ParsedIntent],
        page_context: PageContext,
    ) -> ExecutionPlan:
        """Create an execution plan from intents and page context.

        Composite intents are expanded so that their ``sub_intents``
        are included in the prompt alongside top-level intents.

        Args:
            intents: Parsed user intents to plan for.
            page_context: Current browser page snapshot.

        Returns:
            An ``ExecutionPlan`` with at least one step.

        Raises:
            PlanningError: When the LLM call fails or the response
                cannot be parsed into a valid plan.
        """
        expanded = self._expand_intents(intents)
        intents_json = json.dumps(
            [self._intent_to_dict(i) for i in expanded],
            indent=2,
        )

        prompt = _PLAN_PROMPT_TEMPLATE.format(
            url=page_context.url,
            title=page_context.title,
            dom_summary=page_context.dom_summary,
            visible_elements=_compact_elements_json(
                page_context.visible_elements,
            ),
            intents_json=intents_json,
        )

        logger.debug("Sending plan request to LLM")

        try:
            response: LLMResponse = await self.llm_router.route(
                LLMRequest(prompt=prompt),
            )
        except Exception as exc:
            raise PlanningError(
                f"LLM request failed during planning: {exc}"
            ) from exc

        return self._parse_plan_response(response.content)

    async def replan(
        self,
        failed_step: ActionStep,
        error: str,
        screenshot: bytes,
    ) -> list[ActionStep]:
        """Produce alternative steps after a step failure.

        Args:
            failed_step: The step that failed execution.
            error: Human-readable error description.
            screenshot: Screenshot bytes of the page at failure time.

        Returns:
            A non-empty list of alternative ``ActionStep`` objects.

        Raises:
            PlanningError: When the LLM call fails or the response
                cannot be parsed.
        """
        prompt = _REPLAN_PROMPT_TEMPLATE.format(
            action_type=failed_step.action_type,
            selector_strategy=failed_step.selector_strategy,
            selector_value=failed_step.selector_value,
            input_value=failed_step.input_value,
            error=error,
            has_screenshot=bool(screenshot),
        )

        logger.debug(
            "Sending replan request for failed step: %s",
            failed_step.action_type,
        )

        try:
            response: LLMResponse = await self.llm_router.route(
                LLMRequest(prompt=prompt),
            )
        except Exception as exc:
            raise PlanningError(
                f"LLM request failed during replanning: {exc}"
            ) from exc

        return self._parse_steps(response.content)

    async def plan_next_step(
        self,
        original_goal: str,
        page_context: PageContext,
        history: list[IterationRecord],
    ) -> NextStepResult:
        """Plan the next step in iterative execution.

        Builds a prompt from the goal, current page context, and
        history of previous steps, then asks the LLM for the next
        single action or a goal-reached signal.

        Args:
            original_goal: The original user goal.
            page_context: Current browser page snapshot.
            history: Previous iteration records (may be empty).

        Returns:
            A ``NextStepResult`` with either the next step or
            ``goal_reached=True``.

        Raises:
            PlanningError: When the LLM call fails or the response
                cannot be parsed into a valid result.
        """
        history_summary = self._format_history(history)

        prompt = _PLAN_NEXT_STEP_TEMPLATE.format(
            original_goal=original_goal,
            url=page_context.url,
            title=page_context.title,
            dom_summary=page_context.dom_summary,
            visible_elements=_compact_elements_json(
                page_context.visible_elements,
            ),
            content_snippets=_compact_elements_json(
                page_context.content_snippets,
                max_chars=3000,
            ),
            history=history_summary,
        )

        logger.debug("Sending plan_next_step request to LLM")

        try:
            response: LLMResponse = await self.llm_router.route(
                LLMRequest(prompt=prompt),
            )
        except Exception as exc:
            raise PlanningError(
                f"LLM request failed during plan_next_step: "
                f"{exc}"
            ) from exc

        return self._parse_next_step_response(response.content)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _expand_intents(
        intents: list[ParsedIntent],
    ) -> list[ParsedIntent]:
        """Flatten composite intents into a single list.

        Args:
            intents: Top-level intents, possibly containing composites.

        Returns:
            Flat list with composite intents replaced by their
            sub-intents.
        """
        expanded: list[ParsedIntent] = []
        for intent in intents:
            if (
                intent.intent_type is IntentType.COMPOSITE
                and intent.sub_intents
            ):
                expanded.extend(intent.sub_intents)
            else:
                expanded.append(intent)
        return expanded

    @staticmethod
    def _intent_to_dict(intent: ParsedIntent) -> dict:
        """Serialise a ``ParsedIntent`` to a plain dict.

        Args:
            intent: The intent to serialise.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "intent_type": intent.intent_type.value,
            "target_description": intent.target_description,
            "parameters": intent.parameters,
            "confidence": intent.confidence,
        }

    @staticmethod
    def _format_history(
        history: list[IterationRecord],
    ) -> str:
        """Summarise iteration history for inclusion in a prompt.

        Keeps the most recent 5 iterations to limit prompt size.

        Args:
            history: List of previous iteration records.

        Returns:
            Human-readable summary string. Returns ``"(none)"``
            when history is empty.
        """
        if not history:
            return "(none)"

        recent = history[-5:]
        lines: list[str] = []
        for idx, record in enumerate(recent, start=1):
            status = (
                "OK" if record.result.success else "FAILED"
            )
            error_part = ""
            if record.result.error_message:
                error_part = (
                    f" — error: {record.result.error_message}"
                )
            lines.append(
                f"{idx}. {record.step.action_type}"
                f"({record.step.selector_value})"
                f" → {status}{error_part}"
            )
        return "\n".join(lines)

    def _parse_next_step_response(
        self, content: str,
    ) -> NextStepResult:
        """Parse LLM JSON into a ``NextStepResult``.

        Args:
            content: Raw JSON string from the LLM.

        Returns:
            A validated ``NextStepResult``.

        Raises:
            PlanningError: On invalid JSON or missing/invalid
                fields.
        """
        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError as exc:
            raise PlanningError(
                "Failed to parse plan_next_step response "
                f"as JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise PlanningError(
                "plan_next_step response must be a "
                "JSON object."
            )

        if "goal_reached" not in data:
            raise PlanningError(
                "plan_next_step response missing "
                "'goal_reached' field."
            )

        goal_reached = bool(data["goal_reached"])
        reasoning = str(data.get("reasoning", ""))

        if goal_reached:
            return NextStepResult(
                step=None,
                goal_reached=True,
                reasoning=reasoning,
            )

        raw_step = data.get("step")
        if not isinstance(raw_step, dict):
            raise PlanningError(
                "plan_next_step response must contain a "
                "'step' object when goal_reached is false."
            )

        step = self._build_step(raw_step)
        return NextStepResult(
            step=step,
            goal_reached=False,
            reasoning=reasoning,
        )

    def _parse_plan_response(
        self, content: str,
    ) -> ExecutionPlan:
        """Parse the LLM JSON response into an ``ExecutionPlan``.

        Args:
            content: Raw JSON string from the LLM.

        Returns:
            A validated ``ExecutionPlan``.

        Raises:
            PlanningError: On invalid JSON or missing/invalid fields.
        """
        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError as exc:
            raise PlanningError(
                f"Failed to parse plan response as JSON: {exc}"
            ) from exc

        raw_steps = data.get("steps")
        if (
            not isinstance(raw_steps, list)
            or len(raw_steps) == 0
        ):
            raise PlanningError(
                "Plan response must contain a non-empty "
                "'steps' list."
            )

        steps = [self._build_step(raw) for raw in raw_steps]

        return ExecutionPlan(
            steps=steps,
            description=data.get("description", ""),
            estimated_duration_ms=max(
                0, int(data.get("estimated_duration_ms", 0)),
            ),
        )

    def _parse_steps(self, content: str) -> list[ActionStep]:
        """Parse LLM JSON into a list of ``ActionStep`` objects.

        Args:
            content: Raw JSON string from the LLM.

        Returns:
            A non-empty list of action steps.

        Raises:
            PlanningError: On invalid JSON or empty steps.
        """
        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError as exc:
            raise PlanningError(
                f"Failed to parse replan response as JSON: "
                f"{exc}"
            ) from exc

        raw_steps = data.get("steps")
        if (
            not isinstance(raw_steps, list)
            or len(raw_steps) == 0
        ):
            raise PlanningError(
                "Replan response must contain a non-empty "
                "'steps' list."
            )

        return [self._build_step(raw) for raw in raw_steps]

    @staticmethod
    def _build_step(raw: dict) -> ActionStep:
        """Build a validated ``ActionStep`` from a raw dict.

        Args:
            raw: Dictionary with step fields from the LLM.

        Returns:
            A validated ``ActionStep``.

        Raises:
            PlanningError: On invalid or missing fields.
        """
        action_type = raw.get("action_type", "")
        if action_type not in _VALID_ACTION_TYPES:
            raise PlanningError(
                f"Invalid action_type: '{action_type}'. "
                f"Must be one of "
                f"{sorted(_VALID_ACTION_TYPES)}."
            )

        strategy = raw.get("selector_strategy", "")
        if strategy not in _VALID_SELECTOR_STRATEGIES:
            raise PlanningError(
                f"Invalid selector_strategy: '{strategy}'. "
                f"Must be one of "
                f"{sorted(_VALID_SELECTOR_STRATEGIES)}."
            )

        selector_value = raw.get("selector_value", "")
        if not selector_value:
            raise PlanningError(
                "selector_value must not be empty."
            )

        timeout_ms = int(
            raw.get("timeout_ms", _DEFAULT_TIMEOUT_MS),
        )
        timeout_ms = max(
            _MIN_TIMEOUT_MS, min(_MAX_TIMEOUT_MS, timeout_ms),
        )

        retry_count = int(
            raw.get("retry_count", _DEFAULT_RETRY_COUNT),
        )
        retry_count = max(0, min(10, retry_count))

        return ActionStep(
            action_type=action_type,
            selector_strategy=strategy,
            selector_value=selector_value,
            input_value=raw.get("input_value"),
            wait_condition=raw.get("wait_condition"),
            timeout_ms=timeout_ms,
            retry_count=retry_count,
        )


__all__ = ["TaskPlanner"]
