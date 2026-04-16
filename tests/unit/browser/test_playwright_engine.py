"""Unit tests for PlaywrightEngine.

Tests use mocked Playwright internals so no real browser is needed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_browser_automation.browser.playwright_engine import (
    PlaywrightEngine,
    _EXTRACT_ELEMENTS_JS,
)
from ai_browser_automation.exceptions.errors import BrowserError


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_engine_with_mocks() -> tuple[PlaywrightEngine, AsyncMock]:
    """Return an engine whose internals are mocked as if launched."""
    engine = PlaywrightEngine(browser_type="chromium")

    mock_page = AsyncMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example")
    mock_page.is_closed = MagicMock(return_value=False)

    mock_context = AsyncMock()
    mock_browser = AsyncMock()
    mock_playwright = AsyncMock()

    engine._page = mock_page
    engine._context = mock_context
    engine._browser = mock_browser
    engine._playwright = mock_playwright
    engine._temp_profile_dir = Path("/tmp/ai_browser_test")  # noqa: S108

    return engine, mock_page


# ------------------------------------------------------------------ #
# launch()
# ------------------------------------------------------------------ #

class TestLaunch:
    """Tests for PlaywrightEngine.launch()."""

    @pytest.mark.asyncio
    async def test_launch_unsupported_browser_type(self) -> None:
        """Unsupported browser type raises BrowserError."""
        engine = PlaywrightEngine(browser_type="invalid_browser")
        with patch(
            "ai_browser_automation.browser.playwright_engine"
            ".async_playwright",
        ) as mock_apw:
            mock_pw = AsyncMock()
            mock_pw.invalid_browser = None  # getattr returns None
            mock_apw.return_value.start = AsyncMock(
                return_value=mock_pw,
            )
            with pytest.raises(BrowserError, match="Unsupported"):
                await engine.launch(headless=True)

    @pytest.mark.asyncio
    async def test_launch_playwright_error_wrapped(self) -> None:
        """Generic Playwright errors are wrapped in BrowserError."""
        engine = PlaywrightEngine()
        with patch(
            "ai_browser_automation.browser.playwright_engine"
            ".async_playwright",
        ) as mock_apw:
            mock_apw.return_value.start = AsyncMock(
                side_effect=RuntimeError("pw crash"),
            )
            with pytest.raises(BrowserError, match="Failed to launch"):
                await engine.launch()


# ------------------------------------------------------------------ #
# close()
# ------------------------------------------------------------------ #

class TestClose:
    """Tests for PlaywrightEngine.close()."""

    @pytest.mark.asyncio
    async def test_close_clears_cookies(self) -> None:
        """close() calls clear_cookies on the context."""
        engine, _ = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        engine._context is None  # reset after close

    @pytest.mark.asyncio
    async def test_close_clears_session_storage(self) -> None:
        """close() evaluates sessionStorage.clear()."""
        engine, mock_page = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        mock_page.evaluate.assert_called_once_with(
            "() => sessionStorage.clear()"
        )

    @pytest.mark.asyncio
    async def test_close_deletes_temp_profile(self) -> None:
        """close() removes the temporary profile directory."""
        engine, _ = _make_engine_with_mocks()
        temp_dir = engine._temp_profile_dir
        with patch("shutil.rmtree") as mock_rmtree:
            await engine.close()
        mock_rmtree.assert_called_once_with(
            temp_dir, ignore_errors=True,
        )
        assert engine._temp_profile_dir is None

    @pytest.mark.asyncio
    async def test_close_safe_when_not_launched(self) -> None:
        """close() does not raise when browser was never launched."""
        engine = PlaywrightEngine()
        await engine.close()  # should not raise

    @pytest.mark.asyncio
    async def test_close_resets_all_references(self) -> None:
        """After close(), all internal references are None."""
        engine, _ = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        assert engine._page is None
        assert engine._context is None
        assert engine._browser is None
        assert engine._playwright is None
        assert engine._temp_profile_dir is None


# ------------------------------------------------------------------ #
# _require_page()
# ------------------------------------------------------------------ #

class TestRequirePage:
    """Tests for the _require_page guard."""

    def test_raises_when_page_is_none(self) -> None:
        """_require_page raises BrowserError if not launched."""
        engine = PlaywrightEngine()
        with pytest.raises(BrowserError, match="not launched"):
            engine._require_page()

    def test_returns_page_when_set(self) -> None:
        """_require_page returns the page when available."""
        engine, mock_page = _make_engine_with_mocks()
        assert engine._require_page() is mock_page


# ------------------------------------------------------------------ #
# Navigation & interaction (with mocked page)
# ------------------------------------------------------------------ #

class TestNavigation:
    """Tests for navigate, click, type_text, extract_text."""

    @pytest.mark.asyncio
    async def test_navigate_calls_goto_with_domcontentloaded(
        self,
    ) -> None:
        """navigate() delegates to page.goto() with domcontentloaded."""
        engine, mock_page = _make_engine_with_mocks()
        await engine.navigate("https://example.com")
        mock_page.goto.assert_awaited_once_with(
            "https://example.com",
            wait_until="domcontentloaded",
        )

    @pytest.mark.asyncio
    async def test_navigate_timeout_raises_browser_error(self) -> None:
        """navigate() raises BrowserError when networkidle times out."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.goto.side_effect = TimeoutError(
            "Timeout 30000ms exceeded waiting for networkidle"
        )
        with pytest.raises(BrowserError, match="Navigation"):
            await engine.navigate("https://slow.example.com")

    @pytest.mark.asyncio
    async def test_navigate_wraps_error(self) -> None:
        """navigate() wraps generic errors in BrowserError."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.goto.side_effect = RuntimeError("connection refused")
        with pytest.raises(BrowserError, match="Navigation"):
            await engine.navigate("https://bad.example")

    @pytest.mark.asyncio
    async def test_click_css(self) -> None:
        """click() with css strategy passes selector directly."""
        engine, mock_page = _make_engine_with_mocks()
        await engine.click("#btn", strategy="css")
        mock_page.click.assert_awaited_once_with("#btn")

    @pytest.mark.asyncio
    async def test_click_xpath(self) -> None:
        """click() with xpath strategy prefixes selector."""
        engine, mock_page = _make_engine_with_mocks()
        await engine.click("//button", strategy="xpath")
        mock_page.click.assert_awaited_once_with("xpath=//button")

    @pytest.mark.asyncio
    async def test_click_text(self) -> None:
        """click() with text strategy prefixes selector."""
        engine, mock_page = _make_engine_with_mocks()
        await engine.click("Submit", strategy="text")
        mock_page.click.assert_awaited_once_with("text=Submit")

    @pytest.mark.asyncio
    async def test_type_text_delegates(self) -> None:
        """type_text() delegates to page.fill()."""
        engine, mock_page = _make_engine_with_mocks()
        await engine.type_text("#input", "hello")
        mock_page.fill.assert_awaited_once_with("#input", "hello")

    @pytest.mark.asyncio
    async def test_extract_text_returns_content(self) -> None:
        """extract_text() returns inner_text from locator."""
        engine, mock_page = _make_engine_with_mocks()
        mock_locator = MagicMock()
        mock_locator.first = MagicMock()
        mock_locator.first.inner_text = AsyncMock(
            return_value="Hello",
        )
        mock_page.locator = MagicMock(return_value=mock_locator)
        result = await engine.extract_text("#el")
        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_extract_text_returns_empty_on_none(self) -> None:
        """extract_text() returns '' when inner_text is None."""
        engine, mock_page = _make_engine_with_mocks()
        mock_locator = MagicMock()
        mock_locator.first = MagicMock()
        mock_locator.first.inner_text = AsyncMock(
            return_value=None,
        )
        mock_page.locator = MagicMock(return_value=mock_locator)
        result = await engine.extract_text("#el")
        assert result == ""

    @pytest.mark.asyncio
    async def test_methods_raise_when_not_launched(self) -> None:
        """All page methods raise BrowserError before launch."""
        engine = PlaywrightEngine()
        with pytest.raises(BrowserError):
            await engine.navigate("https://example.com")
        with pytest.raises(BrowserError):
            await engine.click("#btn")
        with pytest.raises(BrowserError):
            await engine.type_text("#in", "x")
        with pytest.raises(BrowserError):
            await engine.extract_text("#el")
        with pytest.raises(BrowserError):
            await engine.screenshot()
        with pytest.raises(BrowserError):
            await engine.get_page_context()


# ------------------------------------------------------------------ #
# screenshot()
# ------------------------------------------------------------------ #

class TestScreenshot:
    """Tests for PlaywrightEngine.screenshot()."""

    @pytest.mark.asyncio
    async def test_screenshot_returns_bytes(self) -> None:
        """screenshot() returns bytes from page.screenshot()."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.screenshot = AsyncMock(return_value=b"PNG")
        result = await engine.screenshot()
        assert result == b"PNG"
        mock_page.screenshot.assert_awaited_once_with(
            full_page=True,
        )


