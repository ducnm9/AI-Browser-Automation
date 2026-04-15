"""Google Gemini LLM provider using ``google-generativeai``.

Implements ``BaseLLMProvider`` for the Google Gemini API.  The API key
is read from ``AppConfig.gemini_api_key`` — never hardcoded.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import google.generativeai as genai

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.models.config import AppConfig, LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider using ``google.generativeai``.

    Args:
        config: Application configuration containing the Gemini API key.
        model: Model identifier to use. Defaults to ``"gemini-pro"``.
    """

    def __init__(
        self,
        config: AppConfig,
        model: str = "",
    ) -> None:
        self._config = config
        self._model_name = model or config.gemini_model
        self._model: Optional[genai.GenerativeModel] = None
        self._configure()

    def _configure(self) -> None:
        """Configure the Gemini SDK and create the generative model."""
        api_key = self._config.gemini_api_key
        if not api_key:
            logger.warning("Gemini API key not configured")
            return
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(self._model_name)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the Gemini API.

        Args:
            request: LLM request containing prompt and metadata.

        Returns:
            LLMResponse with generated content and usage info.

        Raises:
            LLMUnavailableError: When the Gemini API is unreachable
                or returns an error.
        """
        if self._model is None:
            raise LLMUnavailableError("Gemini model not configured")

        prompt = request.prompt
        if request.context:
            prompt = f"{request.context}\n\n{prompt}"

        start = time.monotonic()
        try:
            response = await self._model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=request.max_tokens,
                    temperature=request.temperature,
                ),
            )
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            raise LLMUnavailableError(
                f"Gemini API error: {exc}",
            ) from exc

        latency_ms = (time.monotonic() - start) * 1000

        content = response.text if response.text else ""
        tokens_used = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_used = getattr(
                response.usage_metadata, "total_token_count", 0,
            )

        return LLMResponse(
            content=content,
            provider_used=LLMProvider.GEMINI,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Check whether the Gemini API is reachable.

        Returns:
            True if the model is configured and a test call succeeds.
        """
        if self._model is None:
            return False
        try:
            await self._model.generate_content_async(
                "ping",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1,
                ),
            )
        except Exception:
            return False
        return True


__all__ = ["GeminiProvider"]
