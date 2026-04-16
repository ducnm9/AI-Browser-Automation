"""Unit tests for TaskPlanner.

Tests cover plan(), replan(), intent expansion, step validation,
and error handling against Requirements 2.1, 2.2, 2.3.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_browser_automation.browser.base import PageContext
from ai_browser_automation.core.task_planner import TaskPlanner
from ai_browser_automation.exceptions.errors import PlanningError
from ai_browser_automation.llm.base import LLMResponse
from ai_browser_automation.models.actions import ActionStep
from ai_browser_automation.models.config import LLMProvider
from ai_browser_automation.models.intents import (
    IntentType,
    ParsedIntent,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def mock_router() -> MagicMock:
    """LLMRouter mock with an async route method."""
    router = MagicMock()
    router.route = AsyncMock()
    return router


@pytest.fixture()
def planner(mock_router: MagicMock) -> TaskPlanner:
    """TaskPlanner wired with mock router."""
    return TaskPlanner(mock_router)


@pytest.fixture()
def page_context() -> PageContext:
    """Minimal page context for testing."""
    return PageContext(
        url="https://example.com",
        title="Example",
        dom_summary="<html><body>...</body></html>",
        visible_elements=[
            {"tag": "input", "id": "search", "type": "text"},
            {"tag": "button", "text": "Submit"},
        ],
    )


def _llm_response(content: str) -> LLMResponse:
    """Helper to build a fake LLMResponse."""
    return LLMResponse(
        content=content,
        provider_used=LLMProvider.LM_STUDIO,
        tokens_used=10,
        latency_ms=50.0,
    )


def _valid_plan_json(
    action_type: str = "click",
    strategy: str = "css",
    selector: str = "#btn",
) -> str:
    """Build a valid plan JSON response string."""
    return json.dumps({
        "steps": [{
            "action_type": action_type,
            "selector_strategy": strategy,
            "selector_value": selector,
            "input_value": None,
            "wait_condition": None,
            "timeout_ms": 10000,
            "retry_count": 3,
        }],
        "description": "Click the button",
        "estimated_duration_ms": 5000,
    })


# ── plan: basic success (Req 2.1) ───────────────────────────────────


class TestPlanBasicSuccess:
    """Requirement 2.1: plan returns non-empty steps."""

    @pytest.mark.asyncio()
    async def test_plan_returns_execution_plan(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            _valid_plan_json(),
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="Submit button",
                confidence=0.9,
            ),
        ]

        plan = await planner.plan(intents, page_context)

        assert len(plan.steps) >= 1
        assert plan.steps[0].action_type == "click"
        assert plan.steps[0].selector_strategy == "css"
        assert plan.steps[0].selector_value == "#btn"
        assert plan.description == "Click the button"
        assert plan.estimated_duration_ms == 5000

    @pytest.mark.asyncio()
    async def test_plan_step_has_valid_timeout(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            _valid_plan_json(),
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.NAVIGATE,
                target_description="Google",
                confidence=0.95,
            ),
        ]

        plan = await planner.plan(intents, page_context)

        for step in plan.steps:
            assert 1000 <= step.timeout_ms <= 60000

    @pytest.mark.asyncio()
    async def test_plan_multi_step(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        response_json = json.dumps({
            "steps": [
                {
                    "action_type": "navigate",
                    "selector_strategy": "css",
                    "selector_value": "body",
                    "input_value": "https://google.com",
                    "timeout_ms": 15000,
                    "retry_count": 2,
                },
                {
                    "action_type": "type",
                    "selector_strategy": "css",
                    "selector_value": "#search",
                    "input_value": "hello",
                    "timeout_ms": 10000,
                    "retry_count": 3,
                },
            ],
            "description": "Navigate and search",
            "estimated_duration_ms": 8000,
        })
        mock_router.route.return_value = _llm_response(
            response_json,
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.NAVIGATE,
                target_description="Google",
                confidence=0.9,
            ),
        ]

        plan = await planner.plan(intents, page_context)

        assert len(plan.steps) == 2
        assert plan.steps[0].action_type == "navigate"
        assert plan.steps[1].action_type == "type"
        assert plan.steps[1].input_value == "hello"


# ── plan: composite intent expansion (Req 2.1) ──────────────────────


class TestPlanCompositeExpansion:
    """Composite intents are expanded before sending to LLM."""

    @pytest.mark.asyncio()
    async def test_composite_sub_intents_expanded(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            _valid_plan_json(),
        )
        composite = ParsedIntent(
            intent_type=IntentType.COMPOSITE,
            target_description="Login and read",
            confidence=0.9,
            sub_intents=[
                ParsedIntent(
                    intent_type=IntentType.LOGIN,
                    target_description="Gmail",
                    confidence=0.9,
                ),
                ParsedIntent(
                    intent_type=IntentType.EXTRACT_DATA,
                    target_description="latest email",
                    confidence=0.85,
                ),
            ],
        )

        await planner.plan([composite], page_context)

        call_args = mock_router.route.call_args
        request = call_args[0][0]
        assert "login" in request.prompt
        assert "extract_data" in request.prompt


# ── plan: selector strategy (Req 2.3) ───────────────────────────────


class TestPlanSelectorStrategy:
    """Requirement 2.3: valid selector strategies."""

    @pytest.mark.asyncio()
    @pytest.mark.parametrize(
        "strategy",
        ["css", "xpath", "text", "ai_vision"],
    )
    async def test_all_valid_strategies_accepted(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
        strategy: str,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            _valid_plan_json(strategy=strategy),
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="button",
                confidence=0.9,
            ),
        ]

        plan = await planner.plan(intents, page_context)

        assert plan.steps[0].selector_strategy == strategy


# ── plan: timeout clamping ───────────────────────────────────────────


class TestPlanTimeoutClamping:
    """Timeout values are clamped to [1000, 60000]."""

    @pytest.mark.asyncio()
    async def test_timeout_below_min_clamped(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        response_json = json.dumps({
            "steps": [{
                "action_type": "click",
                "selector_strategy": "css",
                "selector_value": "#btn",
                "timeout_ms": 100,
                "retry_count": 1,
            }],
            "description": "test",
            "estimated_duration_ms": 100,
        })
        mock_router.route.return_value = _llm_response(
            response_json,
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        plan = await planner.plan(intents, page_context)

        assert plan.steps[0].timeout_ms == 1000

    @pytest.mark.asyncio()
    async def test_timeout_above_max_clamped(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        response_json = json.dumps({
            "steps": [{
                "action_type": "click",
                "selector_strategy": "css",
                "selector_value": "#btn",
                "timeout_ms": 999999,
                "retry_count": 1,
            }],
            "description": "test",
            "estimated_duration_ms": 100,
        })
        mock_router.route.return_value = _llm_response(
            response_json,
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        plan = await planner.plan(intents, page_context)

        assert plan.steps[0].timeout_ms == 60000


# ── plan: error handling ─────────────────────────────────────────────


class TestPlanErrorHandling:
    """LLM failures and bad JSON wrapped in PlanningError."""

    @pytest.mark.asyncio()
    async def test_llm_failure_raises_planning_error(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.side_effect = RuntimeError("boom")
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        with pytest.raises(PlanningError, match="planning"):
            await planner.plan(intents, page_context)

    @pytest.mark.asyncio()
    async def test_invalid_json_raises(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            "not json",
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        with pytest.raises(PlanningError, match="JSON"):
            await planner.plan(intents, page_context)

    @pytest.mark.asyncio()
    async def test_empty_steps_raises(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({"steps": []}),
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        with pytest.raises(PlanningError, match="non-empty"):
            await planner.plan(intents, page_context)

    @pytest.mark.asyncio()
    async def test_invalid_action_type_raises(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            _valid_plan_json(action_type="fly"),
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        with pytest.raises(PlanningError, match="action_type"):
            await planner.plan(intents, page_context)

    @pytest.mark.asyncio()
    async def test_invalid_selector_strategy_raises(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            _valid_plan_json(strategy="magic"),
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        with pytest.raises(
            PlanningError, match="selector_strategy",
        ):
            await planner.plan(intents, page_context)

    @pytest.mark.asyncio()
    async def test_empty_selector_value_raises(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            _valid_plan_json(selector=""),
        )
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="btn",
                confidence=0.9,
            ),
        ]

        with pytest.raises(
            PlanningError, match="selector_value",
        ):
            await planner.plan(intents, page_context)


# ── replan (Req 2.2) ────────────────────────────────────────────────


class TestReplan:
    """Requirement 2.2: replan on step failure."""

    @pytest.mark.asyncio()
    async def test_replan_returns_alternative_steps(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "steps": [{
                    "action_type": "click",
                    "selector_strategy": "xpath",
                    "selector_value": "//button[@id='submit']",
                    "timeout_ms": 10000,
                    "retry_count": 2,
                }],
            }),
        )
        failed = ActionStep(
            action_type="click",
            selector_strategy="css",
            selector_value="#submit",
        )

        result = await planner.replan(
            failed, "Element not found", b"screenshot",
        )

        assert len(result) >= 1
        assert result[0].selector_strategy == "xpath"

    @pytest.mark.asyncio()
    async def test_replan_llm_failure_raises(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.side_effect = RuntimeError("down")
        failed = ActionStep(
            action_type="click",
            selector_strategy="css",
            selector_value="#btn",
        )

        with pytest.raises(PlanningError, match="replanning"):
            await planner.replan(
                failed, "error", b"screenshot",
            )

    @pytest.mark.asyncio()
    async def test_replan_invalid_json_raises(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
    ) -> None:
        mock_router.route.return_value = _llm_response(
            "bad json",
        )
        failed = ActionStep(
            action_type="click",
            selector_strategy="css",
            selector_value="#btn",
        )

        with pytest.raises(PlanningError, match="JSON"):
            await planner.replan(
                failed, "error", b"screenshot",
            )


# ── plan_next_step (Req 2.1, 2.2, 2.3, 2.4) ────────────────────────


class TestPlanNextStep:
    """Requirements 2.1–2.4: plan_next_step returns NextStepResult."""

    @pytest.mark.asyncio()
    async def test_goal_reached_true_returns_step_none(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        """Req 2.2: goal_reached=True → step is None."""
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "goal_reached": True,
                "reasoning": "All done",
                "step": None,
            }),
        )

        result = await planner.plan_next_step(
            "Buy shoes", page_context, [],
        )

        assert result.goal_reached is True
        assert result.step is None
        assert result.reasoning == "All done"

    @pytest.mark.asyncio()
    async def test_goal_reached_false_returns_valid_step(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        """Req 2.1, 2.3: goal_reached=False → valid ActionStep."""
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "goal_reached": False,
                "reasoning": "Need to navigate first",
                "step": {
                    "action_type": "navigate",
                    "selector_strategy": "css",
                    "selector_value": "body",
                    "input_value": "https://example.com",
                    "wait_condition": None,
                    "timeout_ms": 15000,
                    "retry_count": 2,
                },
            }),
        )

        result = await planner.plan_next_step(
            "Open example.com", page_context, [],
        )

        assert result.goal_reached is False
        assert result.step is not None
        assert result.step.action_type == "navigate"
        assert result.step.selector_strategy == "css"
        assert result.step.selector_value == "body"
        assert result.step.input_value == "https://example.com"
        assert result.step.timeout_ms == 15000
        assert result.step.retry_count == 2
        assert result.reasoning == "Need to navigate first"

    @pytest.mark.asyncio()
    async def test_invalid_json_raises_planning_error(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        """Req 2.4: invalid JSON → PlanningError."""
        mock_router.route.return_value = _llm_response(
            "this is not json at all",
        )

        with pytest.raises(PlanningError, match="JSON"):
            await planner.plan_next_step(
                "Do something", page_context, [],
            )

    @pytest.mark.asyncio()
    async def test_missing_goal_reached_raises_planning_error(
        self,
        planner: TaskPlanner,
        mock_router: MagicMock,
        page_context: PageContext,
    ) -> None:
        """Req 2.4: missing goal_reached field → PlanningError."""
        mock_router.route.return_value = _llm_response(
            json.dumps({
                "reasoning": "oops",
                "step": None,
            }),
        )

        with pytest.raises(
            PlanningError, match="goal_reached",
        ):
            await planner.plan_next_step(
                "Do something", page_context, [],
            )

    def test_format_history_empty_returns_none_string(
        self,
        planner: TaskPlanner,
    ) -> None:
        """_format_history with empty list returns '(none)'."""
        result = planner._format_history([])
        assert result == "(none)"

    def test_format_history_with_records(
        self,
        planner: TaskPlanner,
        page_context: PageContext,
    ) -> None:
        """_format_history with records returns formatted summary."""
        from ai_browser_automation.models.actions import (
            ActionResult,
            ActionStep,
            IterationRecord,
        )

        step_ok = ActionStep(
            action_type="navigate",
            selector_strategy="css",
            selector_value="body",
            input_value="https://example.com",
        )
        result_ok = ActionResult(success=True, step=step_ok)

        step_fail = ActionStep(
            action_type="click",
            selector_strategy="css",
            selector_value="#btn",
        )
        result_fail = ActionResult(
            success=False,
            step=step_fail,
            error_message="Element not found",
        )

        history = [
            IterationRecord(
                step=step_ok,
                result=result_ok,
                page_context_before=page_context,
            ),
            IterationRecord(
                step=step_fail,
                result=result_fail,
                page_context_before=page_context,
            ),
        ]

        formatted = planner._format_history(history)

        assert "navigate" in formatted
        assert "OK" in formatted
        assert "click" in formatted
        assert "FAILED" in formatted
        assert "Element not found" in formatted
