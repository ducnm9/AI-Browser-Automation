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
from ai_browser_automation.models.actions import ActionStep, ExecutionPlan
from ai_browser_automation.models.intents import IntentType, ParsedIntent

logger = logging.getLogger(__name__)

_VALID_ACTION_TYPES = {
    "navigate", "click", "type", "type_text", "wait",
    "extract", "extract_data", "scroll", "screenshot", "login",
}

_VALID_SELECTOR_STRATEGIES = {"css", "xpath", "text", "ai_vision"}

_MIN_TIMEOUT_MS = 1000
_MAX_TIMEOUT_MS = 60000
_DEFAULT_TIMEOUT_MS = 10000
_DEFAULT_RETRY_COUNT = 3

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
            visible_elements=json.dumps(
                page_context.visible_elements, indent=2,
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
