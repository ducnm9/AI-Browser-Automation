"""Intent types and parsed intent data models.

Defines the vocabulary of user intents that the NL Processor can extract
from natural-language commands, along with the structured representation
of a parsed intent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IntentType(Enum):
    """Enumeration of supported browser-automation intents."""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE_TEXT = "type_text"
    EXTRACT_DATA = "extract_data"
    LOGIN = "login"
    SCROLL = "scroll"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    COMPOSITE = "composite"


@dataclass
class ParsedIntent:
    """Structured representation of a user intent extracted by the NL Processor.

    Args:
        intent_type: The category of action the user wants to perform.
        target_description: Natural-language description of the target
            element.
        parameters: Additional key-value parameters for the intent
            (e.g. url, limit, data_type, sort_by).
        confidence: Model confidence score in the range [0.0, 1.0].
        execution_order: Sequence number for ordered execution within
            a composite intent (1-based, 0 means unset).
        assumptions: Implicit assumptions the parser made about the
            user's command.
        requires_clarification: Whether the intent is ambiguous and
            would benefit from user clarification.
        sub_intents: Child intents when ``intent_type`` is ``COMPOSITE``.
    """

    intent_type: IntentType
    target_description: str
    parameters: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0
    execution_order: int = 0
    assumptions: list[str] = field(default_factory=list)
    requires_clarification: bool = False
    sub_intents: list[ParsedIntent] = field(default_factory=list)


__all__ = [
    "IntentType",
    "ParsedIntent",
]
