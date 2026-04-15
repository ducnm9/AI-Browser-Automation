"""Property-based tests for conversation history and turn validation.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

Property 13: Conversation History Bounded
    For any ConversationHistory with max_context_turns = N, after adding
    any number of turns, the number of turns returned by
    get_context_window() SHALL never exceed N.

Property 14: Conversation Turn Validation
    For any ConversationTurn, the system SHALL accept it only if role is
    exactly "user" or "assistant" AND content is a non-empty string.
    All other combinations SHALL be rejected.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ai_browser_automation.models.conversation import (
    ConversationHistory,
    ConversationTurn,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_roles: st.SearchStrategy[str] = st.sampled_from(["user", "assistant"])

valid_content: st.SearchStrategy[str] = st.text(min_size=1)

max_context_turns_st: st.SearchStrategy[int] = st.integers(
    min_value=1, max_value=100
)

num_turns_st: st.SearchStrategy[int] = st.integers(min_value=1, max_value=100)

invalid_roles: st.SearchStrategy[str] = st.text().filter(
    lambda s: s not in ("user", "assistant")
)


# ---------------------------------------------------------------------------
# Property 13 — Conversation History Bounded
# **Validates: Requirements 7.1, 7.2**
# ---------------------------------------------------------------------------


@given(
    max_turns=max_context_turns_st,
    num_turns=num_turns_st,
    roles=st.lists(valid_roles, min_size=1, max_size=100),
    contents=st.lists(valid_content, min_size=1, max_size=100),
)
@settings(max_examples=100)
def test_context_window_never_exceeds_max(
    max_turns: int,
    num_turns: int,
    roles: list[str],
    contents: list[str],
) -> None:
    """get_context_window() never returns more than max_context_turns."""
    history = ConversationHistory(max_context_turns=max_turns)

    for i in range(num_turns):
        role = roles[i % len(roles)]
        content = contents[i % len(contents)]
        turn = ConversationTurn(role=role, content=content)
        history.add_turn(turn)

        window = history.get_context_window()
        assert len(window) <= max_turns


@given(
    max_turns=max_context_turns_st,
    num_turns=num_turns_st,
)
@settings(max_examples=100)
def test_history_trims_oldest_turns(
    max_turns: int,
    num_turns: int,
) -> None:
    """After adding more turns than max, oldest are trimmed."""
    history = ConversationHistory(max_context_turns=max_turns)

    for i in range(num_turns):
        role = "user" if i % 2 == 0 else "assistant"
        turn = ConversationTurn(role=role, content=f"message-{i}")
        history.add_turn(turn)

    window = history.get_context_window()
    assert len(window) == min(num_turns, max_turns)
    assert len(history.turns) <= max_turns


# ---------------------------------------------------------------------------
# Property 14 — Conversation Turn Validation
# **Validates: Requirements 7.3, 7.4**
# ---------------------------------------------------------------------------


@given(role=valid_roles, content=valid_content)
@settings(max_examples=100)
def test_valid_turn_accepted(role: str, content: str) -> None:
    """Turns with valid role and non-empty content are accepted."""
    turn = ConversationTurn(role=role, content=content)
    assert turn.role == role
    assert turn.content == content


@given(role=invalid_roles, content=valid_content)
@settings(max_examples=100)
def test_invalid_role_rejected(role: str, content: str) -> None:
    """Turns with invalid role raise ValueError."""
    with pytest.raises(ValueError, match="role must be"):
        ConversationTurn(role=role, content=content)


@given(role=valid_roles)
@settings(max_examples=100)
def test_empty_content_rejected(role: str) -> None:
    """Turns with empty content raise ValueError."""
    with pytest.raises(ValueError, match="content must be non-empty"):
        ConversationTurn(role=role, content="")
