"""Playwright-based browser engine implementation.

Provides ``PlaywrightEngine``, a concrete ``BrowserEngine`` that uses
Playwright's async API for browser automation.  Each session runs in an
isolated temporary profile directory that is deleted on ``close()``.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from ai_browser_automation.browser.base import BrowserEngine, PageContext
from ai_browser_automation.exceptions.errors import BrowserError

logger = logging.getLogger(__name__)

_MAX_VISIBLE_ELEMENTS = 50
_TEXT_TRUNCATE_LENGTH = 100
_MAX_CONTENT_SNIPPETS = 30
_CONTENT_TEXT_LENGTH = 200

# JavaScript snippet executed via page.evaluate() to extract visible
# interactable elements from the current page DOM.
_EXTRACT_ELEMENTS_JS = """
() => {
    const sel = 'a, button, input, select, textarea, '
              + '[role="button"], [onclick]';
    const interactable = document.querySelectorAll(sel);
    return Array.from(interactable).slice(0, %d).map(el => ({
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || "").trim().substring(0, %d),
        type: el.getAttribute("type"),
        placeholder: el.getAttribute("placeholder"),
        aria_label: el.getAttribute("aria-label"),
        href: el.getAttribute("href"),
        id: el.id || null,
        name: el.getAttribute("name"),
        visible: el.offsetParent !== null
    })).filter(el => el.visible);
}
""" % (_MAX_VISIBLE_ELEMENTS, _TEXT_TRUNCATE_LENGTH)

# JavaScript snippet to extract content elements (headings,
# articles, paragraphs) for data-extraction planning.
_EXTRACT_CONTENT_JS = """
() => {
    const sel = 'h1, h2, h3, h4, article, .article, '
              + '[class*="title"], [class*="headline"], '
              + '.item-news, .title-news';
    const nodes = document.querySelectorAll(sel);
    return Array.from(nodes).slice(0, %d).map(el => {
        const link = el.querySelector('a');
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
    }).filter(el => el.text.length > 0);
}
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



