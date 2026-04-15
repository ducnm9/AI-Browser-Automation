---
inclusion: auto
---

# Design Patterns — AI Browser Automation

Dự án tuân thủ các design patterns sau để đảm bảo code dễ đọc, dễ mở rộng, và dễ test.

## 1. Strategy Pattern

Dùng cho các thành phần có nhiều implementation thay thế nhau.

**Áp dụng:**
- `BaseLLMProvider` (ABC) → `OpenAIProvider`, `GeminiProvider`, `BedrockProvider`, `LMStudioProvider`
- `BrowserEngine` (ABC) → `PlaywrightEngine`, `SeleniumEngine`

**Quy tắc:**
- Mỗi strategy implement cùng một abstract interface
- Không hardcode implementation cụ thể — luôn reference qua interface
- Thêm provider/engine mới chỉ cần tạo class mới implement ABC, không sửa code hiện tại

```python
# Đúng: reference qua interface
def __init__(self, browser: BrowserEngine): ...

# Sai: hardcode implementation
def __init__(self):
    self.browser = PlaywrightEngine()
```

## 2. Chain of Responsibility

Dùng cho xử lý tuần tự qua nhiều handler cho đến khi có handler xử lý được.

**Áp dụng:**
- `LLMRouter.route()`: request đi qua fallback chain các provider
- Error recovery: retry → replan → report

**Quy tắc:**
- Mỗi handler trong chain phải độc lập, không phụ thuộc handler khác
- Chain phải có điểm dừng rõ ràng (raise exception khi hết handler)

## 3. Command Pattern

Mỗi browser action là một command object có thể serialize và queue.

**Áp dụng:**
- `ActionStep` là command object
- `ExecutionPlan` là danh sách commands

**Quy tắc:**
- Command objects phải immutable (dùng `@dataclass(frozen=True)` hoặc `@dataclass`)
- Mỗi command chứa đủ thông tin để tự thực thi (selector, strategy, timeout)

## 4. Factory Pattern

Tạo đúng instance dựa trên config, tránh if/else chain.

**Áp dụng:**
- `LLMProviderFactory.create()` → tạo provider từ `LLMProvider` enum
- `BrowserEngineFactory.create()` → tạo engine từ config string

**Quy tắc:**
- Factory method trả về interface type, không trả về concrete type
- Registry pattern: đăng ký creator functions thay vì if/else

```python
class LLMProviderFactory:
    _registry: dict[LLMProvider, type[BaseLLMProvider]] = {}

    @classmethod
    def register(cls, provider_type: LLMProvider, provider_class: type[BaseLLMProvider]) -> None:
        cls._registry[provider_type] = provider_class

    @classmethod
    def create(cls, provider_type: LLMProvider, config: AppConfig) -> BaseLLMProvider:
        if provider_type not in cls._registry:
            raise ValueError(f"Unknown provider: {provider_type}")
        return cls._registry[provider_type](config)
```

## 5. Observer Pattern

Các component phát events để logging, monitoring, UI update.

**Áp dụng:**
- Action execution events: `on_step_start`, `on_step_complete`, `on_step_failed`
- LLM routing events: `on_provider_selected`, `on_fallback`

**Quy tắc:**
- Observers không ảnh hưởng logic chính (fire-and-forget)
- Dùng Python `Protocol` hoặc callback functions, không dùng inheritance

## 6. Facade Pattern

Class chính ẩn toàn bộ complexity, expose API đơn giản.

**Áp dụng:**
- `AIBrowserAutomation` là facade: `chat()`, `initialize()`, `shutdown()`

**Quy tắc:**
- Facade không chứa business logic — chỉ orchestrate các components
- User code chỉ interact với facade, không trực tiếp với internal components

## 7. Dependency Injection

Components nhận dependencies qua constructor.

**Quy tắc bắt buộc:**
- KHÔNG tạo dependencies bên trong constructor
- KHÔNG import concrete class trong business logic — import interface
- Test dễ dàng bằng cách inject mock objects

```python
# Đúng: DI qua constructor
class ActionExecutor:
    def __init__(self, browser: BrowserEngine, llm_router: LLMRouter):
        self.browser = browser
        self.llm_router = llm_router

# Sai: tự tạo dependency
class ActionExecutor:
    def __init__(self):
        self.browser = PlaywrightEngine()
        self.llm_router = LLMRouter(AppConfig())
```

## Nguyên Tắc Chung

- **Single Responsibility**: Mỗi class/module chỉ có một lý do để thay đổi
- **Open/Closed**: Mở rộng bằng cách thêm class mới, không sửa class hiện tại
- **Interface Segregation**: Interface nhỏ, tập trung — không ép implement method không cần
- **Dependency Inversion**: Depend on abstractions (ABC), not concretions
