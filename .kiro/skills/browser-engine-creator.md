# Skill: Thêm Browser Engine Mới

Khi cần thêm browser engine mới (ví dụ: Puppeteer via pyppeteer, CDP direct...), tuân thủ quy trình sau:

## Bước 1: Tạo Engine Class

Tạo file `ai_browser_automation/browser/<engine_name>_engine.py`:

```python
"""<Engine Name> browser engine implementation."""
from __future__ import annotations

import logging
from typing import Optional

from ai_browser_automation.browser.base import BrowserEngine, PageContext

logger = logging.getLogger(__name__)

__all__ = ["<EngineName>Engine"]


class <EngineName>Engine(BrowserEngine):
    """<Engine Name> browser engine.

    Args:
        config: Browser configuration settings.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._browser = None
        self._page = None

    async def launch(self, headless: bool = False) -> None: ...
    async def navigate(self, url: str) -> None: ...
    async def click(self, selector: str, strategy: str = "css") -> None: ...
    async def type_text(self, selector: str, text: str, strategy: str = "css") -> None: ...
    async def extract_text(self, selector: str, strategy: str = "css") -> str: ...
    async def screenshot(self) -> bytes: ...
    async def get_page_context(self) -> PageContext: ...
    async def close(self) -> None: ...
```

## Bước 2: Đăng Ký Trong Factory

Cập nhật `ai_browser_automation/browser/factory.py`.

## Bước 3: Viết Tests

Tạo test trong `tests/unit/browser/test_<engine_name>_engine.py`:
- `test_launch_and_close`
- `test_navigate`
- `test_click_element`
- `test_type_text`
- `test_extract_text`
- `test_screenshot`
- `test_get_page_context`

## Checklist

- [ ] Engine class implement `BrowserEngine` ABC (tất cả abstract methods)
- [ ] Đăng ký trong Factory
- [ ] Unit tests cho mỗi method
- [ ] Cập nhật `__init__.py`
- [ ] Cập nhật `pyproject.toml` nếu cần dependency mới
