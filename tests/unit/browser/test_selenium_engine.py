"""Unit tests for SeleniumEngine.

Tests use mocked Selenium WebDriver internals so no real browser is
needed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_browser_automation.browser.selenium_engine import (
    SeleniumEngine,
    _EXTRACT_ELEMENTS_JS,
    _MAX_VISIBLE_ELEMENTS,
)
from ai_browser_automation.exceptions.errors import BrowserError


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_engine_with_mocks() -> tuple[SeleniumEngine, MagicMock]:
    """Return an engine whose internals are mocked as if launched."""
    engine = SeleniumEngine()

    mock_driver = MagicMock()
    mock_driver.current_url = "https://example.com"
    mock_driver.title = "Example"

    engine._driver = mock_driver
    engine._temp_profile_dir = Path("/tmp/ai_browser_sel_test")  # noqa: S108

    return engine, mock_driver


# ------------------------------------------------------------------ #
# launch()
# ------------------------------------------------------------------ #

class TestLaunch:
    """Tests for SeleniumEngine.launch()."""

    @pytest.mark.asyncio
    async def test_launch_wraps_selenium_error(self) -> None:
        """Generic Selenium errors are wrapped in BrowserError."""
        engine = SeleniumEngine()
        with patch(
            "ai_browser_automation.browser.selenium_engine"
            ".webdriver.Chrome",
            side_effect=RuntimeError("chrome crash"),
        ):
            with pytest.raises(
                BrowserError, match="Failed to launch",
            ):
                await engine.launch()


# ------------------------------------------------------------------ #
# close()
# ------------------------------------------------------------------ #

class TestClose:
    """Tests for SeleniumEngine.close()."""

    @pytest.mark.asyncio
    async def test_close_deletes_cookies(self) -> None:
        """close() calls delete_all_cookies on the driver."""
        engine, mock_driver = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        mock_driver.delete_all_cookies.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_clears_session_storage(self) -> None:
        """close() executes sessionStorage.clear()."""
        engine, mock_driver = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        calls = [
            c[0][0]
            for c in mock_driver.execute_script.call_args_list
        ]
        assert "sessionStorage.clear();" in calls

    @pytest.mark.asyncio
    async def test_close_clears_local_storage(self) -> None:
        """close() executes localStorage.clear()."""
        engine, mock_driver = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        calls = [
            c[0][0]
            for c in mock_driver.execute_script.call_args_list
        ]
        assert "localStorage.clear();" in calls

    @pytest.mark.asyncio
    async def test_close_quits_driver(self) -> None:
        """close() calls driver.quit()."""
        engine, mock_driver = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        mock_driver.quit.assert_called_once()

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
        engine = SeleniumEngine()
        await engine.close()  # should not raise

    @pytest.mark.asyncio
    async def test_close_resets_all_references(self) -> None:
        """After close(), all internal references are None."""
        engine, _ = _make_engine_with_mocks()
        with patch("shutil.rmtree"):
            await engine.close()
        assert engine._driver is None
        assert engine._temp_profile_dir is None


# ------------------------------------------------------------------ #
# _require_driver()
# ------------------------------------------------------------------ #

class TestRequireDriver:
    """Tests for the _require_driver guard."""

    def test_raises_when_driver_is_none(self) -> None:
        """_require_driver raises BrowserError if not launched."""
        engine = SeleniumEngine()
        with pytest.raises(BrowserError, match="not launched"):
            engine._require_driver()

    def test_returns_driver_when_set(self) -> None:
        """_require_driver returns the driver when available."""
        engine, mock_driver = _make_engine_with_mocks()
        assert engine._require_driver() is mock_driver


# ------------------------------------------------------------------ #
# Navigation & interaction (with mocked driver)
# ------------------------------------------------------------------ #

class TestNavigation:
    """Tests for navigate, click, type_text, extract_text."""

    @pytest.mark.asyncio
    async def test_navigate_calls_get(self) -> None:
        """navigate() delegates to driver.get()."""
        engine, mock_driver = _make_engine_with_mocks()
        await engine.navigate("https://example.com")
        mock_driver.get.assert_called_once_with(
            "https://example.com",
        )

    @pytest.mark.asyncio
    async def test_navigate_wraps_error(self) -> None:
        """navigate() wraps errors in BrowserError."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.get.side_effect = RuntimeError("timeout")
        with pytest.raises(BrowserError, match="Navigation"):
            await engine.navigate("https://bad.example")

    @pytest.mark.asyncio
    async def test_click_css(self) -> None:
        """click() with css strategy uses CSS_SELECTOR."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_element = MagicMock()
        mock_driver.find_element.return_value = mock_element
        await engine.click("#btn", strategy="css")
        mock_driver.find_element.assert_called_once()
        mock_element.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_xpath(self) -> None:
        """click() with xpath strategy uses XPATH."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_element = MagicMock()
        mock_driver.find_element.return_value = mock_element
        await engine.click("//button", strategy="xpath")
        mock_driver.find_element.assert_called_once()
        mock_element.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_text(self) -> None:
        """click() with text strategy uses XPath contains."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_element = MagicMock()
        mock_driver.find_element.return_value = mock_element
        await engine.click("Submit", strategy="text")
        mock_driver.find_element.assert_called_once()
        mock_element.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_type_text_delegates(self) -> None:
        """type_text() clears and sends keys."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_element = MagicMock()
        mock_driver.find_element.return_value = mock_element
        await engine.type_text("#input", "hello")
        mock_element.clear.assert_called_once()
        mock_element.send_keys.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_extract_text_returns_content(self) -> None:
        """extract_text() returns element.text."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_element = MagicMock()
        mock_element.text = "Hello"
        mock_driver.find_element.return_value = mock_element
        result = await engine.extract_text("#el")
        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_extract_text_returns_empty_on_none(self) -> None:
        """extract_text() returns '' when text is empty."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_element = MagicMock()
        mock_element.text = ""
        mock_driver.find_element.return_value = mock_element
        result = await engine.extract_text("#el")
        assert result == ""

    @pytest.mark.asyncio
    async def test_methods_raise_when_not_launched(self) -> None:
        """All page methods raise BrowserError before launch."""
        engine = SeleniumEngine()
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
# extract_table()
# ------------------------------------------------------------------ #

