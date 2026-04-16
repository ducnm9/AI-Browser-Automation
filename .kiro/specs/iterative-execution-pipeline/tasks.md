# Implementation Plan: Iterative Execution Pipeline

## Overview

Triển khai pipeline thực thi lặp (Observe-Plan-Act loop) cho AI Browser Automation. Thứ tự: foundation (errors, models) → browser layer (extract_table, navigate) → core logic (plan_next_step, action handling, IterativeExecutor) → facade wiring → tests. Tuân thủ DI pattern, Strategy Pattern (ABC), Google-style docstrings, type hints bắt buộc, và security rules.

## Tasks

- [x] 1. Add IterativeExecutionError and data models
  - [x] 1.1 Add `IterativeExecutionError` to `ai_browser_automation/exceptions/errors.py`
    - Add class inheriting from `AppError` with `message` parameter
    - Add to `__all__` exports
    - _Requirements: 7.4, 8.2_

  - [x] 1.2 Add `IterationRecord` and `NextStepResult` data models to `ai_browser_automation/models/actions.py`
    - Add `IterationRecord` dataclass with `step: ActionStep`, `result: ActionResult`, `page_context_before: PageContext` fields (all non-optional)
    - Add `NextStepResult` dataclass with `step: Optional[ActionStep]`, `goal_reached: bool`, `reasoning: str` fields
    - Import `PageContext` from `ai_browser_automation.browser.base`
    - Add both to `__all__` exports
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 1.3 Write property test for NextStepResult validity
    - Create `tests/properties/test_iterative_execution_properties.py`
    - **Property 3: NextStepResult validity** — if `goal_reached` is True then `step` is None; if False then `step` is non-None ActionStep with recognized `action_type`
    - **Validates: Requirements 2.2, 2.3, 7.2, 7.3**

- [x] 2. Implement `extract_table()` on browser engines
  - [x] 2.1 Add `extract_table()` abstract method to `ai_browser_automation/browser/base.py`
    - Add `@abstractmethod async def extract_table(self, selector: str, strategy: str = "css") -> list[list[str]]`
    - _Requirements: 3.1_

  - [x] 2.2 Implement `extract_table()` in `ai_browser_automation/browser/playwright_engine.py`
    - Use `page.evaluate()` with JS to query `tr` rows, extract `th` and `td` cells
    - Strip whitespace from each cell text
    - Return empty list for table with no rows
    - Raise `BrowserError` if selector matches no table
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 2.3 Implement `extract_table()` in `ai_browser_automation/browser/selenium_engine.py`
    - Use `driver.execute_script()` with equivalent JS logic via `_run_sync`
    - Same behavior: strip whitespace, include th+td, raise BrowserError if not found
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 2.4 Write property test for extract_table output structure
    - **Property 4: extract_table output structure** — for any HTML table, result is `list[list[str]]` where every cell is whitespace-stripped, both `th` and `td` included
    - **Validates: Requirements 3.1, 3.4, 3.5**

  - [x] 2.5 Write property test for extract_table serialization round-trip
    - **Property 6: extract_table serialization round-trip** — serializing table data as JSON then deserializing produces equal value
    - **Validates: Requirement 5.2**

