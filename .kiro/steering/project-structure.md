---
inclusion: auto
---

# Project Structure — AI Browser Automation

## Cấu Trúc Thư Mục

```
ai_browser_automation/
├── core/                        # Business logic chính
│   ├── __init__.py
│   ├── nl_processor.py          # Xử lý ngôn ngữ tự nhiên
│   ├── task_planner.py          # Lập kế hoạch thực thi
│   └── action_executor.py       # Thực thi hành động trên browser
├── llm/                         # LLM providers (Strategy Pattern)
│   ├── __init__.py
│   ├── base.py                  # BaseLLMProvider ABC + LLMRequest/Response
│   ├── router.py                # LLMRouter — điều phối provider
│   ├── factory.py               # LLMProviderFactory
│   ├── openai_provider.py
│   ├── gemini_provider.py
│   ├── bedrock_provider.py
│   └── lm_studio_provider.py
├── browser/                     # Browser engines (Strategy Pattern)
│   ├── __init__.py
│   ├── base.py                  # BrowserEngine ABC + PageContext
│   ├── factory.py               # BrowserEngineFactory
│   ├── playwright_engine.py
│   └── selenium_engine.py
├── security/                    # Bảo mật dữ liệu
│   ├── __init__.py
│   └── security_layer.py
├── models/                      # Data classes, enums, schemas
│   ├── __init__.py
│   ├── config.py                # AppConfig, SecurityPolicy
│   ├── intents.py               # IntentType, ParsedIntent
│   ├── actions.py               # ActionStep, ExecutionPlan, ActionResult
│   └── conversation.py          # ConversationTurn, ConversationHistory
├── exceptions/                  # Custom exceptions
│   ├── __init__.py
│   └── errors.py                # AppError hierarchy
├── interfaces/                  # User interfaces
│   ├── __init__.py
│   └── chat_interface.py        # CLI chat interface
├── app.py                       # AIBrowserAutomation facade
└── main.py                      # Entry point

tests/
├── conftest.py                  # Shared fixtures
├── unit/
│   ├── core/
│   │   ├── test_nl_processor.py
│   │   ├── test_task_planner.py
│   │   └── test_action_executor.py
│   ├── llm/
│   │   ├── test_router.py
│   │   └── test_providers.py
│   ├── browser/
│   │   └── test_engines.py
│   └── security/
│       └── test_security_layer.py
├── integration/
│   └── test_end_to_end.py
└── properties/                  # Property-based tests (hypothesis)
    ├── test_security_properties.py
    ├── test_routing_properties.py
    └── test_execution_properties.py

config.yaml                      # Default configuration
pyproject.toml                   # Project metadata & dependencies
README.md
```

## Quy Tắc Tổ Chức

- Mỗi thư mục con PHẢI có `__init__.py` với `__all__` explicit
- Mỗi module chỉ chứa 1 class chính (hoặc một nhóm data classes liên quan)
- Tests mirror cấu trúc source: `ai_browser_automation/llm/router.py` → `tests/unit/llm/test_router.py`
- Không tạo thư mục con nếu chỉ có 1 file — giữ flat khi có thể
- Config files ở root level, không lồng trong source

## Module Dependencies (Hướng phụ thuộc)

```
interfaces → app (facade) → core → llm, browser, security → models, exceptions
```

- `models/` và `exceptions/` không phụ thuộc module nào khác
- `core/` phụ thuộc `llm/`, `browser/`, `security/` qua interfaces (ABC)
- `app.py` orchestrate tất cả, là điểm vào duy nhất
- Không có circular dependencies
