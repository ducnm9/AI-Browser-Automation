"""Browser engine interface and page context data class.

Defines the abstract strategy interface ``BrowserEngine`` that all
concrete browser engines (Playwright, Selenium) must implement,
along with the ``PageContext`` data class representing the current
state of a web page.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PageContext:
    """Snapshot of the current web page state for AI analysis.

    Args:
        url: The current page URL.
        title: The page title.
        dom_summary: Simplified DOM tree for LLM consumption.
        visible_elements: List of visible interactable elements.
        content_snippets: Text snippets from content elements
            (headings, articles, paragraphs) for data extraction.
        screenshot: Optional screenshot bytes of the page.
    """

    url: str
    title: str
    dom_summary: str
    visible_elements: list[dict] = field(default_factory=list)
    content_snippets: list[dict] = field(default_factory=list)
    screenshot: Optional[bytes] = None


class BrowserEngine(ABC):
    """Abstract strategy interface for browser engines.

    All concrete engines (Playwright, Selenium) must implement every
    method to provide a unified API for browser automation.
    """

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure the URL has a valid scheme prefix.

        If the URL lacks a scheme (e.g. ``"google.com"``),
        ``https://`` is prepended automatically.

        Args:
            url: Raw URL string, possibly without a scheme.

        Returns:
            URL with a valid scheme prefix.
        """
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return f"https://{url}"
        return url

    @abstractmethod
    async def launch(self, headless: bool = False) -> None:
        """Launch the browser instance.

        Args:
            headless: Run in headless mode when True.
        """
        ...

    @abstractmethod
    async def navigate(self, url: str) -> None:
        """Navigate to the given URL.

        Args:
            url: Target URL to navigate to.
        """
        ...

    @abstractmethod
    async def click(
        self, selector: str, strategy: str = "css",
    ) -> None:
        """Click on an element identified by selector.

        Args:
            selector: Element selector value.
            strategy: Selector strategy (css, xpath, text).
        """
        ...

    @abstractmethod
    async def type_text(
        self, selector: str, text: str, strategy: str = "css",
    ) -> None:
        """Type text into an element identified by selector.

        Args:
            selector: Element selector value.
            text: Text to type into the element.
            strategy: Selector strategy (css, xpath, text).
        """
        ...

    @abstractmethod
    async def extract_text(
        self, selector: str, strategy: str = "css",
    ) -> str:
        """Extract text content from an element.

        Args:
            selector: Element selector value.
            strategy: Selector strategy (css, xpath, text).

        Returns:
            Text content of the matched element.
        """
        ...

    @abstractmethod
    async def screenshot(self) -> bytes:
        """Capture a screenshot of the current page.

        Returns:
            Screenshot image as bytes.
        """
        ...

    @abstractmethod
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
            strategy: Selector strategy (css, xpath, text).

        Returns:
            List of rows, each row a list of stripped cell text values.
            Returns an empty list when the table contains no rows.

        Raises:
            BrowserError: If no table element matches the selector.
        """
        ...

    @abstractmethod
    async def get_page_context(self) -> PageContext:
        """Retrieve the current page context for AI analysis.

        Returns:
            PageContext with URL, title, DOM summary, and
            visible elements.
        """
        ...

    @abstractmethod
    async def extract_page_text(
        self, max_length: int = 8000,
    ) -> str:
        """Extract readable text content from the current page.

        Strips navigation, scripts, styles, and ads to return
        only the main content text, suitable for LLM analysis.

        Args:
            max_length: Maximum character length of the output.

        Returns:
            Cleaned text content from the page body.

        Raises:
            BrowserError: If text extraction fails.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the browser and clean up resources."""
        ...


__all__ = [
    "BrowserEngine",
    "PageContext",
]
