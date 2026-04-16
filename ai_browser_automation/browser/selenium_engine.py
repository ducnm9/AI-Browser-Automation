"""Selenium-based browser engine implementation.

Provides ``SeleniumEngine``, a concrete ``BrowserEngine`` that uses
Selenium WebDriver as a fallback when Playwright is unavailable.
Synchronous Selenium calls are wrapped with
``asyncio.get_running_loop().run_in_executor()`` for async compatibility.
Each session runs in an isolated temporary profile directory that is
deleted on ``close()``.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from functools import partial
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from ai_browser_automation.browser.base import BrowserEngine, PageContext
from ai_browser_automation.exceptions.errors import BrowserError

logger = logging.getLogger(__name__)

_MAX_VISIBLE_ELEMENTS = 50
_TEXT_TRUNCATE_LENGTH = 100
_MAX_CONTENT_SNIPPETS = 30
_CONTENT_TEXT_LENGTH = 200

# JavaScript snippet executed via driver.execute_script() to extract
# visible interactable elements from the current page DOM.
_EXTRACT_ELEMENTS_JS = """
var sel = 'a, button, input, select, textarea, '
        + '[role="button"], [onclick]';
var interactable = document.querySelectorAll(sel);
return Array.from(interactable).slice(0, %d).map(function(el) {
    return {
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || "").trim().substring(0, %d),
        type: el.getAttribute("type"),
        placeholder: el.getAttribute("placeholder"),
        aria_label: el.getAttribute("aria-label"),
        href: el.getAttribute("href"),
        id: el.id || null,
        name: el.getAttribute("name"),
        visible: el.offsetParent !== null
    };
}).filter(function(el) { return el.visible; });
""" % (_MAX_VISIBLE_ELEMENTS, _TEXT_TRUNCATE_LENGTH)

# JavaScript snippet to extract content elements (headings,
# articles, paragraphs) for data-extraction planning.
_EXTRACT_CONTENT_JS = """
var sel = 'h1, h2, h3, h4, article, .article, '
        + '[class*="title"], [class*="headline"], '
        + '.item-news, .title-news';
