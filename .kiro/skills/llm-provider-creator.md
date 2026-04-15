# Skill: Thêm LLM Provider Mới

Khi cần thêm một LLM provider mới (ví dụ: Anthropic, Cohere, Ollama...), tuân thủ quy trình sau:

## Bước 1: Tạo Provider Class

Tạo file `ai_browser_automation/llm/<provider_name>_provider.py`:

```python
"""<Provider Name> LLM provider implementation."""
from __future__ import annotations

import logging
from typing import Optional

from ai_browser_automation.llm.base import BaseLLMProvider, LLMRequest, LLMResponse, LLMProvider
from ai_browser_automation.models.config import AppConfig

logger = logging.getLogger(__name__)

__all__ = ["<ProviderName>Provider"]


class <ProviderName>Provider(BaseLLMProvider):
    """<Provider Name> LLM provider.

    Args:
        config: Application configuration chứa API key và settings.
    """

    def __init__(self, config: AppConfig) -> None:
        self._api_key = config.<provider>_api_key
        self._client = None  # Lazy initialization

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Gửi request đến <Provider Name> và nhận response."""
        ...

    async def health_check(self) -> bool:
        """Kiểm tra <Provider Name> có sẵn sàng không."""
        ...
```

## Bước 2: Đăng Ký Trong Factory

Cập nhật `ai_browser_automation/llm/factory.py`:

```python
LLMProviderFactory.register(LLMProvider.<PROVIDER_NAME>, <ProviderName>Provider)
```

## Bước 3: Cập Nhật Enum

Thêm giá trị mới vào `LLMProvider` enum trong `ai_browser_automation/llm/base.py`.

## Bước 4: Cập Nhật Config

Thêm config fields vào `AppConfig` trong `ai_browser_automation/models/config.py`.

## Bước 5: Viết Tests

Tạo test trong `tests/unit/llm/test_<provider_name>_provider.py`:
- `test_complete_success`
- `test_complete_api_error`
- `test_health_check_available`
- `test_health_check_unavailable`

## Bước 6: Cập Nhật Exports

Thêm vào `ai_browser_automation/llm/__init__.py` và `__all__`.

## Checklist

- [ ] Provider class implement `BaseLLMProvider` ABC
- [ ] Đăng ký trong Factory
- [ ] Enum value mới
- [ ] Config fields mới
- [ ] Unit tests
- [ ] Cập nhật `__init__.py`
- [ ] Cập nhật `pyproject.toml` nếu cần dependency mới