class TestExtractTable:
    """Tests for SeleniumEngine.extract_table()."""

    @pytest.mark.asyncio
    async def test_extract_table_returns_rows(self) -> None:
        """extract_table() returns list of rows from JS result."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.execute_script.return_value = [
            ["Name", "Score"],
            ["Alice", "100"],
        ]
        result = await engine.extract_table("table.scores")
        assert result == [["Name", "Score"], ["Alice", "100"]]
        mock_driver.execute_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_table_empty_table(self) -> None:
        """extract_table() returns empty list for no rows."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.execute_script.return_value = []
        result = await engine.extract_table("table.empty")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_table_not_found_raises(self) -> None:
        """extract_table() raises BrowserError when not found."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.execute_script.return_value = None
        with pytest.raises(BrowserError, match="Table not found"):
            await engine.extract_table("table.missing")

    @pytest.mark.asyncio
    async def test_extract_table_js_error_raises(self) -> None:
        """extract_table() wraps JS errors in BrowserError."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.execute_script.side_effect = RuntimeError(
            "JS error",
        )
        with pytest.raises(
            BrowserError, match="Extract table failed",
        ):
            await engine.extract_table("table")

    @pytest.mark.asyncio
    async def test_extract_table_passes_strategy(self) -> None:
        """extract_table() passes selector and strategy to JS."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.execute_script.return_value = [["cell"]]
        await engine.extract_table("//table", strategy="xpath")
        call_args = mock_driver.execute_script.call_args
        assert call_args[0][1] == "//table"
        assert call_args[0][2] == "xpath"

    @pytest.mark.asyncio
    async def test_extract_table_not_launched(self) -> None:
        """extract_table() raises BrowserError before launch."""
        engine = SeleniumEngine()
        with pytest.raises(BrowserError, match="not launched"):
            await engine.extract_table("table")


# ------------------------------------------------------------------ #
# screenshot()
# ------------------------------------------------------------------ #

class TestScreenshot:
    """Tests for SeleniumEngine.screenshot()."""

    @pytest.mark.asyncio
    async def test_screenshot_returns_bytes(self) -> None:
        """screenshot() returns bytes from get_screenshot_as_png."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.get_screenshot_as_png.return_value = b"PNG"
        result = await engine.screenshot()
        assert result == b"PNG"
        mock_driver.get_screenshot_as_png.assert_called_once()


