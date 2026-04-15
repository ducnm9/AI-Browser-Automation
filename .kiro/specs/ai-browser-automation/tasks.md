# Implementation Plan: AI Browser Automation

## Overview

Implement an AI-powered browser automation tool that lets users control web browsers via natural language (Vietnamese/English). The system uses a modular architecture with Strategy, Factory, DI, Chain of Responsibility, Command, Observer, and Facade patterns. All components follow the project structure in `.kiro/steering/project-structure.md`, coding conventions in `.kiro/steering/python-conventions.md`, design patterns in `.kiro/steering/design-patterns.md`, and security rules in `.kiro/steering/security-rules.md`.

Implementation language: Python (async/await throughout). All files must use `from __future__ import annotations`, type hints on all signatures, Google-style docstrings, explicit `__all__` in `__init__.py`, DI via constructor, and custom exceptions inheriting from `AppError`.

## Tasks

- [x] 1. Set up project foundation: exceptions, data models, and config validation
  - [x] 1.1 Create exception hierarchy in `ai_browser_automation/exceptions/errors.py`
    - Define `AppError(Exception)` base and subclasses: `LLMUnavailableError`, `BrowserError`, `NLProcessingError`, `SecurityError`, `ConfigValidationError`, `ActionExecutionError`, `PlanningError`
    - Create `ai_browser_automation/exceptions/__init__.py` with explicit `__all__`
    - _Requirements: 4.3, 3.4_

  - [x] 1.2 Create data models in `ai_browser_automation/models/`
    - `models/intents.py`: `IntentType` enum (NAVIGATE, CLICK, TYPE_TEXT, EXTRACT_DATA, LOGIN, SCROLL, WAIT, SCREENSHOT, COMPOSITE), `ParsedIntent` dataclass with `intent_type`, `target_description`, `parameters`, `confidence`, `sub_intents`
    - `models/actions.py`: `ActionStep` dataclass (action_type, selector_strategy, selector_value, input_value, wait_condition, timeout_ms, retry_count), `ExecutionPlan` dataclass, `ActionResult` dataclass (success, step, extracted_data, screenshot, error_message, duration_ms)
    - `models/conversation.py`: `ConversationTurn` dataclass with validation (role must be "user" or "assistant", content must be non-empty), `ConversationHistory` with `add_turn()` that auto-trims oldest turns when exceeding `max_context_turns`, `get_context_window()` returns at most `max_context_turns` turns
    - `models/config.py`: `LLMProvider` enum, `SecurityPolicy` dataclass with `sensitive_patterns: list[str]`, `AppConfig` as pydantic `BaseModel` with validators — `openai_api_key` starts with "sk-" or is None, `lm_studio_url` is valid URL, `action_timeout_ms` in (0, 60000], `max_retries` in [0, 10], `default_llm` defaults to `LLMProvider.LM_STUDIO`
    - Create `ai_browser_automation/models/__init__.py` with explicit `__all__`
    - _Requirements: 1.1, 2.1, 3.1, 3.6, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 1.3 Write property tests for config validation
    - **Property 15: Configuration Validation**
    - Use hypothesis to generate: api keys (valid "sk-..." and invalid), URLs, timeout values, retry values
    - Assert invalid values are rejected by pydantic validators
    - File: `tests/properties/test_config_properties.py`
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

  - [x] 1.4 Write property tests for conversation history
    - **Property 13: Conversation History Bounded**
    - Use hypothesis to generate arbitrary numbers of turns and verify `get_context_window()` never exceeds `max_context_turns`
    - **Property 14: Conversation Turn Validation**
    - Use hypothesis to generate role strings and content strings; only "user"/"assistant" with non-empty content accepted
    - File: `tests/properties/test_conversation_properties.py`
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [x] 1.5 Write unit tests for models
    - Test `ConversationHistory.add_turn()` trimming, `ActionResult` defaults, `ExecutionPlan` construction, `ParsedIntent` with sub_intents
    - File: `tests/unit/test_models.py`
    - _Requirements: 3.1, 3.6, 7.1, 7.2_

