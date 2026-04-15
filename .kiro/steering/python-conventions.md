---
inclusion: auto
---

# Python Coding Conventions — AI Browser Automation

## Naming Conventions

- Classes: `PascalCase` — `LLMRouter`, `ActionExecutor`, `PlaywrightEngine`
- Functions/methods: `snake_case` — `execute_plan()`, `detect_sensitive_data()`
- Constants: `UPPER_SNAKE_CASE` — `MAX_RETRIES`, `DEFAULT_TIMEOUT_MS`
- Private members: prefix `_` — `_validate_config()`, `_internal_state`
- Protected members: prefix `_` — `_process_internal()`
- Module files: `snake_case.py` — `llm_router.py`, `browser_engine.py`
- Test files: `test_<module>.py` — `test_llm_router.py`
- Enum values: `UPPER_SNAKE_CASE` — `LLMProvider.LM_STUDIO`

## Type Hints (Bắt buộc)

Tất cả function signatures PHẢI có type hints đầy đủ:

```python
# Good
async def execute_step(self, step: ActionStep) -> ActionResult: ...
def detect_sensitive_data(self, text: str) -> list[str]: ...

# Bad — thiếu type hints
async def execute_step(self, step): ...
def detect_sensitive_data(self, text): ...
```

Sử dụng `Optional[T]` thay vì `T | None` cho Python 3.9 compatibility.
Sử dụng `from __future__ import annotations` ở đầu mỗi file.

## Docstrings (Google Style)

```python
async def route(self, request: LLMRequest) -> LLMResponse:
    """Điều phối request đến LLM provider phù hợp.

    Args:
        request: LLM request chứa prompt và metadata.

    Returns:
        LLMResponse với content từ provider đã xử lý.

    Raises:
        LLMUnavailableError: Khi tất cả provider đều lỗi.
    """
```

## Import Order

1. Standard library
2. Third-party packages
3. Local application imports

Mỗi nhóm cách nhau 1 dòng trống. Không dùng wildcard imports (`from x import *`).

```python
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page
from pydantic import BaseModel

from ai_browser_automation.models.config import AppConfig
from ai_browser_automation.security.security_layer import SecurityLayer
```

## Error Handling

- Custom exceptions kế thừa từ `AppError`
- KHÔNG dùng bare `except:` — luôn specify exception type
- Logging thay vì `print()`
- Mỗi module có exception riêng

```python
# Good
try:
    response = await provider.complete(request)
except ConnectionError as e:
    logger.error("Provider %s connection failed: %s", provider_type, e)
    raise LLMUnavailableError(f"Connection failed: {e}") from e

# Bad
try:
    response = await provider.complete(request)
except:
    print("Error!")
```

## Async/Await

- Tất cả I/O operations PHẢI dùng `async/await`
- Không dùng `asyncio.run()` bên trong async context
- Sử dụng `asyncio.gather()` cho parallel operations khi các bước độc lập

## Data Classes

- Dùng `@dataclass` cho internal data objects đơn giản
- Dùng `pydantic.BaseModel` cho objects cần validation (config, API input/output)
- Dùng `field(default_factory=...)` cho mutable defaults

## Module Exports

Mỗi `__init__.py` PHẢI có `__all__` explicit:

```python
# ai_browser_automation/llm/__init__.py
__all__ = ["LLMRouter", "BaseLLMProvider", "LLMProvider", "LLMRequest", "LLMResponse"]
```

## Code Style

- Max line length: 100 characters
- Trailing commas trong multi-line collections
- f-strings cho string formatting (không dùng `.format()` hoặc `%`)
- Sử dụng `pathlib.Path` thay vì `os.path`

## Logging

Sử dụng `structlog` hoặc standard `logging` với format thống nhất:

```python
import logging

logger = logging.getLogger(__name__)

# Levels:
# DEBUG: Chi tiết internal (selector found, DOM parsed)
# INFO: Hành động chính (action executed, provider selected)
# WARNING: Fallback, retry
# ERROR: Lỗi cần xử lý
# CRITICAL: Lỗi không khắc phục được
```

## Testing Conventions

- Test file đặt cùng cấu trúc thư mục với source: `tests/unit/llm/test_router.py`
- Test function: `test_<method>_<scenario>` — `test_route_sensitive_data_uses_local()`
- Fixtures dùng `@pytest.fixture`
- Property-based tests dùng `hypothesis` với `@given` decorator
- Mock external dependencies, không mock internal logic
