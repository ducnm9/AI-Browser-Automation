"""Custom exception hierarchy for AI Browser Automation.

All application-specific exceptions inherit from ``AppError`` so callers can
catch a single base type when broad error handling is appropriate.
"""

from __future__ import annotations


class AppError(Exception):
    """Base exception for all application errors.

    Args:
        message: Human-readable error description.
    """

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


class LLMUnavailableError(AppError):
    """Raised when no LLM provider is available to handle a request.

    Args:
        message: Human-readable error description.
    """


class BrowserError(AppError):
    """Raised when a browser engine operation fails.

    Args:
        message: Human-readable error description.
    """


class NLProcessingError(AppError):
    """Raised when natural-language processing fails.

    Args:
        message: Human-readable error description.
    """


class SecurityError(AppError):
    """Raised when a security policy violation is detected.

    Args:
        message: Human-readable error description.
    """


class ConfigValidationError(AppError):
    """Raised when configuration validation fails.

    Args:
        message: Human-readable error description.
    """


class ActionExecutionError(AppError):
    """Raised when a browser action step fails to execute.

    Args:
        message: Human-readable error description.
    """


class PlanningError(AppError):
    """Raised when the task planner cannot produce an execution plan.

    Args:
        message: Human-readable error description.
    """


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
