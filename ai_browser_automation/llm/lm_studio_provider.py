"""LM Studio local LLM provider using ``httpx.AsyncClient``.

Implements ``BaseLLMProvider`` for a locally-running LM Studio server
that exposes an OpenAI-compatible API.  The endpoint URL is read from
``AppConfig.lm_studio_url`` — no API key required.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.models.config import AppConfig, LLMProvider

logger = logging.getLogger(__name__)


class LMStudioProvider(BaseLLMProvider):
    """LM Studio local provider using ``httpx.AsyncClient``.

    Communicates with a locally-running LM Studio server via its
    OpenAI-compatible ``/chat/completions`` endpoint.

    Args:
        config: Application configuration containing lm_studio_url.
        model: Model identifier to request. Defaults to ``"local-model"``.
    """

    def __init__(
        self,
        config: AppConfig,
        model: str = "",
    ) -> None:
        self._config = config
        self._model = model or config.lm_studio_model
        self._base_url = config.lm_studio_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _ensure_client(self) -> None:
        """Create the httpx async client if not yet created."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(60.0),
            )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the local LM Studio server.

        Uses the OpenAI-compatible ``/chat/completions`` endpoint.

        Args:
            request: LLM request containing prompt and metadata.

        Returns:
            LLMResponse with generated content and usage info.

        Raises:
            LLMUnavailableError: When the LM Studio server is
                unreachable or returns an error.
        """
        self._ensure_client()
        assert self._client is not None  # noqa: S101

        messages: list[dict[str, str]] = []
        if request.context:
            messages.append({"role": "system", "content": request.context})
        messages.append({"role": "user", "content": request.prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        start = time.monotonic()
        try:
            response = await self._client.post(
                "/chat/completions",
                json=payload,
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.error("LM Studio connection failed: %s", exc)
            raise LLMUnavailableError(
                f"LM Studio connection failed: {exc}",
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response else "N/A"
            logger.error(
                "LM Studio HTTP error %s: %s — body: %s",
                exc.response.status_code,
                exc,
                body,
            )
            raise LLMUnavailableError(
                f"LM Studio HTTP error {exc.response.status_code}: {body}",
            ) from exc

        latency_ms = (time.monotonic() - start) * 1000

        data = response.json()
        content = ""
        if data.get("choices"):
            content = (
                data["choices"][0]
                .get("message", {})
                .get("content", "")
            )

        usage = data.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)

        return LLMResponse(
            content=content,
            provider_used=LLMProvider.LM_STUDIO,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Check whether the LM Studio server is reachable.

        Returns:
            True if the ``/models`` endpoint responds successfully.
        """
        self._ensure_client()
        assert self._client is not None  # noqa: S101
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except (httpx.ConnectError, httpx.HTTPStatusError):
            return False


__all__ = ["LMStudioProvider"]
