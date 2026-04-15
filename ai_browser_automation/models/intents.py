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
        target_description: Natural-language description of the target element.
        parameters: Additional key-value parameters for the intent.
        confidence: Model confidence score in the range [0.0, 1.0].
        sub_intents: Child intents when ``intent_type`` is ``COMPOSITE``.
    """

    intent_type: IntentType
    target_description: str
    parameters: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    sub_intents: list[ParsedIntent] = field(default_factory=list)


__all__ = [
    "IntentType",
    "ParsedIntent",
]
