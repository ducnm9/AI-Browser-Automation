# Skill: Tạo Python Module Mới

Khi tạo một Python module mới trong dự án AI Browser Automation, tuân thủ template sau:

## Template Module

```python
"""<Mô tả ngắn module>.

<Mô tả chi tiết hơn nếu cần.>
"""
from __future__ import annotations

# Standard library imports
import logging
from typing import Optional

# Third-party imports (nếu cần)

# Local imports
from ai_browser_automation.exceptions.errors import AppError

logger = logging.getLogger(__name__)

__all__ = ["ClassName"]


class ClassName:
    """<Mô tả class>.

    Args:
        dependency: <Mô tả dependency>.
    """

    def __init__(self, dependency: DependencyInterface) -> None:
        self._dependency = dependency

    async def public_method(self, param: str) -> ReturnType:
        """<Mô tả method>.

        Args:
            param: <Mô tả param>.

        Returns:
            <Mô tả return>.

        Raises:
            SpecificError: <Khi nào raise>.
        """
        ...
```

## Checklist khi tạo module mới

1. `from __future__ import annotations` ở dòng đầu
2. Module docstring
3. Import theo thứ tự: stdlib → third-party → local
4. `logger = logging.getLogger(__name__)`
5. `__all__` explicit
6. Type hints đầy đủ cho tất cả public methods
7. Google-style docstrings cho public methods
8. Dependencies inject qua constructor
9. Cập nhật `__init__.py` của package cha
10. Tạo test file tương ứng trong `tests/`
