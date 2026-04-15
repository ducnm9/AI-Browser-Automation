"""CLI chat interface for interactive browser automation.

Provides a simple read-eval-print loop that accepts natural-language
commands, forwards them to :class:`AIBrowserAutomation`, and displays
the results.  Handles graceful shutdown on ``Ctrl+C`` / ``EOF``.

Requirements: 9.1
"""

from __future__ import annotations

import asyncio
import logging

from ai_browser_automation.app import AIBrowserAutomation

logger = logging.getLogger(__name__)

_PROMPT = ">>> "
_WELCOME = (
    "AI Browser Automation — type a command or 'exit' to quit."
)
_GOODBYE = "Shutting down. Goodbye!"


class ChatInterface:
    """CLI chat loop wrapping an :class:`AIBrowserAutomation` instance.

    Args:
        app: An already-constructed (but not necessarily initialised)
            ``AIBrowserAutomation`` facade.
    """

    def __init__(self, app: AIBrowserAutomation) -> None:
        self._app = app

    async def run(self) -> None:
        """Start the interactive chat loop.

        Initialises the application, then repeatedly reads user
        input, calls ``app.chat()``, and prints the result.  The
        loop exits on ``exit`` / ``quit``, ``Ctrl+C``, or ``EOF``.
        The application is always shut down cleanly.
        """
        await self._app.initialize()
        print(_WELCOME)  # noqa: T201

        try:
            await self._loop()
        except (KeyboardInterrupt, EOFError):
            print()  # noqa: T201
        finally:
            print(_GOODBYE)  # noqa: T201
            await self._app.shutdown()

    async def _loop(self) -> None:
        """Read-eval-print loop (extracted for testability)."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                user_input: str = await loop.run_in_executor(
                    None, lambda: input(_PROMPT),
                )
            except (KeyboardInterrupt, EOFError):
                raise

            stripped = user_input.strip()
            if not stripped:
                continue
            if stripped.lower() in {"exit", "quit"}:
                break

            result = await self._app.chat(stripped)
            print(result)  # noqa: T201


__all__ = ["ChatInterface"]
