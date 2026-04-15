"""Exception hierarchy for AI Browser Automation."""

from __future__ import annotations

from ai_browser_automation.exceptions.errors import (
    ActionExecutionError,
    AppError,
    BrowserError,
    ConfigValidationError,
    LLMUnavailableError,
    NLProcessingError,
    PlanningError,
    SecurityError,
)

__all__ = [
    "AppError",
    "LLMUnavailableError",
    "BrowserError",
    "NLProcessingError",
    "SecurityError",
    "ConfigValidationError",
    "ActionExecutionError",
    "PlanningError",
]
