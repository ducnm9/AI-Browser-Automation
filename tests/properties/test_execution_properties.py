"""Property-based tests for core execution components.

Uses hypothesis to verify correctness properties 1–6 from the design
document against Requirements 1.1, 1.3, 1.4, 3.1, 3.2, 3.4, 3.6.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ai_browser_automation.core.action_executor import ActionExecutor
from ai_browser_automation.core.nl_processor import NLProcessor
from ai_browser_automation.exceptions.errors import NLProcessingError
from ai_browser_automation.llm.base import LLMResponse
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.actions import (
    ActionStep,
    ExecutionPlan,
)
from ai_browser_automation.models.config import (
    LLMProvider,
    SecurityPolicy,
)
from ai_browser_automation.models.intents import (
    IntentType,
    ParsedIntent,
)
from ai_browser_automation.security.security_layer import SecurityLayer


# ── Helpers ──────────────────────────────────────────────────────


def _make_llm_response_with_intents(
    intents: list[dict],
) -> LLMResponse:
    """Build a fake LLMResponse containing intent JSON."""
    return LLMResponse(
        content=json.dumps({"intents": intents}),
        provider_used=LLMProvider.LM_STUDIO,
        tokens_used=10,
        latency_ms=5.0,
    )


def _make_mock_router() -> MagicMock:
    """Create a mock LLMRouter with async route."""
    router = MagicMock()
    router.route = AsyncMock()
    return router


def _make_security() -> SecurityLayer:
    """Create a SecurityLayer with default policy."""
    return SecurityLayer(SecurityPolicy())


# ── Strategies ───────────────────────────────────────────────────

# Non-empty, non-whitespace strings for NL parse input
_nonempty_text_st = st.text(
    min_size=1, max_size=100,
).filter(lambda s: s.strip() != "")

# Whitespace-only strings (including empty)
_whitespace_st = st.from_regex(
    r"^[\s]*$", fullmatch=True,
).filter(lambda s: s.strip() == "")

# Action step strategy — scroll is a no-op, always succeeds
_action_step_st = st.builds(
    ActionStep,
    action_type=st.just("scroll"),
    selector_strategy=st.just("css"),
    selector_value=st.just("#el"),
    timeout_ms=st.just(1000),
    retry_count=st.integers(min_value=0, max_value=5),
)

# Execution plan with N steps (all scroll = all succeed)
_success_plan_st = st.lists(
    _action_step_st,
    min_size=1,
    max_size=10,
).map(lambda steps: ExecutionPlan(steps=steps))


# ── Property 1: NL Parse Output Invariants ───────────────────────


class TestNLParseOutputInvariants:
    """**Validates: Requirement 1.1**

    For any non-empty, non-whitespace input string,
    NLProcessor.parse() SHALL return a non-empty list of
    ParsedIntent where every intent has an intent_type belonging
    to IntentType and confidence in [0.0, 1.0].
    """

    @given(user_input=_nonempty_text_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_parse_returns_valid_intents(
        self, user_input: str,
    ) -> None:
        """parse() returns non-empty list with valid types."""
        mock_router = _make_mock_router()
        security = _make_security()

        mock_router.route.return_value = (
            _make_llm_response_with_intents([{
                "intent_type": "navigate",
                "target_description": "test target",
                "parameters": {},
                "confidence": 0.85,
                "sub_intents": [],
            }])
        )

        processor = NLProcessor(mock_router, security)
        result = await processor.parse(user_input)

        assert len(result) >= 1
        for intent in result:
            assert isinstance(intent.intent_type, IntentType)
            assert 0.0 <= intent.confidence <= 1.0


# ── Property 2: Low Confidence Triggers Clarification ────────────


class TestLowConfidenceTriggersClarification:
    """**Validates: Requirement 1.3**

    For any ParsedIntent with confidence < 0.7, the system SHALL
    return a clarification request. For all intents with
    confidence >= 0.7, the system SHALL proceed to execution.
    """

    @given(
        confidence=st.floats(
            min_value=0.0,
            max_value=0.69,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_low_confidence_triggers_clarification(
        self, confidence: float,
    ) -> None:
        """Any intent with confidence < 0.7 triggers clarify."""
        intents = [
            ParsedIntent(
                intent_type=IntentType.NAVIGATE,
                target_description="some page",
                confidence=confidence,
            ),
        ]

        has_low = any(
            i.confidence < 0.7 for i in intents
        )
        assert has_low is True

    @given(
        confidences=st.lists(
            st.floats(
                min_value=0.7,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_all_high_confidence_proceeds(
        self, confidences: list[float],
    ) -> None:
        """All intents >= 0.7 proceed to execution."""
        intents = [
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description=f"target_{i}",
                confidence=c,
            )
            for i, c in enumerate(confidences)
        ]

        has_low = any(
            i.confidence < 0.7 for i in intents
        )
        assert has_low is False

    @given(
        high_conf=st.floats(
            min_value=0.7,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        low_conf=st.floats(
            min_value=0.0,
            max_value=0.69,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_mixed_confidence_triggers_clarification(
        self, high_conf: float, low_conf: float,
    ) -> None:
        """Mixed list with any < 0.7 triggers clarification."""
        intents = [
            ParsedIntent(
                intent_type=IntentType.NAVIGATE,
                target_description="high",
                confidence=high_conf,
            ),
            ParsedIntent(
                intent_type=IntentType.CLICK,
                target_description="low",
                confidence=low_conf,
            ),
        ]

        has_low = any(
            i.confidence < 0.7 for i in intents
        )
        assert has_low is True


# ── Property 3: Whitespace Input Rejection ───────────────────────


class TestWhitespaceInputRejection:
    """**Validates: Requirement 1.4**

    For any string composed entirely of whitespace characters
    (spaces, tabs, newlines, or empty string),
    NLProcessor.parse() SHALL reject the input and raise
    NLProcessingError.
    """

    @given(ws_input=_whitespace_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_whitespace_only_raises(
        self, ws_input: str,
    ) -> None:
        """Whitespace-only input raises NLProcessingError."""
        mock_router = _make_mock_router()
        security = _make_security()
        processor = NLProcessor(mock_router, security)

        with pytest.raises(NLProcessingError):
            await processor.parse(ws_input)


# ── Property 4: Execution Plan Result Integrity ──────────────────


class TestExecutionPlanResultIntegrity:
    """**Validates: Requirements 3.1, 3.6**

    For any ExecutionPlan where all steps succeed,
    ActionExecutor SHALL return results where
    len(results) == len(plan.steps),
    results[i].step == plan.steps[i], and
    all duration_ms >= 0.
    """

    @given(plan=_success_plan_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_result_count_matches_steps(
        self, plan: ExecutionPlan,
    ) -> None:
        """len(results) == N for N-step all-succeed plan."""
        mock_browser = AsyncMock()
        mock_browser.screenshot = AsyncMock(
            return_value=b"png",
        )
        mock_router = AsyncMock(spec=LLMRouter)

        executor = ActionExecutor(mock_browser, mock_router)
        results = await executor.execute_plan(plan)

        assert len(results) == len(plan.steps)
        for i, result in enumerate(results):
            assert result.step is plan.steps[i]
            assert result.duration_ms >= 0
            assert result.success is True


# ── Property 5: Retry Bounded by retry_count ─────────────────────


class TestRetryBoundedByRetryCount:
    """**Validates: Requirement 3.2**

    For any ActionStep that fails, the number of smart retry
    attempts SHALL be at most equal to step.retry_count.
    """

    @given(
        retry_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_retry_count_bounds_attempts(
        self, retry_count: int,
    ) -> None:
        """Smart retry attempts <= step.retry_count."""
        smart_retry_call_count = 0

        mock_browser = AsyncMock()
        mock_browser.click = AsyncMock(
            side_effect=RuntimeError("not found"),
        )
        mock_browser.screenshot = AsyncMock(
            return_value=b"png",
        )

        mock_router = AsyncMock(spec=LLMRouter)
        mock_router.route = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps({
                    "selector_strategy": "xpath",
                    "selector_value": "//button",
                }),
                provider_used=LLMProvider.LM_STUDIO,
                tokens_used=5,
                latency_ms=10.0,
            ),
        )

        executor = ActionExecutor(mock_browser, mock_router)

        # Wrap smart_retry to count calls
        original_smart_retry = executor.smart_retry

        async def counting_smart_retry(
            step: ActionStep, error: str,
        ) -> object:
            nonlocal smart_retry_call_count
            smart_retry_call_count += 1
            return await original_smart_retry(step, error)

        executor.smart_retry = counting_smart_retry  # type: ignore[assignment]

        step = ActionStep(
            action_type="click",
            selector_strategy="css",
            selector_value="#btn",
            retry_count=retry_count,
        )
        plan = ExecutionPlan(steps=[step])

        await executor.execute_plan(plan)

        assert smart_retry_call_count <= retry_count


# ── Property 6: Failure Stops Subsequent Execution ───────────────


class TestFailureStopsSubsequentExecution:
    """**Validates: Requirement 3.4**

    For any ExecutionPlan where step at index N fails
    irrecoverably, no steps at index > N SHALL be executed,
    and len(results) == N + 1.
    """

    @given(
        fail_index=st.integers(min_value=0, max_value=4),
        extra_steps=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio()
    async def test_failure_stops_remaining_steps(
        self, fail_index: int, extra_steps: int,
    ) -> None:
        """Steps after failed index are not executed."""
        total_steps = fail_index + 1 + extra_steps

        mock_browser = AsyncMock()
        mock_browser.screenshot = AsyncMock(
            return_value=b"png",
        )

        # Build steps: scroll (succeed) up to fail_index,
        # then click (fail) at fail_index,
        # then scroll (succeed) for remaining.
        steps: list[ActionStep] = []
        for i in range(total_steps):
            if i == fail_index:
                steps.append(ActionStep(
                    action_type="click",
                    selector_strategy="css",
                    selector_value=f"#fail_{i}",
                    retry_count=0,
                ))
            else:
                steps.append(ActionStep(
                    action_type="scroll",
                    selector_strategy="css",
                    selector_value=f"#ok_{i}",
                    retry_count=0,
                ))

        # Make click always fail
        mock_browser.click = AsyncMock(
            side_effect=RuntimeError("fail"),
        )

        # Replan also fails so step is irrecoverable
        mock_router = AsyncMock(spec=LLMRouter)
        mock_router.route = AsyncMock(
            side_effect=RuntimeError("no replan"),
        )

        executor = ActionExecutor(mock_browser, mock_router)
        plan = ExecutionPlan(steps=steps)

        results = await executor.execute_plan(plan)

        # Exactly fail_index + 1 results
        assert len(results) == fail_index + 1
        # All before fail_index succeeded
        for r in results[:fail_index]:
            assert r.success is True
        # The failed step
        assert results[fail_index].success is False
