# Requirements Document

## Introduction

Hệ thống AI Browser Automation hiện tại chạy pipeline một lần duy nhất (plan once → execute all), dẫn đến thất bại khi xử lý các prompt đa bước cần navigate trước rồi mới có DOM context thực tế. Feature này bổ sung pipeline thực thi lặp (Observe-Plan-Act loop) cho phép hệ thống re-plan sau mỗi action dựa trên page context thực tế, cùng với khả năng trích xuất dữ liệu bảng HTML và cải thiện wait strategy cho trang JS-heavy.

Thiết kế tuân thủ các design patterns hiện có: Dependency Injection qua constructor, Strategy Pattern cho BrowserEngine (ABC interface), Factory Pattern, và Facade Pattern cho AIBrowserAutomation. Custom exceptions kế thừa từ AppError. Sensitive data đi qua SecurityLayer trước khi log.

## Glossary

- **IterativeExecutor**: Component mới điều phối vòng lặp Observe-Plan-Act, nhận dependencies qua constructor injection.
- **TaskPlanner**: Component lập kế hoạch hành động, được mở rộng thêm method `plan_next_step()`.
- **BrowserEngine**: Abstract strategy interface (ABC) cho browser automation, được mở rộng thêm method `extract_table()`.
- **PlaywrightEngine**: Implementation cụ thể của BrowserEngine dùng Playwright async API.
- **ActionExecutor**: Component thực thi từng action step trên browser.
- **App_Facade**: `AIBrowserAutomation` class — facade điều phối toàn bộ pipeline.
- **PageContext**: Data class chứa snapshot trạng thái trang web hiện tại.
- **IterationRecord**: Data model lưu trữ kết quả một iteration (step, result, page_context_before).
- **NextStepResult**: Data model chứa step tiếp theo hoặc tín hiệu goal_reached từ LLM.
- **IterativeExecutionError**: Exception class kế thừa từ AppError cho lỗi không khắc phục được trong iterative loop.
- **ParsedIntent**: Structured representation của user intent từ NL Processor.
- **ActionStep**: Một browser action cụ thể cần thực thi.
- **ActionResult**: Kết quả thực thi một ActionStep.

## Requirements

### Requirement 1: Vòng lặp Observe-Plan-Act

**User Story:** As a user, I want the system to re-plan after each action based on real page context, so that multi-step tasks like "navigate to a site and extract data" succeed even when the initial page is blank.

#### Acceptance Criteria

1. WHEN the IterativeExecutor receives a goal and intents, THE IterativeExecutor SHALL execute an Observe-Plan-Act loop that observes page context, plans the next step, and executes the step in each iteration.
2. WHILE the IterativeExecutor is running, THE IterativeExecutor SHALL maintain a history list of IterationRecord objects where `len(history) == len(results)` at every point during execution.
3. WHEN the LLM signals `goal_reached=true` in a NextStepResult, THE IterativeExecutor SHALL stop the loop and return all collected ActionResult objects.
4. WHEN the iteration count reaches `max_iterations`, THE IterativeExecutor SHALL stop the loop and return all ActionResult objects collected so far.
5. WHEN a step execution fails during the loop, THE IterativeExecutor SHALL record the failure in history and continue the loop so the LLM can adjust the plan.
6. THE IterativeExecutor SHALL produce a results list with length less than or equal to `max_iterations`.

### Requirement 2: Plan Next Step

**User Story:** As a developer, I want the TaskPlanner to plan one step at a time with full history context, so that each action is based on the real current page state rather than guessing from the initial context.

#### Acceptance Criteria

1. WHEN `plan_next_step()` is called with a goal, page context, and history, THE TaskPlanner SHALL return a NextStepResult containing either the next ActionStep or a goal_reached signal.
2. WHEN the LLM response indicates `goal_reached=true`, THE TaskPlanner SHALL return a NextStepResult where `step` is None and `goal_reached` is True.
3. WHEN the LLM response indicates `goal_reached=false`, THE TaskPlanner SHALL return a NextStepResult where `step` is a valid ActionStep with a recognized `action_type`.
4. IF the LLM returns invalid JSON or missing fields in `plan_next_step()`, THEN THE TaskPlanner SHALL raise a PlanningError.

