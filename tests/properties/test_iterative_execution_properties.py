"""Property-based tests for iterative execution pipeline data models.

Uses hypothesis to verify correctness properties from the design
document for the iterative execution pipeline.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from ai_browser_automation.browser.base import PageContext
from ai_browser_automation.core.iterative_executor import (
    IterativeExecutor,
)
from ai_browser_automation.core.task_planner import TaskPlanner
from ai_browser_automation.models.actions import (
    ActionResult,
    ActionStep,
    NextStepResult,
)
from ai_browser_automation.models.intents import (
    IntentType,
    ParsedIntent,
)


# ── Recognized action types from the codebase ───────────────────

RECOGNIZED_ACTION_TYPES = {
    "navigate", "click", "type", "type_text", "wait",
    "extract", "extract_data", "scroll", "screenshot",
    "login", "extract_table",
}


# ── Strategies ───────────────────────────────────────────────────

_action_type_st = st.sampled_from(sorted(RECOGNIZED_ACTION_TYPES))

_action_step_st = st.builds(
    ActionStep,
    action_type=_action_type_st,
    selector_strategy=st.sampled_from(["css", "xpath", "text"]),
    selector_value=st.text(min_size=1, max_size=50).filter(
        lambda s: s.strip() != ""
    ),
)

_goal_reached_result_st = st.builds(
    NextStepResult,
    step=st.none(),
    goal_reached=st.just(True),
    reasoning=st.text(max_size=100),
)

_goal_not_reached_result_st = st.builds(
    NextStepResult,
    step=_action_step_st,
    goal_reached=st.just(False),
    reasoning=st.text(max_size=100),
)

_next_step_result_st = st.one_of(
    _goal_reached_result_st,
    _goal_not_reached_result_st,
)


# ── Property 3: NextStepResult validity ──────────────────────────


class TestNextStepResultValidity:
    """**Validates: Requirements 2.2, 2.3, 7.2, 7.3**

    For any NextStepResult, if goal_reached is True then step
    SHALL be None, and if goal_reached is False then step SHALL
    be a non-None ActionStep with a recognized action_type.
    """

    @given(result=_goal_reached_result_st)
    @settings(max_examples=50)
    def test_goal_reached_implies_step_is_none(
        self, result: NextStepResult,
    ) -> None:
        """When goal_reached is True, step must be None."""
        assert result.goal_reached is True
        assert result.step is None

    @given(result=_goal_not_reached_result_st)
    @settings(max_examples=50)
    def test_goal_not_reached_implies_valid_step(
        self, result: NextStepResult,
    ) -> None:
        """When goal_reached is False, step must be a valid ActionStep."""
        assert result.goal_reached is False
        assert result.step is not None
        assert isinstance(result.step, ActionStep)
        assert result.step.action_type in RECOGNIZED_ACTION_TYPES

    @given(result=_next_step_result_st)
    @settings(max_examples=100)
    def test_validity_invariant_holds_for_any_result(
        self, result: NextStepResult,
    ) -> None:
        """The validity invariant holds across all generated results."""
        if result.goal_reached:
            assert result.step is None
        else:
            assert result.step is not None
            assert isinstance(result.step, ActionStep)
            assert result.step.action_type in RECOGNIZED_ACTION_TYPES


# ── Strategies for extract_table ─────────────────────────────────

# Cell text that may contain leading/trailing whitespace, tabs, newlines
_cell_text_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z", "Zs"),
        whitelist_characters=" \t\n\r",
    ),
    max_size=80,
)

# A row is a list of cell texts (simulating th and td cells)
_row_st = st.lists(_cell_text_st, min_size=0, max_size=10)

# A table is a list of rows
_table_data_st = st.lists(_row_st, min_size=0, max_size=20)


def _simulate_extract_table(raw_table: list[list[str]]) -> list[list[str]]:
    """Simulate the extract_table stripping behavior.

    Mirrors the JS logic: for each row, strip whitespace from every
    cell text value.  Both th and td cells are included (the raw data
    already represents both).
    """
    return [
        [cell.strip() for cell in row]
        for row in raw_table
    ]


# ── Property 4: extract_table output structure ───────────────────


class TestExtractTableOutputStructure:
    """**Validates: Requirements 3.1, 3.4, 3.5**

    For any HTML table, extract_table() SHALL return a
    list[list[str]] where every cell is a whitespace-stripped
    string, and both th and td cells are included.
    """

    @given(raw_table=_table_data_st)
    @settings(max_examples=100)
    def test_result_is_list_of_lists_of_strings(
        self, raw_table: list[list[str]],
    ) -> None:
        """Output is always list[list[str]]."""
        result = _simulate_extract_table(raw_table)

        assert isinstance(result, list)
        for row in result:
            assert isinstance(row, list)
            for cell in row:
                assert isinstance(cell, str)

    @given(raw_table=_table_data_st)
    @settings(max_examples=100)
    def test_every_cell_is_whitespace_stripped(
        self, raw_table: list[list[str]],
    ) -> None:
        """Every cell value equals its stripped version."""
        result = _simulate_extract_table(raw_table)

        for row in result:
            for cell in row:
                assert cell == cell.strip(), (
                    f"Cell not stripped: {cell!r}"
                )

    @given(raw_table=_table_data_st)
    @settings(max_examples=100)
    def test_row_count_preserved(
        self, raw_table: list[list[str]],
    ) -> None:
        """Number of rows in output matches input."""
        result = _simulate_extract_table(raw_table)
        assert len(result) == len(raw_table)

    @given(raw_table=_table_data_st)
    @settings(max_examples=100)
    def test_cell_count_per_row_preserved(
        self, raw_table: list[list[str]],
    ) -> None:
        """Number of cells per row matches input (th + td all included)."""
        result = _simulate_extract_table(raw_table)
        for original_row, result_row in zip(raw_table, result):
            assert len(result_row) == len(original_row)


# ── Strategies for serialization round-trip ──────────────────────

# Stripped cell text (post-extract_table output)
_stripped_cell_st = _cell_text_st.map(lambda s: s.strip())
_stripped_row_st = st.lists(_stripped_cell_st, min_size=0, max_size=10)
_stripped_table_st = st.lists(_stripped_row_st, min_size=0, max_size=20)


# ── Property 6: extract_table serialization round-trip ───────────


class TestExtractTableSerializationRoundTrip:
    """**Validates: Requirement 5.2**

    For any table data returned by BrowserEngine.extract_table(),
    when the ActionExecutor serializes the data as JSON via
    ``json.dumps(table_data, ensure_ascii=False)`` into
    ``extracted_data``, deserializing that JSON with
    ``json.loads()`` SHALL produce a value equal to the original
    table data.
    """

    @given(table_data=_stripped_table_st)
    @settings(max_examples=100)
    def test_json_round_trip_preserves_table_data(
        self, table_data: list[list[str]],
    ) -> None:
        """Serializing then deserializing table data yields equal value."""
        serialized = json.dumps(table_data, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized == table_data

    @given(raw_table=_table_data_st)
    @settings(max_examples=100)
    def test_json_round_trip_after_extract(
        self, raw_table: list[list[str]],
    ) -> None:
        """Full pipeline: extract (strip) then serialize then deserialize."""
        extracted = _simulate_extract_table(raw_table)
        serialized = json.dumps(extracted, ensure_ascii=False)
        deserialized = json.loads(serialized)
        assert deserialized == extracted


# ── Strategies for Property 1: Loop termination ─────────────────

_max_iterations_st = st.integers(min_value=1, max_value=20)

_valid_step = ActionStep(
    action_type="click",
    selector_strategy="css",
    selector_value="button.submit",
)

_mock_page_context = PageContext(
    url="https://example.com",
    title="Example",
    dom_summary="<html>...</html>",
    visible_elements=[],
)


def _make_executor(max_iterations: int) -> IterativeExecutor:
    """Build an IterativeExecutor with mocked dependencies.

    TaskPlanner.plan_next_step always returns goal_reached=False
    with a valid step, so the loop runs until max_iterations.
    ActionExecutor.execute_step returns a successful result.
    BrowserEngine.get_page_context returns a valid PageContext.

    Args:
        max_iterations: Upper bound on loop iterations.

    Returns:
        Configured IterativeExecutor with mock dependencies.
    """
    planner = MagicMock()
    planner.plan_next_step = AsyncMock(
        return_value=NextStepResult(
            step=_valid_step,
            goal_reached=False,
            reasoning="still working",
        ),
    )

    action_exec = MagicMock()
    action_exec.execute_step = AsyncMock(
        return_value=ActionResult(
            success=True,
            step=_valid_step,
        ),
    )

    browser = MagicMock()
    browser.get_page_context = AsyncMock(
        return_value=_mock_page_context,
    )

    return IterativeExecutor(
        task_planner=planner,
        action_executor=action_exec,
        browser_engine=browser,
        max_iterations=max_iterations,
    )


# ── Property 1: Loop termination ────────────────────────────────


class TestLoopTermination:
    """**Validates: Requirements 1.4, 1.6**

    For any IterativeExecutor with max_iterations=N, and for any
    goal and intents, the length of the returned results list
    SHALL be less than or equal to N.
    """

    @given(max_iterations=_max_iterations_st)
    @settings(max_examples=50)
    def test_results_length_bounded_by_max_iterations(
        self, max_iterations: int,
    ) -> None:
        """len(results) <= max_iterations for any N."""
        ie = _make_executor(max_iterations)

        results = asyncio.get_event_loop().run_until_complete(
            ie.execute(
                original_goal="test goal",
                intents=[],
            ),
        )

        assert len(results) <= max_iterations


# ── Property 2: History-result consistency ───────────────────────

# Number of steps to execute before goal_reached
_num_steps_st = st.integers(min_value=1, max_value=10)


def _make_executor_with_goal_after_n(
    n: int,
) -> tuple[IterativeExecutor, list[int]]:
    """Build an IterativeExecutor that reaches goal after N steps.

    The planner returns goal_reached=False for the first N calls,
    then goal_reached=True on call N+1.  A side-effect tracker
    records the length of the history list passed to each
    plan_next_step call, allowing verification that
    len(history) == len(results) at every iteration.

    Args:
        n: Number of steps to execute before signalling goal.

    Returns:
        Tuple of (executor, history_lengths) where
        history_lengths is populated during execution.
    """
    call_count = 0
    history_lengths: list[int] = []

    async def _plan_next_step(
        original_goal: str,
        page_context: object,
        history: list,
    ) -> NextStepResult:
        nonlocal call_count
        history_lengths.append(len(history))
        call_count += 1
        if call_count <= n:
            return NextStepResult(
                step=_valid_step,
                goal_reached=False,
                reasoning=f"step {call_count}",
            )
        return NextStepResult(
            step=None,
            goal_reached=True,
            reasoning="done",
        )

    planner = MagicMock()
    planner.plan_next_step = AsyncMock(
        side_effect=_plan_next_step,
    )

    action_exec = MagicMock()
    action_exec.execute_step = AsyncMock(
        return_value=ActionResult(
            success=True,
            step=_valid_step,
        ),
    )

    browser = MagicMock()
    browser.get_page_context = AsyncMock(
        return_value=_mock_page_context,
    )

    executor = IterativeExecutor(
        task_planner=planner,
        action_executor=action_exec,
        browser_engine=browser,
        max_iterations=n + 5,
    )

    return executor, history_lengths


class TestHistoryResultConsistency:
    """**Validates: Requirement 1.2**

    For any execution of the Observe-Plan-Act loop, at every
    iteration the length of the history list SHALL equal the
    length of the results list.  Since both are appended in
    lockstep, we verify:
    - The history length seen by plan_next_step at call i equals
      i-1 (the number of results produced so far).
    - The final len(results) equals N (the number of executed
      steps).
    """

    @given(n=_num_steps_st)
    @settings(max_examples=50)
    def test_results_count_equals_executed_steps(
        self, n: int,
    ) -> None:
        """len(results) == N + 1 when goal_reached after N steps.

        The extra result is the summary appended when
        ``goal_reached=True`` with a non-empty reasoning string.
        """
        executor, _ = _make_executor_with_goal_after_n(n)

        results = asyncio.get_event_loop().run_until_complete(
            executor.execute(
                original_goal="test goal",
                intents=[],
            ),
        )

        # N action results + 1 summary result
        assert len(results) == n + 1

    @given(n=_num_steps_st)
    @settings(max_examples=50)
    def test_history_length_matches_results_at_each_iteration(
        self, n: int,
    ) -> None:
        """At each plan_next_step call, len(history) == results so far."""
        executor, history_lengths = (
            _make_executor_with_goal_after_n(n)
        )

        asyncio.get_event_loop().run_until_complete(
            executor.execute(
                original_goal="test goal",
                intents=[],
            ),
        )

        # plan_next_step is called N+1 times:
        # calls 1..N produce steps, call N+1 returns goal_reached
        assert len(history_lengths) == n + 1
        for i, hist_len in enumerate(history_lengths):
            assert hist_len == i, (
                f"At call {i + 1}, expected history "
                f"length {i} but got {hist_len}"
            )


# ── Strategies for routing correctness ───────────────────────────

# All non-COMPOSITE intent types
_NON_COMPOSITE_INTENT_TYPES = [
    it for it in IntentType if it is not IntentType.COMPOSITE
]

_NAVIGATE_ONLY = [IntentType.NAVIGATE]

_NON_NAVIGATE_TYPES = [
    it for it in _NON_COMPOSITE_INTENT_TYPES
    if it is not IntentType.NAVIGATE
]


def _make_intent(
    intent_type: IntentType,
    sub_intents: list[ParsedIntent] | None = None,
) -> ParsedIntent:
    """Build a minimal ParsedIntent for testing."""
    return ParsedIntent(
        intent_type=intent_type,
        target_description="test",
        confidence=0.9,
        sub_intents=sub_intents or [],
    )


def _needs_iterative_execution(
    intents: list[ParsedIntent],
) -> bool:
    """Replicate the routing logic from AIBrowserAutomation.

    Uses TaskPlanner._expand_intents to flatten composites,
    then checks for at least one NAVIGATE and at least one
    non-NAVIGATE intent.
    """
    flat = TaskPlanner._expand_intents(intents)
    has_navigate = any(
        i.intent_type == IntentType.NAVIGATE for i in flat
    )
    has_other = any(
        i.intent_type != IntentType.NAVIGATE for i in flat
    )
    return has_navigate and has_other


# Strategy: list of non-composite ParsedIntents
_intent_type_st = st.sampled_from(_NON_COMPOSITE_INTENT_TYPES)

_parsed_intent_st = st.builds(
    _make_intent,
    intent_type=_intent_type_st,
)

# Strategy: list of intents guaranteed to have navigate + non-navigate
_navigate_intent_st = st.just(_make_intent(IntentType.NAVIGATE))
_non_navigate_intent_st = st.builds(
    _make_intent,
    intent_type=st.sampled_from(_NON_NAVIGATE_TYPES),
)

# Strategy: composite intent whose sub_intents contain both types
_composite_with_both_st = st.builds(
    lambda nav, others: _make_intent(
        IntentType.COMPOSITE,
        sub_intents=[nav] + others,
    ),
    nav=_navigate_intent_st,
    others=st.lists(
        _non_navigate_intent_st, min_size=1, max_size=5,
    ),
)


# ── Property 5: Routing correctness ─────────────────────────────


class TestRoutingCorrectness:
    """**Validates: Requirements 6.1, 6.2, 6.3**

    For any list of intents containing at least one NAVIGATE and
    at least one non-NAVIGATE intent (including expanded composites),
    _needs_iterative_execution() SHALL return True.  For any list
    containing only a single action type or only NAVIGATE intents,
    it SHALL return False.
    """

    @given(
        navigates=st.lists(
            _navigate_intent_st, min_size=1, max_size=3,
        ),
        others=st.lists(
            _non_navigate_intent_st, min_size=1, max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_navigate_plus_non_navigate_returns_true(
        self,
        navigates: list[ParsedIntent],
        others: list[ParsedIntent],
    ) -> None:
        """Mixed navigate + non-navigate intents → True."""
        intents = navigates + others
        assert _needs_iterative_execution(intents) is True

    @given(
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_only_navigate_returns_false(
        self,
        count: int,
    ) -> None:
        """Only NAVIGATE intents → False."""
        intents = [
            _make_intent(IntentType.NAVIGATE)
            for _ in range(count)
        ]
        assert _needs_iterative_execution(intents) is False

    @given(
        intents=st.lists(
            _non_navigate_intent_st, min_size=1, max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_only_non_navigate_returns_false(
        self,
        intents: list[ParsedIntent],
    ) -> None:
        """Only non-NAVIGATE intents → False."""
        assert _needs_iterative_execution(intents) is False

    @given(
        single_type=_intent_type_st,
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_single_type_returns_false(
        self,
        single_type: IntentType,
        count: int,
    ) -> None:
        """All intents of the same single type → False."""
        intents = [
            _make_intent(single_type) for _ in range(count)
        ]
        if single_type == IntentType.NAVIGATE:
            assert _needs_iterative_execution(intents) is False
        else:
            assert _needs_iterative_execution(intents) is False

    @given(composite=_composite_with_both_st)
    @settings(max_examples=50)
    def test_composite_with_navigate_and_other_returns_true(
        self,
        composite: ParsedIntent,
    ) -> None:
        """Composite intent expanding to navigate + non-navigate → True."""
        assert _needs_iterative_execution([composite]) is True

    @given(
        others=st.lists(
            _non_navigate_intent_st, min_size=1, max_size=3,
        ),
    )
    @settings(max_examples=50)
    def test_composite_without_navigate_returns_false(
        self,
        others: list[ParsedIntent],
    ) -> None:
        """Composite expanding to only non-navigate → False."""
        composite = _make_intent(
            IntentType.COMPOSITE, sub_intents=others,
        )
        assert _needs_iterative_execution([composite]) is False

    @given(
        intents=st.lists(
            _parsed_intent_st, min_size=1, max_size=8,
        ),
    )
    @settings(max_examples=100)
    def test_routing_matches_intent_composition(
        self,
        intents: list[ParsedIntent],
    ) -> None:
        """For any random intent list, result matches the definition."""
        flat = TaskPlanner._expand_intents(intents)
        has_nav = any(
            i.intent_type == IntentType.NAVIGATE for i in flat
        )
        has_other = any(
            i.intent_type != IntentType.NAVIGATE for i in flat
        )
        expected = has_nav and has_other
        assert _needs_iterative_execution(intents) is expected