- [x] 2. Implement Security Layer
  - [x] 2.1 Implement `ai_browser_automation/security/security_layer.py`
    - `SecurityLayer.__init__(self, policy: SecurityPolicy)` — DI via constructor
    - `detect_sensitive_data(self, text: str) -> list[str]` — builtin patterns (email, VN phone, credit card, CMND/CCCD, password fields) + custom patterns from policy; empty text returns empty list
    - `sanitize_for_cloud(self, text: str) -> tuple[str, dict[str, str]]` — replace sensitive data with `<<REDACTED_N>>` placeholders, return mapping
    - `restore_sensitive_data(self, text: str, mapping: dict[str, str]) -> str` — restore original text from mapping; `restore(sanitize(text)) == text`
    - `should_use_local_llm(self, text: str) -> bool` — returns True if sensitive data detected and `policy.force_local_on_sensitive`
    - `mask_for_log(self, text: str) -> str` — mask sensitive data for logging
    - Create `ai_browser_automation/security/__init__.py` with explicit `__all__`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 2.2 Write property test: Sensitive Data Detection Completeness
    - **Property 9: Sensitive Data Detection Completeness**
    - Use hypothesis to generate texts with embedded emails, VN phone numbers, credit card numbers, CMND/CCCD numbers, password fields
    - Assert all generated sensitive items are found in `detect_sensitive_data()` output
    - File: `tests/properties/test_security_properties.py`
    - **Validates: Requirement 5.1**

  - [x] 2.3 Write property test: Sanitization Removes All Sensitive Patterns
    - **Property 10: Sanitization Removes All Sensitive Patterns**
    - After `sanitize_for_cloud()`, run `detect_sensitive_data()` on sanitized output and assert empty result
    - File: `tests/properties/test_security_properties.py`
    - **Validates: Requirement 5.2**

  - [x] 2.4 Write property test: Sanitize/Restore Round-Trip
    - **Property 11: Sanitize/Restore Round-Trip**
    - For any text with sensitive data, `restore_sensitive_data(*sanitize_for_cloud(text)) == text`
    - File: `tests/properties/test_security_properties.py`
    - **Validates: Requirement 5.3**

  - [x] 2.5 Write property test: Custom Sensitive Patterns
    - **Property 12: Custom Sensitive Patterns**
    - Add custom regex to `SecurityPolicy.sensitive_patterns`, generate matching text, verify detection includes both builtin and custom matches
    - File: `tests/properties/test_security_properties.py`
    - **Validates: Requirement 5.4**

  - [x] 2.6 Write unit tests for SecurityLayer
    - Test empty text returns empty list (Req 5.5), `mask_for_log()` masks all sensitive data, edge cases with overlapping patterns
    - File: `tests/unit/security/test_security_layer.py`
    - _Requirements: 5.1, 5.5, 5.6_