### Requirement 3: Extract Table Data

**User Story:** As a user, I want the system to extract HTML table data as structured rows, so that I can retrieve tabular information like sports schedules or rankings.

#### Acceptance Criteria

1. WHEN `extract_table()` is called with a valid selector pointing to a table element, THE BrowserEngine SHALL return a list of rows where each row is a list of cell text strings.
2. WHEN `extract_table()` is called and the table element contains no rows, THE BrowserEngine SHALL return an empty list.
3. IF the selector does not match any table element, THEN THE BrowserEngine SHALL raise a BrowserError.
4. THE BrowserEngine SHALL strip whitespace from each cell text value in the extracted table data.
5. THE BrowserEngine SHALL include both `th` and `td` cells when extracting table rows.

### Requirement 4: Navigate Wait Strategy

**User Story:** As a user, I want page navigation to wait for network idle instead of just DOM content loaded, so that JavaScript-heavy pages are fully rendered before the system interacts with them.

#### Acceptance Criteria

1. WHEN `navigate()` is called on PlaywrightEngine, THE PlaywrightEngine SHALL use `networkidle` as the default wait strategy instead of `domcontentloaded`.
2. IF a page does not reach `networkidle` within the timeout period, THEN THE PlaywrightEngine SHALL raise a BrowserError.

### Requirement 5: Extract Table Action Handling

**User Story:** As a developer, I want the ActionExecutor to handle `extract_table` as a recognized action type, so that the iterative pipeline can extract tabular data during execution.

#### Acceptance Criteria

1. WHEN an ActionStep with `action_type="extract_table"` is executed, THE ActionExecutor SHALL call `BrowserEngine.extract_table()` with the step's selector and strategy.
2. WHEN `extract_table` succeeds, THE ActionExecutor SHALL serialize the table data as a JSON string in the ActionResult's `extracted_data` field.
3. IF `extract_table` fails with a BrowserError, THEN THE ActionExecutor SHALL return an ActionResult with `success=False` and the error message.

### Requirement 6: Pipeline Routing

**User Story:** As a developer, I want the App facade to automatically route requests between the legacy pipeline and the iterative pipeline, so that multi-step tasks use the iterative approach while simple tasks use the existing fast path.

#### Acceptance Criteria

1. WHEN parsed intents contain at least one NAVIGATE intent and at least one non-NAVIGATE intent, THE App_Facade SHALL route the request to the IterativeExecutor.
2. WHEN parsed intents contain a COMPOSITE intent that expands to include both NAVIGATE and non-NAVIGATE intents, THE App_Facade SHALL route the request to the IterativeExecutor.
3. WHEN parsed intents contain only a single action type or only NAVIGATE intents, THE App_Facade SHALL route the request to the legacy pipeline.

### Requirement 7: Data Models

**User Story:** As a developer, I want well-defined data models for the iterative pipeline, so that data flows between components are type-safe and validated.

#### Acceptance Criteria

1. THE IterationRecord SHALL contain non-None values for `step`, `result`, and `page_context_before` fields.
2. WHEN NextStepResult has `goal_reached=True`, THE NextStepResult SHALL have `step` set to None.
3. WHEN NextStepResult has `goal_reached=False`, THE NextStepResult SHALL have `step` set to a valid ActionStep.
4. THE IterativeExecutionError SHALL inherit from AppError and accept a message string parameter.

### Requirement 8: Error Handling trong Iterative Pipeline

**User Story:** As a user, I want the iterative pipeline to handle errors gracefully, so that partial results are returned even when some steps fail.

#### Acceptance Criteria

1. IF the LLM returns invalid JSON during `plan_next_step()`, THEN THE IterativeExecutor SHALL retry up to 2 times before stopping the loop and returning collected results.
2. IF a BrowserError occurs during `get_page_context()` or `execute_step()` in the iterative loop, THEN THE IterativeExecutor SHALL raise an IterativeExecutionError.
3. WHEN an IterativeExecutionError is raised, THE App_Facade SHALL catch the error and call `_ensure_browser_stable()` for recovery.