var nodes = document.querySelectorAll(sel);
return Array.from(nodes).slice(0, %d).map(function(el) {
    var link = el.querySelector('a');
    return {
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || "").trim().substring(0, %d),
        href: link ? link.getAttribute("href") : null,
        class_name: el.className
            ? el.className.substring(0, 80)
            : null,
        selector: el.id
            ? "#" + el.id
            : el.tagName.toLowerCase()
              + (el.className
                 ? "." + el.className.split(" ")[0]
                 : "")
    };
}).filter(function(el) { return el.text.length > 0; });
""" % (_MAX_CONTENT_SNIPPETS, _CONTENT_TEXT_LENGTH)


def _build_dom_summary(elements: list[dict]) -> str:
    """Build a compact one-line-per-element DOM summary.

    Produces a much smaller string than ``str(elements)`` so the
    LLM prompt stays within the model's context window.

    Args:
        elements: Visible interactable elements from the page.

    Returns:
        Compact multi-line summary string.
    """
    lines: list[str] = []
    for el in elements:
        tag = el.get("tag", "?")
        text = (el.get("text") or "")[:60]
        eid = el.get("id") or ""
        href = (el.get("href") or "")[:80]
        parts = [tag]
        if eid:
            parts.append(f'id="{eid}"')
        if href:
            parts.append(f'href="{href}"')
        if text:
            parts.append(f'"{text}"')
        lines.append(" ".join(parts))
    return (
        f"{len(elements)} interactive elements:\n"
        + "\n".join(lines)
    )


class SeleniumEngine(BrowserEngine):
    """Browser engine backed by Selenium WebDriver (Chrome).

    Acts as a fallback when Playwright is unavailable.  All synchronous
    Selenium calls are executed in a thread-pool via
    ``asyncio.get_running_loop().run_in_executor()`` so the engine
    exposes the same async API as ``PlaywrightEngine``.

    Each ``launch()`` creates a temporary profile directory for browser
    isolation.  ``close()`` clears cookies, session data, and removes
    the temporary directory so that no data persists between sessions.
    """

    def __init__(self) -> None:
        self._driver: Optional[WebDriver] = None
        self._temp_profile_dir: Optional[Path] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_sync(self, func: partial) -> object:  # type: ignore[type-arg]
        """Run a synchronous callable in the default executor.

        Args:
            func: A ``functools.partial`` wrapping the sync call.

        Returns:
            The return value of *func*.

        Raises:
            BrowserError: If the underlying call raises.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func)

    def _require_driver(self) -> WebDriver:
        """Return the active WebDriver or raise ``BrowserError``.

        Raises:
            BrowserError: If the browser has not been launched.
        """
        if self._driver is None:
            raise BrowserError(
                "Browser not launched. Call launch() first."
            )
        return self._driver

    @staticmethod
    def _resolve_locator(
        selector: str, strategy: str,
    ) -> tuple[str, str]:
        """Convert a *(selector, strategy)* pair to a Selenium locator.

        Args:
            selector: Raw selector value.
            strategy: One of ``css``, ``xpath``, or ``text``.

        Returns:
            Tuple of ``(By.<method>, selector_value)``.
        """
        if strategy == "xpath":
            return (By.XPATH, selector)
        if strategy == "text":
            return (
                By.XPATH,
                f"//*[contains(text(),'{selector}')]",
            )
        return (By.CSS_SELECTOR, selector)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def launch(self, headless: bool = False) -> None:
        """Launch a Chrome browser instance with an isolated profile.

        Args:
            headless: Run in headless mode when ``True``.

        Raises:
            BrowserError: If Selenium fails to start Chrome.
        """
        try:
            self._temp_profile_dir = Path(
                tempfile.mkdtemp(prefix="ai_browser_sel_"),
            )
            options = ChromeOptions()
            options.add_argument(
                f"--user-data-dir={self._temp_profile_dir}",
            )
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-first-run")
            options.add_argument("--disable-extensions")

            def _create_driver() -> WebDriver:
                return webdriver.Chrome(
                    service=ChromeService(),
                    options=options,
                )

            self._driver = await self._run_sync(
                partial(_create_driver),
            )
            logger.info(
                "Selenium browser launched (headless=%s)",
                headless,
            )
        except BrowserError:
            raise
        except Exception as exc:
            raise BrowserError(
                f"Failed to launch Selenium browser: {exc}"
            ) from exc

    async def close(self) -> None:
        """Close the browser and clean up all session data.

        Clears cookies, deletes session storage, and removes the
        temporary profile directory.  Safe to call even if the
        browser was never launched.

        Raises:
            BrowserError: If cleanup encounters an unexpected error.
        """
        try:
            if self._driver is not None:
                try:
                    await self._run_sync(
                        partial(
                            self._driver.delete_all_cookies,
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("Could not delete cookies")

                try:
                    await self._run_sync(
                        partial(
                            self._driver.execute_script,
                            "sessionStorage.clear();",
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Could not clear sessionStorage"
                    )

                try:
                    await self._run_sync(
                        partial(
                            self._driver.execute_script,
                            "localStorage.clear();",
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Could not clear localStorage"
                    )

                await self._run_sync(
                    partial(self._driver.quit),
                )
                self._driver = None

            if self._temp_profile_dir is not None:
                shutil.rmtree(
                    self._temp_profile_dir,
                    ignore_errors=True,
                )
                logger.info(
                    "Deleted temp profile: %s",
                    self._temp_profile_dir,
                )
                self._temp_profile_dir = None
        except Exception as exc:
            raise BrowserError(
                f"Error during browser cleanup: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> None:
        """Navigate to the given URL.

        Args:
            url: Target URL to navigate to.

        Raises:
            BrowserError: If navigation fails.
        """
        driver = self._require_driver()
        url = self._normalize_url(url)
        try:
            await self._run_sync(partial(driver.get, url))
            logger.info("Navigated to %s", url)
        except Exception as exc:
            raise BrowserError(
                f"Navigation to {url} failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    async def click(
        self, selector: str, strategy: str = "css",
    ) -> None:
        """Click on an element identified by *selector*.

        Args:
            selector: Element selector value.
            strategy: Selector strategy (``css``, ``xpath``,
                ``text``).

        Raises:
            BrowserError: If the element cannot be found or clicked.
        """
        driver = self._require_driver()
        by, value = self._resolve_locator(selector, strategy)
        try:
            element: WebElement = await self._run_sync(
                partial(driver.find_element, by, value),
            )
            await self._run_sync(partial(element.click))
        except Exception as exc:
            raise BrowserError(
                f"Click failed for '{value}': {exc}"
            ) from exc

    async def type_text(
        self, selector: str, text: str, strategy: str = "css",
    ) -> None:
        """Type *text* into an element identified by *selector*.

        Args:
            selector: Element selector value.
            text: Text to type into the element.
            strategy: Selector strategy (``css``, ``xpath``,
                ``text``).

        Raises:
            BrowserError: If the element cannot be found or typed
                into.
        """
        driver = self._require_driver()
        by, value = self._resolve_locator(selector, strategy)
        try:
            element: WebElement = await self._run_sync(
                partial(driver.find_element, by, value),
            )
            await self._run_sync(partial(element.clear))
            await self._run_sync(
                partial(element.send_keys, text),
            )
        except Exception as exc:
            raise BrowserError(
                f"Type failed for '{value}': {exc}"
            ) from exc

    async def extract_text(
        self, selector: str, strategy: str = "css",
    ) -> str:
        """Extract text content from an element.

        Args:
            selector: Element selector value.
            strategy: Selector strategy (``css``, ``xpath``,
                ``text``).

        Returns:
            Text content of the matched element.

        Raises:
            BrowserError: If the element cannot be found.
        """
        driver = self._require_driver()
        by, value = self._resolve_locator(selector, strategy)
        try:
            element: WebElement = await self._run_sync(
                partial(driver.find_element, by, value),
            )
            result: str = element.text
            return result or ""
        except Exception as exc:
            raise BrowserError(
                f"Extract text failed for '{value}': {exc}"
            ) from exc

    async def extract_table(
        self, selector: str, strategy: str = "css",
    ) -> list[list[str]]:
        """Extract tabular data from an HTML table element.

        Locates the table matching the given selector and returns its
        contents as a list of rows, where each row is a list of cell
        text strings.  Both ``<th>`` and ``<td>`` cells are included,
        and whitespace is stripped from every cell value.

        Uses ``driver.execute_script()`` with JavaScript that handles
        css, xpath, and text selector strategies.

        Args:
            selector: Selector pointing to the target table element.
            strategy: Selector strategy (``css``, ``xpath``,
                ``text``).

        Returns:
            List of rows, each row a list of stripped cell text
            values.  Returns an empty list when the table contains
            no rows.

        Raises:
            BrowserError: If no table element matches the selector.
        """
        driver = self._require_driver()

        js_extract = """
        var selector = arguments[0];
        var strategy = arguments[1];
        var table;
        if (strategy === 'xpath') {
            var result = document.evaluate(
                selector, document, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null
            );
            table = result.singleNodeValue;
        } else if (strategy === 'text') {
            var xpath = "//*[contains(text(),'" + selector + "')]";
            var result = document.evaluate(
                xpath, document, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null
            );
            table = result.singleNodeValue;
        } else {
            table = document.querySelector(selector);
        }
        if (!table) return null;
        var rows = table.querySelectorAll('tr');
        return Array.from(rows).map(function(row) {
            var cells = row.querySelectorAll('th, td');
            return Array.from(cells).map(function(cell) {
                return cell.textContent.trim();
            });
        });
        """
        try:
            result = await self._run_sync(
                partial(
                    driver.execute_script,
                    js_extract,
                    selector,
                    strategy,
                ),
            )
        except Exception as exc:
            raise BrowserError(
                f"Extract table failed for '{selector}': {exc}"
            ) from exc

        if result is None:
            raise BrowserError(
                f"Table not found for selector: '{selector}'"
            )

        return result

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    async def screenshot(self) -> bytes:
        """Capture a full-page screenshot (in memory only).

        Returns:
            PNG screenshot as bytes.

        Raises:
            BrowserError: If the screenshot cannot be taken.
        """
        driver = self._require_driver()
        try:
            png: bytes = await self._run_sync(
                partial(driver.get_screenshot_as_png),
            )
            return png
        except Exception as exc:
            raise BrowserError(
                f"Screenshot failed: {exc}"
            ) from exc

    async def get_page_context(self) -> PageContext:
        """Retrieve the current page context for AI analysis.

        Extracts up to 50 visible interactable elements and up to
        30 content snippets (headings, articles) using
        ``driver.execute_script()``.

        Returns:
            PageContext with URL, title, DOM summary, visible
            elements, and content snippets.

        Raises:
            BrowserError: If page context extraction fails.
        """
        driver = self._require_driver()
        try:
            url: str = driver.current_url
            title: str = driver.title
            elements: list[dict] = await self._run_sync(
                partial(
                    driver.execute_script,
                    _EXTRACT_ELEMENTS_JS,
                ),
            )
            try:
                content: list[dict] = await self._run_sync(
                    partial(
                        driver.execute_script,
                        _EXTRACT_CONTENT_JS,
                    ),
                )
            except Exception as exc:
                logger.debug(
                    "Content extraction failed: %s", exc,
                )
                content = []
            dom_summary = _build_dom_summary(elements)
            return PageContext(
                url=url,
                title=title,
                dom_summary=dom_summary,
                visible_elements=elements,
                content_snippets=content,
            )
        except Exception as exc:
            raise BrowserError(
                f"Failed to extract page context: {exc}"
            ) from exc


__all__ = [
    "SeleniumEngine",
]
