"""Browser engine layer: abstract interface, engines, and factory."""

from __future__ import annotations

from ai_browser_automation.browser.base import BrowserEngine, PageContext
from ai_browser_automation.browser.factory import BrowserEngineFactory
from ai_browser_automation.browser.playwright_engine import PlaywrightEngine
from ai_browser_automation.browser.selenium_engine import SeleniumEngine

__all__ = [
    "BrowserEngine",
    "BrowserEngineFactory",
    "PageContext",
    "PlaywrightEngine",
    "SeleniumEngine",
]