- [x] 3. Improve PlaywrightEngine navigate wait strategy
  - [x] 3.1 Update `navigate()` in `ai_browser_automation/browser/playwright_engine.py` to use `networkidle`
    - Change `wait_until="domcontentloaded"` to `wait_until="networkidle"`
    - Ensure `BrowserError` is raised on timeout
    - _Requirements: 4.1, 4.2_

  - [x] 3.2 Write unit tests for navigate networkidle behavior
    - Test that `page.goto` is called with `wait_until="networkidle"`
    - Test that timeout raises `BrowserError`
    - _Requirements: 4.1, 4.2_

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement `plan_next_step()` on TaskPlanner
  - [x] 5.1 Add `plan_next_step()` method to `ai_browser_automation/core/task_planner.py`
    - Add `_PLAN_NEXT_STEP_TEMPLATE` prompt with goal, page context, history summary
    - Add `_format_history()` helper to summarize IterationRecord list
    - Add `_parse_next_step_response()` to parse LLM JSON into `NextStepResult`
    - Add `"extract_table"` to `_VALID_ACTION_TYPES` set
    - Return `NextStepResult` with `goal_reached=True` and `step=None` when LLM signals done
    - Return `NextStepResult` with valid `ActionStep` when LLM signals next step
    - Raise `PlanningError` on invalid JSON or missing fields
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 5.2 Write unit tests for `plan_next_step()`
    - Test valid response parsing (goal_reached=True and goal_reached=False)
    - Test PlanningError on invalid JSON
    - Test history formatting
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 6. Add `extract_table` action handling in ActionExecutor
  - [x] 6.1 Add `extract_table` action branch to `execute_step()` in `ai_browser_automation/core/action_executor.py`
    - Call `self.browser.extract_table(selector_value, strategy=selector_strategy)`
    - Serialize result as JSON string (`json.dumps(table_data, ensure_ascii=False)`) into `extracted_data`
    - Return `ActionResult(success=False, error_message=...)` on `BrowserError`
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 6.2 Write unit tests for extract_table action handling
    - Test successful extraction returns JSON in `extracted_data`
    - Test BrowserError returns failure result
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 7. Implement IterativeExecutor
  - [x] 7.1 Create `ai_browser_automation/core/iterative_executor.py` with `IterativeExecutor` class
    - Constructor accepts `task_planner: TaskPlanner`, `action_executor: ActionExecutor`, `browser_engine: BrowserEngine`, `max_iterations: int` via DI
    - Implement `async def execute(self, original_goal: str, intents: list[ParsedIntent]) -> list[ActionResult]`
    - Observe: call `browser_engine.get_page_context()`
    - Plan: call `task_planner.plan_next_step(goal, page_context, history)`
    - Act: call `action_executor.execute_step(step)`
    - Stop on `goal_reached=True` or `max_iterations` reached
    - On step failure: record in history, continue loop
    - On `PlanningError`: retry up to 2 times, then stop and return collected results
    - On `BrowserError` from `get_page_context()`/`execute_step()`: raise `IterativeExecutionError`
    - Maintain `len(history) == len(results)` invariant
    - Use `logging.getLogger(__name__)` for logging, mask sensitive data
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.2_

  - [x] 7.2 Update `ai_browser_automation/core/__init__.py` to export `IterativeExecutor`
    - Add import and `__all__` entry
    - _Requirements: 1.1_

  - [x] 7.3 Write property test for loop termination
    - **Property 1: Loop termination** — for any `max_iterations=N`, `len(results) <= N`
    - **Validates: Requirements 1.4, 1.6**

  - [x] 7.4 Write property test for history-result consistency
    - **Property 2: History-result consistency** — at every iteration `len(history) == len(results)`
    - **Validates: Requirement 1.2**

  - [x] 7.5 Write unit tests for IterativeExecutor
    - Test loop stops on `goal_reached=True`
    - Test loop stops at `max_iterations`
    - Test step failure recorded in history, loop continues
    - Test PlanningError retry (up to 2 times)
    - Test BrowserError raises IterativeExecutionError
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 8.2_

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Wire IterativeExecutor into App facade
  - [x] 9.1 Add `_needs_iterative_execution()` routing method to `ai_browser_automation/app.py`
    - Expand composite intents via `TaskPlanner._expand_intents()`
    - Return True if intents contain at least one NAVIGATE and at least one non-NAVIGATE
    - Return False for single action type or only NAVIGATE intents
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 9.2 Create and wire `IterativeExecutor` in `initialize()` and update `_execute_pipeline()` in `ai_browser_automation/app.py`
    - Instantiate `IterativeExecutor` with existing `task_planner`, `action_executor`, `browser_engine` via DI
    - In `_execute_pipeline()`: after parsing intents, call `_needs_iterative_execution()`
    - Route to `iterative_executor.execute()` or legacy pipeline accordingly
    - Catch `IterativeExecutionError` in `chat()` and call `_ensure_browser_stable()` for recovery
    - _Requirements: 6.1, 6.2, 6.3, 8.3_

  - [x] 9.3 Write property test for routing correctness
    - **Property 5: Routing correctness** — navigate + non-navigate → True; single type or only navigate → False
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 9.4 Write unit tests for App routing and IterativeExecutionError handling
    - Test `_needs_iterative_execution()` with various intent combinations
    - Test `IterativeExecutionError` caught and `_ensure_browser_stable()` called
    - _Requirements: 6.1, 6.2, 6.3, 8.3_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