class PlaywrightEngine(BrowserEngine):
    """Browser engine backed by Playwright's async API.

    Each ``launch()`` creates a temporary profile directory for browser
    isolation.  ``close()`` clears cookies, session storage, and removes
    the temporary directory so that no data persists between sessions.

    Args:
        browser_type: Chromium variant to use (``"chromium"``,
            ``"firefox"``, or ``"webkit"``).
    """

    def __init__(self, browser_type: str = "chromium") -> None:
        self._browser_type = browser_type
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._temp_profile_dir: Optional[Path] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def launch(self, headless: bool = False) -> None:
        """Launch a browser instance with an isolated profile.

        Args:
            headless: Run in headless mode when ``True``.

        Raises:
            BrowserError: If Playwright fails to start or launch.
        """
        try:
            self._temp_profile_dir = Path(
                tempfile.mkdtemp(prefix="ai_browser_"),
            )
            self._playwright = await async_playwright().start()

            launcher = getattr(
                self._playwright, self._browser_type, None,
            )
            if launcher is None:
                raise BrowserError(
                    f"Unsupported browser type: {self._browser_type}"
                )

            self._browser = await launcher.launch(headless=headless)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
            logger.info(
                "Browser launched (type=%s, headless=%s)",
                self._browser_type,
                headless,
            )
        except BrowserError:
            raise
        except Exception as exc:
            raise BrowserError(
                f"Failed to launch browser: {exc}"
            ) from exc

    async def close(self) -> None:
        """Close the browser and clean up all session data.

        Clears cookies, session storage, and deletes the temporary
        profile directory.  Safe to call even if the browser was never
        launched.

        Raises:
            BrowserError: If cleanup encounters an unexpected error.
        """
        try:
            if self._context is not None:
                await self._context.clear_cookies()
                # Clear session storage on every open page.
                if self._page is not None and not self._page.is_closed():
                    try:
                        await self._page.evaluate(
                            "() => sessionStorage.clear()"
                        )
                    except Exception:  # noqa: BLE001
                        logger.debug(
                            "Could not clear sessionStorage "
                            "(page may have navigated away)"
                        )
                await self._context.close()
                self._context = None
                self._page = None

            if self._browser is not None:
                await self._browser.close()
                self._browser = None

            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None

            if self._temp_profile_dir is not None:
                shutil.rmtree(
                    self._temp_profile_dir, ignore_errors=True,
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
        page = self._require_page()
        url = self._normalize_url(url)
        try:
            await page.goto(url, wait_until="domcontentloaded")
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
            strategy: Selector strategy (``css``, ``xpath``, ``text``).

        Raises:
            BrowserError: If the element cannot be found or clicked.
        """
        page = self._require_page()
        resolved = self._resolve_selector(selector, strategy)
        try:
            await page.click(resolved)
        except Exception as exc:
            raise BrowserError(
                f"Click failed for '{resolved}': {exc}"
            ) from exc

    async def type_text(
        self, selector: str, text: str, strategy: str = "css",
    ) -> None:
        """Type *text* into an element identified by *selector*.

        Args:
            selector: Element selector value.
            text: Text to type into the element.
            strategy: Selector strategy (``css``, ``xpath``, ``text``).

        Raises:
            BrowserError: If the element cannot be found or typed into.
        """
        page = self._require_page()
        resolved = self._resolve_selector(selector, strategy)
        try:
            await page.fill(resolved, text)
        except Exception as exc:
            raise BrowserError(
                f"Type failed for '{resolved}': {exc}"
            ) from exc

    async def extract_text(
        self, selector: str, strategy: str = "css",
    ) -> str:
        """Extract text content from an element.

        Args:
            selector: Element selector value.
            strategy: Selector strategy (``css``, ``xpath``, ``text``).

        Returns:
            Text content of the matched element.

        Raises:
            BrowserError: If the element cannot be found.
        """
        page = self._require_page()
        resolved = self._resolve_selector(selector, strategy)
        try:
            locator = page.locator(resolved).first
            return await locator.inner_text() or ""
        except Exception as exc:
            raise BrowserError(
                f"Extract text failed for '{resolved}': {exc}"
            ) from exc

    async def extract_table(
        self, selector: str, strategy: str = "css",
    ) -> list[list[str]]:
        """Extract tabular data from an HTML table element.

        Locates the table matching the given selector and returns its
        contents as a list of rows, where each row is a list of cell
        text strings.  Both ``<th>`` and ``<td>`` cells are included,
        and whitespace is stripped from every cell value.

        Args:
            selector: Selector pointing to the target table element.
            strategy: Selector strategy (``css``, ``xpath``, ``text``).

        Returns:
            List of rows, each row a list of stripped cell text values.
            Returns an empty list when the table contains no rows.

        Raises:
            BrowserError: If no table element matches the selector.
        """
        page = self._require_page()
        resolved = self._resolve_selector(selector, strategy)

        js_extract = """
        (selector) => {
            const table = document.querySelector(selector);
            if (!table) return null;
            const rows = table.querySelectorAll('tr');
            return Array.from(rows).map(row => {
                const cells = row.querySelectorAll('th, td');
                return Array.from(cells).map(
                    cell => cell.textContent.trim()
                );
            });
        }
        """
        try:
            result = await page.evaluate(js_extract, resolved)
        except Exception as exc:
            raise BrowserError(
                f"Extract table failed for '{resolved}': {exc}"
            ) from exc

        if result is None:
            raise BrowserError(
                f"Table not found for selector: '{resolved}'"
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
        page = self._require_page()
        try:
            return await page.screenshot(full_page=True)
        except Exception as exc:
            raise BrowserError(
                f"Screenshot failed: {exc}"
            ) from exc

    async def get_page_context(self) -> PageContext:
        """Retrieve the current page context for AI analysis.

        Extracts up to 50 visible interactable elements and up to
        30 content snippets (headings, articles) using
        ``page.evaluate()``.

        Returns:
            PageContext with URL, title, DOM summary, visible
            elements, and content snippets.

        Raises:
            BrowserError: If page context extraction fails.
        """
        page = self._require_page()
        try:
            url: str = page.url
            title: str = await page.title()
            elements: list[dict] = await page.evaluate(
                _EXTRACT_ELEMENTS_JS,
            )
            try:
                content: list[dict] = await page.evaluate(
                    _EXTRACT_CONTENT_JS,
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_page(self) -> Page:
        """Return the active page or raise ``BrowserError``.

        Raises:
            BrowserError: If the browser has not been launched.
        """
        if self._page is None:
            raise BrowserError(
                "Browser not launched. Call launch() first."
            )
        return self._page

    @staticmethod
    def _resolve_selector(
        selector: str, strategy: str,
    ) -> str:
        """Convert a *(selector, strategy)* pair into a Playwright locator.

        Args:
            selector: Raw selector value.
            strategy: One of ``css``, ``xpath``, or ``text``.

        Returns:
            Playwright-compatible selector string.
        """
        if strategy == "xpath":
            return f"xpath={selector}"
        if strategy == "text":
            return f"text={selector}"
        return selector  # css is the default


__all__ = [
    "PlaywrightEngine",
]
