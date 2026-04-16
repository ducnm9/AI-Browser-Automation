"""Action step, execution plan, and action result data models.

These models represent the planning and execution layer: an ``ExecutionPlan``
is a sequence of ``ActionStep`` objects, and each step produces an
``ActionResult`` after execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ai_browser_automation.browser.base import PageContext


@dataclass
class ActionStep:
    """A single browser action to be executed.

    Args:
        action_type: Kind of action (e.g. "click", "type", "navigate").
        selector_strategy: How to locate the element ("css", "xpath",
            "text", "ai_vision").
        selector_value: The selector expression or description.
        input_value: Text to type, URL to navigate to, etc.
        wait_condition: Optional JS expression or event to wait for.
        timeout_ms: Maximum time in milliseconds to wait for the action.
        retry_count: Number of smart-retry attempts on failure.
    """

    action_type: str
    selector_strategy: str
    selector_value: str
    input_value: Optional[str] = None
    wait_condition: Optional[str] = None
    timeout_ms: int = 10000
    retry_count: int = 3


@dataclass
class ExecutionPlan:
    """An ordered sequence of action steps produced by the Task Planner.

    Args:
        steps: Ordered list of actions to execute.
        description: Human-readable summary of the plan.
        estimated_duration_ms: Estimated total execution time.
        requires_auth: Whether the plan involves authentication.
        sensitive_data_involved: Whether sensitive data is part of the plan.
    """

    steps: list[ActionStep] = field(default_factory=list)
    description: str = ""
    estimated_duration_ms: int = 0
    requires_auth: bool = False
    sensitive_data_involved: bool = False


@dataclass
class ActionResult:
    """Outcome of executing a single ``ActionStep``.

    Args:
        success: Whether the step completed successfully.
        step: The action step that was executed.
        extracted_data: Data extracted from the page (for "extract" actions).
        screenshot: Screenshot bytes captured after execution.
        error_message: Description of the failure when ``success`` is False.
        duration_ms: Wall-clock time spent executing the step.
    """

    success: bool
    step: ActionStep
    extracted_data: Optional[str] = None
    screenshot: Optional[bytes] = None
    error_message: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class IterationRecord:
    """Result of one iteration in the Observe-Plan-Act loop.

    Args:
        step: The action step that was executed.
        result: The execution result.
        page_context_before: Page context before executing the step.
    """

    step: ActionStep
    result: ActionResult
    page_context_before: PageContext


@dataclass
class NextStepResult:
    """Result from plan_next_step — next step or goal_reached signal.

    Args:
        step: Next action step (None when goal_reached is True).
        goal_reached: True when the LLM confirms the goal is complete.
        reasoning: Brief explanation from the LLM about the decision.
    """

    step: Optional[ActionStep] = None
    goal_reached: bool = False
    reasoning: str = ""


__all__ = [
    "ActionStep",
    "ExecutionPlan",
    "ActionResult",
    "IterationRecord",
    "NextStepResult",
]
