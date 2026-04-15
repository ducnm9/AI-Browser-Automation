"""Unit tests for BrowserEngineFactory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_browser_automation.browser.base import BrowserEngine
from ai_browser_automation.browser.factory import BrowserEngineFactory


class TestBrowserEngineFactory:
    """Tests for BrowserEngineFactory.create() fallback logic."""

    def test_create_returns_playwright_when_available(self) -> None:
        """create() returns PlaywrightEngine when Playwright is importable."""
        with patch.object(
            BrowserEngineFactory,
            "_try_playwright",
        ) as mock_pw:
            sentinel = object()
            mock_pw.return_value = sentinel

            result = BrowserEngineFactory.create()

            assert result is sentinel
            mock_pw.assert_called_once()

    def test_create_falls_back_to_selenium(self) -> None:
        """create() falls back to SeleniumEngine when Playwright fails."""
        with patch.object(
            BrowserEngineFactory,
            "_try_playwright",
            return_value=None,
        ), patch.object(
            BrowserEngineFactory,
            "_try_selenium",
        ) as mock_sel:
            sentinel = object()
            mock_sel.return_value = sentinel

            result = BrowserEngineFactory.create()

            assert result is sentinel
            mock_sel.assert_called_once()

    def test_create_raises_when_no_engine_available(self) -> None:
        """create() raises RuntimeError when both engines fail."""
        with patch.object(
            BrowserEngineFactory,
            "_try_playwright",
            return_value=None,
        ), patch.object(
            BrowserEngineFactory,
            "_try_selenium",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="No browser engine"):
                BrowserEngineFactory.create()

    def test_try_playwright_returns_none_on_import_error(
        self,
    ) -> None:
        """_try_playwright() returns None when Playwright import fails."""
        with patch(
            "ai_browser_automation.browser.playwright_engine"
            ".PlaywrightEngine",
            side_effect=ImportError("no playwright"),
        ):
            result = BrowserEngineFactory._try_playwright()
            assert result is None

    def test_try_selenium_returns_none_on_import_error(
        self,
    ) -> None:
        """_try_selenium() returns None when Selenium import fails."""
        with patch(
            "ai_browser_automation.browser.selenium_engine"
            ".SeleniumEngine",
            side_effect=ImportError("no selenium"),
        ):
            result = BrowserEngineFactory._try_selenium()
            assert result is None