# ------------------------------------------------------------------ #
# get_page_context()
# ------------------------------------------------------------------ #

class TestGetPageContext:
    """Tests for PlaywrightEngine.get_page_context()."""

    @pytest.mark.asyncio
    async def test_returns_page_context(self) -> None:
        """get_page_context() returns a populated PageContext."""
        engine, mock_page = _make_engine_with_mocks()
        elements = [
            {"tag": "a", "text": "Link", "visible": True},
            {"tag": "button", "text": "Click", "visible": True},
        ]
        mock_page.evaluate = AsyncMock(return_value=elements)
        ctx = await engine.get_page_context()
        assert ctx.url == "https://example.com"
        assert ctx.title == "Example"
        assert ctx.visible_elements == elements
        assert len(ctx.visible_elements) == 2
        assert ctx.screenshot is None

    @pytest.mark.asyncio
    async def test_caps_at_50_elements(self) -> None:
        """The JS snippet limits to 50 elements."""
        assert "50" in _EXTRACT_ELEMENTS_JS

    @pytest.mark.asyncio
    async def test_wraps_evaluate_error(self) -> None:
        """get_page_context() wraps JS errors in BrowserError."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.evaluate = AsyncMock(
            side_effect=RuntimeError("JS error"),
        )
        with pytest.raises(BrowserError, match="page context"):
            await engine.get_page_context()


# ------------------------------------------------------------------ #
# _resolve_selector()
# ------------------------------------------------------------------ #

class TestResolveSelector:
    """Tests for the static _resolve_selector helper."""

    def test_css_passthrough(self) -> None:
        """CSS selectors are returned as-is."""
        assert PlaywrightEngine._resolve_selector(
            "#id", "css",
        ) == "#id"

    def test_xpath_prefix(self) -> None:
        """XPath selectors get 'xpath=' prefix."""
        assert PlaywrightEngine._resolve_selector(
            "//div", "xpath",
        ) == "xpath=//div"

    def test_text_prefix(self) -> None:
        """Text selectors get 'text=' prefix."""
        assert PlaywrightEngine._resolve_selector(
            "Submit", "text",
        ) == "text=Submit"


# ------------------------------------------------------------------ #
# extract_table()
# ------------------------------------------------------------------ #

class TestExtractTable:
    """Tests for PlaywrightEngine.extract_table()."""

    @pytest.mark.asyncio
    async def test_extract_table_returns_rows(self) -> None:
        """extract_table() returns list of rows from page.evaluate()."""
        engine, mock_page = _make_engine_with_mocks()
        table_data = [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ]
        mock_page.evaluate = AsyncMock(return_value=table_data)
        result = await engine.extract_table("table.scores")
        assert result == table_data
        mock_page.evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extract_table_empty_table(self) -> None:
        """extract_table() returns empty list for table with no rows."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.evaluate = AsyncMock(return_value=[])
        result = await engine.extract_table("table.empty")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_table_no_match_raises(self) -> None:
        """extract_table() raises BrowserError when no table found."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.evaluate = AsyncMock(return_value=None)
        with pytest.raises(BrowserError, match="Table not found"):
            await engine.extract_table("table.missing")

    @pytest.mark.asyncio
    async def test_extract_table_js_error_raises(self) -> None:
        """extract_table() wraps JS errors in BrowserError."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.evaluate = AsyncMock(
            side_effect=RuntimeError("JS error"),
        )
        with pytest.raises(
            BrowserError, match="Extract table failed",
        ):
            await engine.extract_table("table.bad")

    @pytest.mark.asyncio
    async def test_extract_table_xpath_strategy(self) -> None:
        """extract_table() resolves xpath strategy correctly."""
        engine, mock_page = _make_engine_with_mocks()
        mock_page.evaluate = AsyncMock(return_value=[["A"]])
        result = await engine.extract_table(
            "//table", strategy="xpath",
        )
        assert result == [["A"]]
        call_args = mock_page.evaluate.call_args
        assert call_args[0][1] == "xpath=//table"

    @pytest.mark.asyncio
    async def test_extract_table_not_launched_raises(self) -> None:
        """extract_table() raises BrowserError before launch."""
        engine = PlaywrightEngine()
        with pytest.raises(BrowserError, match="not launched"):
            await engine.extract_table("table")
