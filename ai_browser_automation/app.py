"""Facade for AI Browser Automation.

``AIBrowserAutomation`` is the single entry point for the application.
It hides all internal complexity behind three methods: ``initialize()``,
``chat()``, and ``shutdown()``.  Components are wired together via
dependency injection during ``initialize()``.

Requirements: 9.1, 9.2, 9.3, 9.4, 1.3
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ai_browser_automation.browser.base import BrowserEngine
from ai_browser_automation.browser.factory import BrowserEngineFactory
from ai_browser_automation.core.action_executor import ActionExecutor
from ai_browser_automation.core.iterative_executor import IterativeExecutor
from ai_browser_automation.core.nl_processor import NLProcessor
from ai_browser_automation.core.task_planner import TaskPlanner
from ai_browser_automation.models.intents import IntentType, ParsedIntent
from ai_browser_automation.exceptions.errors import (
    AppError,
    IterativeExecutionError,
)
from ai_browser_automation.llm.bedrock_provider import BedrockProvider
from ai_browser_automation.llm.factory import LLMProviderFactory
from ai_browser_automation.llm.gemini_provider import GeminiProvider
from ai_browser_automation.llm.lm_studio_provider import LMStudioProvider
from ai_browser_automation.llm.openai_provider import OpenAIProvider
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.actions import ActionResult
from ai_browser_automation.models.config import (
    AppConfig,
    LLMProvider,
    SecurityPolicy,
)
from ai_browser_automation.models.conversation import (
    ConversationHistory,
    ConversationTurn,
)
from ai_browser_automation.security.security_layer import SecurityLayer

logger = logging.getLogger(__name__)


def _format_results(results: list[ActionResult]) -> str:
    """Build a human-readable summary from action results.

    Args:
        results: List of action results from the executor.

    Returns:
        A summary string describing successes and failures.
    """
    if not results:
        return "No actions were executed."

    success_count = sum(1 for r in results if r.success)
    total_count = len(results)

    parts: list[str] = []
    max_display = 2000
    for r in results:
        if r.success:
            detail = r.extracted_data or "OK"
            if len(detail) > max_display:
                detail = detail[:max_display] + "... (truncated)"
            parts.append(f"[OK] {r.step.action_type}: {detail}")
        else:
            parts.append(
                f"[FAIL] {r.step.action_type}: "
                f"{r.error_message or 'unknown error'}"
            )

    header = f"Completed {success_count}/{total_count} actions."
    return f"{header}\n" + "\n".join(parts)


class AIBrowserAutomation:
    """Facade that orchestrates all components behind a simple API.

    Provides ``initialize()``, ``chat()``, and ``shutdown()`` as the
    only public interface.  Internal components are created during
    ``initialize()`` via dependency injection and factory patterns.

    Args:
        config: Application configuration.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._security: Optional[SecurityLayer] = None
        self._llm_router: Optional[LLMRouter] = None
        self._browser_engine: Optional[BrowserEngine] = None
        self._nl_processor: Optional[NLProcessor] = None
        self._task_planner: Optional[TaskPlanner] = None
        self._action_executor: Optional[ActionExecutor] = None
        self._iterative_executor: Optional[IterativeExecutor] = None
        self._history = ConversationHistory()
        self._initialized = False

    async def initialize(self) -> None:
        """Create and wire all components via DI and factories.

        Registers all four LLM providers (OpenAI, Gemini, Bedrock,
        LM Studio) via ``LLMProviderFactory``, creates a browser
        engine with Playwright-to-Selenium fallback, and assembles
        the NL processor, task planner, and action executor.

        Raises:
            AppError: When a critical component fails to initialise.
        """
        logger.info("Initializing AIBrowserAutomation")

        # Security layer
        self._security = SecurityLayer(SecurityPolicy())

        # LLM router + provider registration
        self._llm_router = LLMRouter(self._config)
        self._register_providers()

        # Browser engine (Playwright -> Selenium fallback)
        try:
            self._browser_engine = BrowserEngineFactory.create()
            await self._browser_engine.launch()
            logger.info("Browser engine launched")
        except RuntimeError as exc:
            raise AppError(
                f"Failed to create browser engine: {exc}"
            ) from exc

        # Core components via DI
        self._nl_processor = NLProcessor(
            self._llm_router, self._security,
        )
        self._task_planner = TaskPlanner(self._llm_router)
        self._action_executor = ActionExecutor(
            self._browser_engine, self._llm_router,
        )

        # Iterative executor via DI
        self._iterative_executor = IterativeExecutor(
            task_planner=self._task_planner,
            action_executor=self._action_executor,
            browser_engine=self._browser_engine,
            llm_router=self._llm_router,
        )

        self._initialized = True
        logger.info("AIBrowserAutomation initialized successfully")

    async def chat(self, user_input: str) -> str:
        """Run the full pipeline for a user command.

        Pipeline: security check -> NL parse -> confidence check ->
        get page context -> plan -> execute -> format results ->
        update conversation history.

        Sensitive data is auto-routed to the local LLM before
        pipeline execution.  On failure at any step the method
        returns a detailed error message and ensures the browser
        remains in a stable state.

        Args:
            user_input: Natural-language command from the user.

        Returns:
            A human-readable result summary or error message.
        """
        if not self._initialized:
            return (
                "Error: system not initialized. "
                "Call initialize() first."
            )

        assert self._security is not None  # noqa: S101
        assert self._nl_processor is not None  # noqa: S101
        assert self._task_planner is not None  # noqa: S101
        assert self._action_executor is not None  # noqa: S101
        assert self._browser_engine is not None  # noqa: S101
        assert self._llm_router is not None  # noqa: S101

        # Log masked input
        logger.info(
            "Processing command: %s",
            self._security.mask_for_log(user_input),
        )

        try:
            return await self._execute_pipeline(user_input)
        except AppError as exc:
            logger.error("Pipeline error: %s", exc.message)
            await self._ensure_browser_stable()
            return f"Error: {exc.message}"
        except Exception as exc:
            logger.error(
                "Unexpected error: %s", exc, exc_info=True,
            )
            await self._ensure_browser_stable()
            return f"Unexpected error: {exc}"

    async def shutdown(self) -> None:
        """Close the browser and clean up resources.

        Safe to call even if ``initialize()`` was never called or
        the browser is already closed.
        """
        logger.info("Shutting down AIBrowserAutomation")
        if self._browser_engine is not None:
            try:
                await self._browser_engine.close()
                logger.info("Browser engine closed")
            except Exception as exc:
                logger.warning(
                    "Error closing browser: %s", exc,
                )
        self._initialized = False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register_providers(self) -> None:
        """Register all four LLM providers via the factory."""
        assert self._llm_router is not None  # noqa: S101

        LLMProviderFactory.register(
            LLMProvider.OPENAI, OpenAIProvider,
        )
        LLMProviderFactory.register(
            LLMProvider.GEMINI, GeminiProvider,
        )
        LLMProviderFactory.register(
            LLMProvider.BEDROCK, BedrockProvider,
        )
        LLMProviderFactory.register(
            LLMProvider.LM_STUDIO, LMStudioProvider,
        )

        for provider_type in LLMProvider:
            try:
                provider = LLMProviderFactory.create(
                    provider_type, self._config,
                )
                self._llm_router.register_provider(
                    provider_type, provider,
                )
            except (ValueError, Exception) as exc:
                logger.warning(
                    "Could not register %s: %s",
                    provider_type.value,
                    exc,
                )

    async def _execute_pipeline(
        self, user_input: str,
    ) -> str:
        """Execute the main processing pipeline.

        Args:
            user_input: Raw user command.

        Returns:
            Result summary string.

        Raises:
            AppError: On any pipeline step failure.
        """
        assert self._security is not None  # noqa: S101
        assert self._nl_processor is not None  # noqa: S101
        assert self._task_planner is not None  # noqa: S101
        assert self._action_executor is not None  # noqa: S101
        assert self._browser_engine is not None  # noqa: S101
        assert self._llm_router is not None  # noqa: S101

        # Step 1: Security check — route sensitive data to local
        is_sensitive = self._security.should_use_local_llm(
            user_input,
        )
        if is_sensitive:
            self._llm_router.default_provider = (
                LLMProvider.LM_STUDIO
            )
            logger.info(
                "Sensitive data detected, routing to local LLM",
            )

        # Step 2: NL parse
        intents = await self._nl_processor.parse(user_input)

        # Step 3: Confidence check — clarify if < 0.7
        low_confidence = [
            i for i in intents if i.confidence < 0.7
        ]
        if low_confidence:
            clarification = await self._nl_processor.clarify(
                user_input,
                [i.target_description for i in low_confidence],
            )
            return f"Xin hãy làm rõ: {clarification}"

        # Step 4: Route to iterative or legacy pipeline
        if self._needs_iterative_execution(intents):
            assert (  # noqa: S101
                self._iterative_executor is not None
            )
            results = await self._iterative_executor.execute(
                original_goal=user_input,
                intents=intents,
            )
        else:
            # Legacy pipeline: get context → plan → execute
            page_context = (
                await self._browser_engine.get_page_context()
            )
            plan = await self._task_planner.plan(
                intents, page_context,
            )
            results = (
                await self._action_executor.execute_plan(plan)
            )

        # Step 5: Format results
        summary = _format_results(results)

        # Step 6: Update conversation history
        self._history.add_turn(ConversationTurn(
            role="user",
            content=user_input,
            timestamp=time.time(),
        ))
        self._history.add_turn(ConversationTurn(
            role="assistant",
            content=summary,
            timestamp=time.time(),
            actions_taken=results,
        ))

        logger.info(
            "Pipeline completed: %s",
            self._security.mask_for_log(summary),
        )
        return summary

    def _needs_iterative_execution(
        self,
        intents: list[ParsedIntent],
    ) -> bool:
        """Determine whether the request requires iterative execution.

        Expands composite intents via ``TaskPlanner._expand_intents()``
        and checks whether the flattened list contains more than one
        distinct intent, or if any original intent is COMPOSITE
        (even with empty sub_intents, indicating the LLM recognised
        a multi-step goal but failed to enumerate sub-steps).

        Args:
            intents: Parsed user intents (may include composites).

        Returns:
            True if the request should be routed to the iterative
            pipeline; False for single-action or navigate-only
            requests.
        """
        # Any COMPOSITE intent signals a multi-step goal
        has_composite = any(
            i.intent_type is IntentType.COMPOSITE
            for i in intents
        )
        if has_composite:
            return True

        flat_intents = TaskPlanner._expand_intents(intents)

        # Any EXTRACT_DATA intent benefits from the iterative
        # pipeline's LLM extract fallback, even without navigate
        has_extract = any(
            i.intent_type is IntentType.EXTRACT_DATA
            for i in flat_intents
        )
        if has_extract:
            return True

        # Multiple distinct intent types → iterative
        if len(flat_intents) >= 2:
            intent_types = {i.intent_type for i in flat_intents}
            if len(intent_types) > 1:
                return True

        # Classic check: NAVIGATE + something else
        has_navigate = any(
            i.intent_type is IntentType.NAVIGATE
            for i in flat_intents
        )
        has_other = any(
            i.intent_type is not IntentType.NAVIGATE
            for i in flat_intents
        )
        return has_navigate and has_other

    async def _ensure_browser_stable(self) -> None:
        """Best-effort attempt to leave the browser in a usable state."""
        if self._browser_engine is None:
            return
        try:
            await self._browser_engine.get_page_context()
        except Exception as exc:
            logger.warning(
                "Browser may be unstable: %s", exc,
            )


__all__ = ["AIBrowserAutomation"]