- [x] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement LLM layer: base provider, concrete providers, factory, and router
  - [x] 4.1 Implement LLM base in `ai_browser_automation/llm/base.py`
    - `BaseLLMProvider(ABC)` with abstract `complete(request: LLMRequest) -> LLMResponse` and `health_check() -> bool`
    - `LLMRequest` dataclass: prompt, context, max_tokens, temperature, is_sensitive
    - `LLMResponse` dataclass: content, provider_used, tokens_used, latency_ms
    - _Requirements: 4.1, 4.5_

  - [x] 4.2 Implement LLM providers
    - `llm/openai_provider.py`: `OpenAIProvider(BaseLLMProvider)` using `openai` async client
    - `llm/gemini_provider.py`: `GeminiProvider(BaseLLMProvider)` using `google-generativeai`
    - `llm/bedrock_provider.py`: `BedrockProvider(BaseLLMProvider)` using `boto3`
    - `llm/lm_studio_provider.py`: `LMStudioProvider(BaseLLMProvider)` using `httpx.AsyncClient` to local endpoint
    - Each receives config via constructor (DI), no hardcoded API keys
    - _Requirements: 4.1, 4.2, 4.5_

  - [x] 4.3 Implement `ai_browser_automation/llm/factory.py`
    - `LLMProviderFactory` with `_registry: dict[LLMProvider, type[BaseLLMProvider]]`
    - `register(provider_type, provider_class)` and `create(provider_type, config) -> BaseLLMProvider`
    - Returns interface type, not concrete type
    - _Requirements: 4.5_

  - [x] 4.4 Implement `ai_browser_automation/llm/router.py`
    - `LLMRouter.__init__(self, config: AppConfig)` — DI
    - `register_provider(provider_type: LLMProvider, provider: BaseLLMProvider)` — open for extension (Req 4.5)
    - `route(request: LLMRequest) -> LLMResponse`:
      - If `is_sensitive=True`: route only to `LM_STUDIO`, skip all cloud providers
      - Fallback chain: target → default → remaining registered providers
      - Each provider tried at most once (tracked via `tried_providers` set)
      - Raise `LLMUnavailableError` with list of tried providers when all fail
    - Create `ai_browser_automation/llm/__init__.py` with explicit `__all__`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 4.5 Write property test: Sensitive Data Routes to Local LLM
    - **Property 7: Sensitive Data Routes to Local LLM**
    - Use hypothesis to generate `LLMRequest` with `is_sensitive=True` and various provider configurations
    - Assert `response.provider_used == LLMProvider.LM_STUDIO` always; mock cloud providers to verify they are never called
    - File: `tests/properties/test_routing_properties.py`
    - **Validates: Requirements 4.1, 9.4**

  - [x] 4.6 Write property test: Fallback Exhaustion and Provider Uniqueness
    - **Property 8: Fallback Exhaustion and Provider Uniqueness**
    - Use hypothesis to generate sets of providers with varying availability
    - Assert each provider tried at most once, `LLMUnavailableError` raised when all fail, no duplicates
    - File: `tests/properties/test_routing_properties.py`
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [x] 4.7 Write unit tests for LLMRouter
    - Test `register_provider()` adds new provider without modifying existing code
    - Test fallback chain order, sensitive routing to local only, all-providers-down raises `LLMUnavailableError`
    - File: `tests/unit/llm/test_router.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 5. Implement Browser Engine layer
  - [x] 5.1 Implement browser base in `ai_browser_automation/browser/base.py`
    - `BrowserEngine(ABC)` with abstract methods: `launch(headless: bool)`, `navigate(url: str)`, `click(selector: str, strategy: str)`, `type_text(selector: str, text: str, strategy: str)`, `extract_text(selector: str, strategy: str) -> str`, `screenshot() -> bytes`, `get_page_context() -> PageContext`, `close()`
    - `PageContext` dataclass: url, title, dom_summary, visible_elements, screenshot
    - _Requirements: 6.1_

  - [x] 5.2 Implement `ai_browser_automation/browser/playwright_engine.py`
    - `PlaywrightEngine(BrowserEngine)` using `playwright.async_api`
    - `get_page_context()` extracts max 50 visible interactable elements (a, button, input, select, textarea, role="button", onclick)
    - `close()` cleans up cookies, session data, and temporary profile directory
    - Supports headless and headed modes via `launch(headless)` parameter
    - _Requirements: 6.1, 6.3, 6.4, 6.5_

  - [x] 5.3 Implement `ai_browser_automation/browser/selenium_engine.py`
    - `SeleniumEngine(BrowserEngine)` as fallback engine with same API contract
    - _Requirements: 6.1, 6.2_

  - [x] 5.4 Implement `ai_browser_automation/browser/factory.py`
    - `BrowserEngineFactory` — tries Playwright first, falls back to Selenium if unavailable
    - Create `ai_browser_automation/browser/__init__.py` with explicit `__all__`
    - _Requirements: 6.2_

  - [x] 5.5 Write unit tests for browser engines
    - Test unified API contract with mocked browser APIs
    - Test `BrowserEngineFactory` fallback from Playwright to Selenium
    - Test `get_page_context()` caps at 50 elements
    - Test `close()` cleanup of cookies/session/temp directory
    - File: `tests/unit/browser/test_engines.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement core processing: NL Processor, Task Planner, Action Executor
  - [x] 7.1 Implement `ai_browser_automation/core/nl_processor.py`
    - `NLProcessor.__init__(self, llm_router: LLMRouter, security: SecurityLayer)` — DI via constructor
    - `parse(user_input: str) -> list[ParsedIntent]`: returns non-empty list with confidence in [0.0, 1.0], handles composite intents with sub_intents
    - `clarify(user_input: str, ambiguities: list[str]) -> str`: generates clarification question
    - Rejects empty/whitespace-only input by raising `NLProcessingError`
    - Create `ai_browser_automation/core/__init__.py` with explicit `__all__`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 7.2 Write property test: NL Parse Output Invariants
    - **Property 1: NL Parse Output Invariants**
    - Use hypothesis to generate non-empty, non-whitespace strings
    - Assert `parse()` returns non-empty list, every intent has valid `IntentType`, confidence in [0.0, 1.0]
    - File: `tests/properties/test_execution_properties.py`
    - **Validates: Requirement 1.1**

  - [x] 7.3 Write property test: Low Confidence Triggers Clarification
    - **Property 2: Low Confidence Triggers Clarification**
    - Generate `ParsedIntent` lists with varying confidence values
    - Assert: any intent with confidence < 0.7 triggers clarification; all >= 0.7 proceeds to execution
    - File: `tests/properties/test_execution_properties.py`
    - **Validates: Requirement 1.3**

  - [x] 7.4 Write property test: Whitespace Input Rejection
    - **Property 3: Whitespace Input Rejection**
    - Use hypothesis to generate whitespace-only strings (spaces, tabs, newlines, empty)
    - Assert `parse()` raises `NLProcessingError`
    - File: `tests/properties/test_execution_properties.py`
    - **Validates: Requirement 1.4**

  - [x] 7.5 Implement `ai_browser_automation/core/task_planner.py`
    - `TaskPlanner.__init__(self, llm_router: LLMRouter)` — DI
    - `plan(intents: list[ParsedIntent], page_context: PageContext) -> ExecutionPlan`: creates plan with non-empty steps, each step has valid action_type, selector_strategy, selector_value, timeout_ms
    - `replan(failed_step: ActionStep, error: str, screenshot: bytes) -> list[ActionStep]`: alternative steps based on error analysis
    - Determines selector strategy (css, xpath, text, ai_vision) based on page context
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 7.6 Implement `ai_browser_automation/core/action_executor.py`
    - `ActionExecutor.__init__(self, browser_engine: BrowserEngine, llm_router: LLMRouter)` — DI
    - `execute_plan(plan: ExecutionPlan) -> list[ActionResult]`: sequential execution, `len(results) == len(steps executed)`, results in order
    - `execute_step(step: ActionStep) -> ActionResult`: single step execution, records `duration_ms >= 0`, extract actions populate `extracted_data`
    - `smart_retry(step: ActionStep, error: str) -> ActionResult`: AI-powered retry with alternative selectors, bounded by `step.retry_count`
    - On irrecoverable failure (retries + replan exhausted): stops execution, returns results up to failed step with detailed error
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 7.7 Write property test: Execution Plan Result Integrity
    - **Property 4: Execution Plan Result Integrity**
    - Use hypothesis to generate `ExecutionPlan` with N steps (all succeed)
    - Assert `len(results) == N`, `results[i].step == plan.steps[i]`, all `duration_ms >= 0`
    - File: `tests/properties/test_execution_properties.py`
    - **Validates: Requirements 3.1, 3.6**

  - [x] 7.8 Write property test: Retry Bounded by retry_count
    - **Property 5: Retry Bounded by retry_count**
    - Use hypothesis to generate steps with varying `retry_count` values
    - Mock failures and count retry attempts; assert count <= `retry_count`
    - File: `tests/properties/test_execution_properties.py`
    - **Validates: Requirement 3.2**

  - [x] 7.9 Write property test: Failure Stops Subsequent Execution
    - **Property 6: Failure Stops Subsequent Execution**
    - Use hypothesis to generate plans where step at index N fails irrecoverably
    - Assert no steps at index > N executed, `len(results) == N + 1`
    - File: `tests/properties/test_execution_properties.py`
    - **Validates: Requirement 3.4**

  - [x] 7.10 Write unit tests for core components
    - Test `NLProcessor.parse()` with Vietnamese and English commands, composite intents
    - Test `TaskPlanner.plan()` with different intent types and page contexts
    - Test `ActionExecutor` success, retry, replan, and failure-stops scenarios
    - Files: `tests/unit/core/test_nl_processor.py`, `tests/unit/core/test_task_planner.py`, `tests/unit/core/test_action_executor.py`
    - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 3.1, 3.2, 3.4_

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement facade, chat interface, entry point, and wire everything together
  - [x] 9.1 Implement `ai_browser_automation/app.py`
    - `AIBrowserAutomation.__init__(self, config: AppConfig)` — stores config, initializes component references
    - `initialize()`: creates SecurityLayer, LLMRouter, registers providers via Factory, creates BrowserEngine via Factory (Playwright → Selenium fallback), creates NLProcessor, TaskPlanner, ActionExecutor — all via DI
    - `chat(user_input: str) -> str`: full pipeline — security check → NL parse → confidence check (clarify if < 0.7) → get page context → plan → execute → format results → update ConversationHistory
    - `shutdown()`: closes browser, cleans up resources
    - Sensitive data auto-routes to local LLM before pipeline execution
    - On failure at any step: returns detailed error, ensures browser in stable state
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 1.3_

  - [x] 9.2 Implement `ai_browser_automation/interfaces/chat_interface.py`
    - CLI chat loop: reads user input, calls `app.chat()`, displays result
    - Handles graceful shutdown on Ctrl+C
    - Create `ai_browser_automation/interfaces/__init__.py` with explicit `__all__`
    - _Requirements: 9.1_

  - [x] 9.3 Implement `ai_browser_automation/main.py`
    - Entry point: loads config from `config.yaml` and/or environment variables
    - API keys from env vars (`OPENAI_API_KEY`, etc.) or encrypted config — never hardcoded
    - Initializes `AIBrowserAutomation` and starts `ChatInterface`
    - _Requirements: 5.7, 8.5_

  - [x] 9.4 Create default `config.yaml` at project root
    - Default `LM_STUDIO` as provider, `lm_studio_url: http://localhost:1234/v1`
    - `browser_engine: playwright`, `headless: false`
    - Placeholder comments for API keys (loaded from env vars)
    - _Requirements: 8.5_

  - [x] 9.5 Create all `__init__.py` files with explicit `__all__`
    - `ai_browser_automation/__init__.py` exporting `AIBrowserAutomation`
    - Verify every subpackage has `__init__.py` with `__all__`
    - _Requirements: project conventions_

  - [x] 9.6 Create `tests/conftest.py` with shared fixtures
    - Mock fixtures: `mock_browser_engine`, `mock_llm_provider`, `mock_llm_router`, `mock_security_layer`
    - `AppConfig` fixture with test defaults
    - `pytest-asyncio` configuration
    - _Requirements: testing conventions_

  - [x] 9.7 Write integration tests for main pipeline
    - Test full pipeline with mocked LLM and browser: command → parse → plan → execute → result
    - Test sensitive data pipeline auto-routes to local LLM
    - Test pipeline failure returns error message and browser remains stable
    - Test conversation history updated after each interaction
    - File: `tests/integration/test_end_to_end.py`
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 15 correctness properties from design.md using `hypothesis`
- Unit tests validate specific examples and edge cases
- All code must follow `.kiro/steering/python-conventions.md` (type hints, docstrings, imports, etc.)
- Project structure must follow `.kiro/steering/project-structure.md`
- Security rules must follow `.kiro/steering/security-rules.md` (no hardcoded keys, sanitize before cloud, no sensitive logging)
- Design patterns must follow `.kiro/steering/design-patterns.md` (Strategy, Factory, DI, Facade, etc.)
