"""Conversation turn and history data models.

Tracks the dialogue between the user and the assistant, enforcing role
and content validation and automatically trimming old turns to stay
within the configured context window.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai_browser_automation.models.actions import ActionResult

_VALID_ROLES = frozenset({"user", "assistant"})


@dataclass
class ConversationTurn:
    """A single turn in the conversation.

    Args:
        role: Must be ``"user"`` or ``"assistant"``.
        content: The message text (must be non-empty).
        timestamp: Unix epoch timestamp of the turn.
        actions_taken: Browser actions executed during this turn.

    Raises:
        ValueError: If ``role`` is not ``"user"``/``"assistant"`` or
            ``content`` is empty.
    """

    role: str
    content: str
    timestamp: float = 0.0
    actions_taken: list[ActionResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.role not in _VALID_ROLES:
            raise ValueError(
                f"role must be 'user' or 'assistant', got '{self.role}'"
            )
        if not self.content:
            raise ValueError("content must be non-empty")


@dataclass
class ConversationHistory:
    """Bounded conversation history with automatic trimming.

    Args:
        turns: List of conversation turns.
        max_context_turns: Maximum number of turns to retain.
    """

    turns: list[ConversationTurn] = field(default_factory=list)
    max_context_turns: int = 20

    def add_turn(self, turn: ConversationTurn) -> None:
        """Append a turn and trim oldest turns if over the limit.

        Args:
            turn: The conversation turn to add.
        """
        self.turns.append(turn)
        if len(self.turns) > self.max_context_turns:
            self.turns = self.turns[-self.max_context_turns :]

    def get_context_window(self) -> list[ConversationTurn]:
        """Return the most recent turns within the context window.

        Returns:
            At most ``max_context_turns`` most-recent turns.
        """
        return self.turns[-self.max_context_turns :]


__all__ = [
    "ConversationTurn",
    "ConversationHistory",
]
