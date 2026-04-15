"""Unit tests for data models: conversation, actions, and intents.

Validates: Requirements 3.1, 3.6, 7.1, 7.2
"""

from __future__ import annotations

from ai_browser_automation.models.actions import (
    ActionResult,
    ActionStep,
    ExecutionPlan,
)
from ai_browser_automation.models.conversation import (
    ConversationHistory,
    ConversationTurn,
)
from ai_browser_automation.models.intents import IntentType, ParsedIntent


# ------------------------------------------------------------------ #
# ConversationHistory
# ------------------------------------------------------------------ #


class TestConversationHistoryAddTurn:
    """Tests for ConversationHistory.add_turn() trimming behaviour."""

    def test_add_turn_trims_oldest_when_exceeding_max(self) -> None:
        """Oldest turns are dropped when history exceeds max_context_turns.

        Validates: Requirement 7.2
        """
        history = ConversationHistory(max_context_turns=3)
        for i in range(5):
            history.add_turn(
                ConversationTurn(
                    role="user",
                    content=f"msg-{i}",
                    timestamp=float(i),
                )
            )

        assert len(history.turns) == 3
        # Only the three most recent turns survive.
        assert [t.content for t in history.turns] == [
            "msg-2",
            "msg-3",
            "msg-4",
        ]

    def test_add_turn_no_trim_when_under_limit(self) -> None:
        """No trimming occurs when turn count is within the limit.

        Validates: Requirement 7.1
        """
        history = ConversationHistory(max_context_turns=10)
        history.add_turn(
            ConversationTurn(
                role="user", content="hello", timestamp=0.0,
            )
        )
        history.add_turn(
            ConversationTurn(
                role="assistant", content="hi", timestamp=1.0,
            )
        )

        assert len(history.turns) == 2


class TestConversationHistoryGetContextWindow:
    """Tests for ConversationHistory.get_context_window()."""

    def test_returns_at_most_max_context_turns(self) -> None:
        """get_context_window() never returns more than max_context_turns.

        Validates: Requirement 7.2
        """
        history = ConversationHistory(max_context_turns=2)
        for i in range(5):
            history.add_turn(
                ConversationTurn(
                    role="user",
                    content=f"msg-{i}",
                    timestamp=float(i),
                )
            )

        window = history.get_context_window()
        assert len(window) <= 2

    def test_returns_all_when_under_limit(self) -> None:
        """All turns returned when count is below max_context_turns.

        Validates: Requirement 7.1
        """
        history = ConversationHistory(max_context_turns=10)
        history.add_turn(
            ConversationTurn(
                role="user", content="a", timestamp=0.0,
            )
        )

        assert len(history.get_context_window()) == 1


# ------------------------------------------------------------------ #
# ActionResult defaults
# ------------------------------------------------------------------ #


class TestActionResultDefaults:
    """Tests for ActionResult default field values.

    Validates: Requirements 3.1, 3.6
    """

    def test_defaults(self) -> None:
        """Optional fields default to None/0.0 when not provided."""
        step = ActionStep(
            action_type="click",
            selector_strategy="css",
            selector_value="#btn",
        )
        result = ActionResult(success=True, step=step)

        assert result.extracted_data is None
        assert result.screenshot is None
        assert result.error_message is None
        assert result.duration_ms == 0.0

    def test_explicit_values_override_defaults(self) -> None:
        """Explicitly provided values take precedence over defaults."""
        step = ActionStep(
            action_type="extract",
            selector_strategy="xpath",
            selector_value="//div",
        )
        result = ActionResult(
            success=False,
            step=step,
            extracted_data="some data",
            screenshot=b"png",
            error_message="timeout",
            duration_ms=123.4,
        )

        assert result.extracted_data == "some data"
        assert result.screenshot == b"png"
        assert result.error_message == "timeout"
        assert result.duration_ms == 123.4


# ------------------------------------------------------------------ #
# ExecutionPlan construction
# ------------------------------------------------------------------ #


class TestExecutionPlanConstruction:
    """Tests for ExecutionPlan construction.

    Validates: Requirement 3.1
    """

    def test_construction_with_steps(self) -> None:
        """ExecutionPlan stores steps, description, and duration."""
        steps = [
            ActionStep(
                action_type="navigate",
                selector_strategy="css",
                selector_value="",
            ),
            ActionStep(
                action_type="click",
                selector_strategy="css",
                selector_value="#btn",
            ),
        ]
        plan = ExecutionPlan(
            steps=steps,
            description="Navigate and click",
            estimated_duration_ms=5000,
        )

        assert len(plan.steps) == 2
        assert plan.description == "Navigate and click"
        assert plan.estimated_duration_ms == 5000
        assert plan.requires_auth is False
        assert plan.sensitive_data_involved is False

    def test_default_construction(self) -> None:
        """ExecutionPlan defaults to empty steps and zero duration."""
        plan = ExecutionPlan()

        assert plan.steps == []
        assert plan.description == ""
        assert plan.estimated_duration_ms == 0


# ------------------------------------------------------------------ #
# ParsedIntent
# ------------------------------------------------------------------ #


class TestParsedIntentSubIntents:
    """Tests for ParsedIntent with sub_intents (COMPOSITE type).

    Validates: Requirement 3.1
    """

    def test_composite_with_sub_intents(self) -> None:
        """COMPOSITE intent holds child sub_intents."""
        child_a = ParsedIntent(
            intent_type=IntentType.NAVIGATE,
            target_description="Go to Gmail",
            confidence=0.9,
        )
        child_b = ParsedIntent(
            intent_type=IntentType.CLICK,
            target_description="Click inbox",
            confidence=0.85,
        )
        composite = ParsedIntent(
            intent_type=IntentType.COMPOSITE,
            target_description="Login and read email",
            sub_intents=[child_a, child_b],
            confidence=0.88,
        )

        assert composite.intent_type is IntentType.COMPOSITE
        assert len(composite.sub_intents) == 2
        assert composite.sub_intents[0].intent_type is IntentType.NAVIGATE
        assert composite.sub_intents[1].intent_type is IntentType.CLICK


class TestParsedIntentDefaults:
    """Tests for ParsedIntent default values.

    Validates: Requirement 3.1
    """

    def test_defaults(self) -> None:
        """parameters, confidence, and sub_intents default correctly."""
        intent = ParsedIntent(
            intent_type=IntentType.CLICK,
            target_description="a button",
        )

        assert intent.parameters == {}
        assert intent.confidence == 0.0
        assert intent.sub_intents == []