# ------------------------------------------------------------------ #
# get_page_context()
# ------------------------------------------------------------------ #

class TestGetPageContext:
    """Tests for SeleniumEngine.get_page_context()."""

    @pytest.mark.asyncio
    async def test_returns_page_context(self) -> None:
        """get_page_context() returns a populated PageContext."""
        engine, mock_driver = _make_engine_with_mocks()
        elements = [
            {"tag": "a", "text": "Link", "visible": True},
            {"tag": "button", "text": "Click", "visible": True},
        ]
        mock_driver.execute_script.return_value = elements
        ctx = await engine.get_page_context()
        assert ctx.url == "https://example.com"
        assert ctx.title == "Example"
        assert ctx.visible_elements == elements
        assert len(ctx.visible_elements) == 2
        assert ctx.screenshot is None

    def test_caps_at_50_elements(self) -> None:
        """The JS snippet limits to 50 elements."""
        assert str(_MAX_VISIBLE_ELEMENTS) in _EXTRACT_ELEMENTS_JS

    @pytest.mark.asyncio
    async def test_wraps_execute_script_error(self) -> None:
        """get_page_context() wraps JS errors in BrowserError."""
        engine, mock_driver = _make_engine_with_mocks()
        mock_driver.execute_script.side_effect = RuntimeError(
            "JS error",
        )
        with pytest.raises(BrowserError, match="page context"):
            await engine.get_page_context()


# ------------------------------------------------------------------ #
# _resolve_locator()
# ------------------------------------------------------------------ #

class TestResolveLocator:
    """Tests for the static _resolve_locator helper."""

    def test_css_uses_css_selector(self) -> None:
        """CSS selectors use By.CSS_SELECTOR."""
        by, val = SeleniumEngine._resolve_locator("#id", "css")
        assert by == "css selector"
        assert val == "#id"

    def test_xpath_uses_xpath(self) -> None:
        """XPath selectors use By.XPATH."""
        by, val = SeleniumEngine._resolve_locator(
            "//div", "xpath",
        )
        assert by == "xpath"
        assert val == "//div"

    def test_text_uses_xpath_contains(self) -> None:
        """Text selectors use XPath contains()."""
        by, val = SeleniumEngine._resolve_locator(
            "Submit", "text",
        )
        assert by == "xpath"
        assert "contains(text(),'Submit')" in val


# ------------------------------------------------------------------ #
# ABC contract
# ------------------------------------------------------------------ #

class TestABCContract:
    """Verify SeleniumEngine satisfies BrowserEngine ABC."""

    def test_is_subclass_of_browser_engine(self) -> None:
        """SeleniumEngine is a subclass of BrowserEngine."""
        from ai_browser_automation.browser.base import (
            BrowserEngine,
        )
        assert issubclass(SeleniumEngine, BrowserEngine)

    def test_implements_all_abstract_methods(self) -> None:
        """SeleniumEngine can be instantiated (all ABCs met)."""
        engine = SeleniumEngine()
        assert engine is not None
