"""OpenAI LLM provider using the async OpenAI client.

Implements ``BaseLLMProvider`` for the OpenAI ChatGPT API via
``openai.AsyncOpenAI``.  The API key is read from ``AppConfig`` —
never hardcoded.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import openai

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.models.config import AppConfig, LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI ChatGPT provider using ``openai.AsyncOpenAI``.

    Args:
        config: Application configuration containing the OpenAI API key.
        model: Model identifier to use. Defaults to ``"gpt-4"``.
    """

    def __init__(
        self,
        config: AppConfig,
        model: str = "",
    ) -> None:
        self._config = config
        self._model = model or config.openai_model
        self._client: Optional[openai.AsyncOpenAI] = None
        self._ensure_client()

    def _ensure_client(self) -> None:
        """Lazily create the async OpenAI client."""
        if self._client is None:
            api_key = self._config.openai_api_key
            if not api_key:
                logger.warning("OpenAI API key not configured")
            self._client = openai.AsyncOpenAI(api_key=api_key or "")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the OpenAI API.

        Args:
            request: LLM request containing prompt and metadata.

        Returns:
            LLMResponse with generated content and usage info.

        Raises:
            LLMUnavailableError: When the OpenAI API is unreachable
                or returns an error.
        """
        self._ensure_client()
        assert self._client is not None  # noqa: S101

        messages: list[dict[str, str]] = []
        if request.context:
            messages.append({"role": "system", "content": request.context})
        messages.append({"role": "user", "content": request.prompt})

        start = time.monotonic()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except openai.APIConnectionError as exc:
            logger.error("OpenAI connection failed: %s", exc)
            raise LLMUnavailableError(
                f"OpenAI connection failed: {exc}",
            ) from exc
        except openai.APIStatusError as exc:
            logger.error("OpenAI API error %s: %s", exc.status_code, exc)
            raise LLMUnavailableError(
                f"OpenAI API error {exc.status_code}: {exc}",
            ) from exc

        latency_ms = (time.monotonic() - start) * 1000

        choice = response.choices[0]
        content = choice.message.content or ""
        tokens_used = (
            response.usage.total_tokens if response.usage else 0
        )

        return LLMResponse(
            content=content,
            provider_used=LLMProvider.OPENAI,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Check whether the OpenAI API is reachable.

        Returns:
            True if a lightweight models list call succeeds.
        """
        self._ensure_client()
        assert self._client is not None  # noqa: S101
        try:
            await self._client.models.list()
        except (openai.APIConnectionError, openai.APIStatusError):
            return False
        return True


__all__ = ["OpenAIProvider"]
