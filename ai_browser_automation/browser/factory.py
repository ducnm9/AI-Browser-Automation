"""Browser engine factory with automatic fallback.

``BrowserEngineFactory`` attempts to create a ``PlaywrightEngine`` first.
If Playwright is unavailable (import error or instantiation failure), it
falls back to ``SeleniumEngine``.  The ``create()`` class method always
returns the ``BrowserEngine`` interface type, never a concrete type.
"""

from __future__ import annotations

import logging
from typing import Optional

from ai_browser_automation.browser.base import BrowserEngine

logger = logging.getLogger(__name__)


class BrowserEngineFactory:
    """Factory for creating a browser engine with Playwright-first fallback.

    Tries Playwright as the primary engine.  When Playwright is not
    installed or cannot be instantiated, Selenium is used instead.
    """

    @classmethod
    def create(cls) -> BrowserEngine:
        """Create a browser engine, preferring Playwright over Selenium.

        Returns:
            A ``BrowserEngine`` instance (PlaywrightEngine or
            SeleniumEngine).

        Raises:
            RuntimeError: If neither Playwright nor Selenium is
                available.
        """
        engine = cls._try_playwright()
        if engine is not None:
            return engine

        engine = cls._try_selenium()
        if engine is not None:
            return engine

        raise RuntimeError(
            "No browser engine available. "
            "Install playwright or selenium to continue."
        )

    @classmethod
    def _try_playwright(cls) -> Optional[BrowserEngine]:
        """Attempt to instantiate a PlaywrightEngine.

        Returns:
            A ``PlaywrightEngine`` instance, or ``None`` if Playwright
            is unavailable.
        """
        try:
            from ai_browser_automation.browser.playwright_engine import (
                PlaywrightEngine,
            )

            engine: BrowserEngine = PlaywrightEngine()
            logger.info("Selected browser engine: PlaywrightEngine")
            return engine
        except Exception:
            logger.warning(
                "Playwright unavailable, will try Selenium fallback"
            )
            return None

    @classmethod
    def _try_selenium(cls) -> Optional[BrowserEngine]:
        """Attempt to instantiate a SeleniumEngine.

        Returns:
            A ``SeleniumEngine`` instance, or ``None`` if Selenium
            is unavailable.
        """
        try:
            from ai_browser_automation.browser.selenium_engine import (
                SeleniumEngine,
            )

            engine: BrowserEngine = SeleniumEngine()
            logger.info("Selected browser engine: SeleniumEngine")
            return engine
        except Exception:
            logger.warning("Selenium also unavailable")
            return None


__all__ = ["BrowserEngineFactory"]
