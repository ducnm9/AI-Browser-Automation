"""AWS Bedrock LLM provider using ``boto3``.

Implements ``BaseLLMProvider`` for AWS Bedrock.  Region and credentials
are read from ``AppConfig`` and the standard AWS credential chain —
never hardcoded.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import partial
from typing import Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.models.config import AppConfig, LLMProvider

logger = logging.getLogger(__name__)


class BedrockProvider(BaseLLMProvider):
    """AWS Bedrock provider using ``boto3``.

    Uses ``asyncio.get_event_loop().run_in_executor`` to wrap the
    synchronous boto3 calls for async compatibility.

    Args:
        config: Application configuration with optional bedrock_region.
        model_id: Bedrock model identifier. Defaults to
            ``"anthropic.claude-3-sonnet-20240229-v1:0"``.
    """

    def __init__(
        self,
        config: AppConfig,
        model_id: str = "",
    ) -> None:
        self._config = config
        self._model_id = model_id or config.bedrock_model
        self._client: Optional[Any] = None
        self._ensure_client()

    def _ensure_client(self) -> None:
        """Create the boto3 bedrock-runtime client if not yet created."""
        if self._client is not None:
            return
        region = self._config.bedrock_region or "us-east-1"
        try:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=region,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Failed to create Bedrock client: %s", exc)
            self._client = None

    async def _invoke_model(self, body: dict[str, Any]) -> dict[str, Any]:
        """Invoke the Bedrock model in a thread executor.

        Args:
            body: JSON-serialisable request body.

        Returns:
            Parsed JSON response from Bedrock.

        Raises:
            LLMUnavailableError: On any boto3 / network error.
        """
        if self._client is None:
            raise LLMUnavailableError("Bedrock client not initialised")

        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(
                None,
                partial(
                    self._client.invoke_model,
                    modelId=self._model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(body),
                ),
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Bedrock invoke error: %s", exc)
            raise LLMUnavailableError(
                f"Bedrock invoke error: {exc}",
            ) from exc

        raw = response["body"].read()
        return json.loads(raw)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to AWS Bedrock.

        Args:
            request: LLM request containing prompt and metadata.

        Returns:
            LLMResponse with generated content and usage info.

        Raises:
            LLMUnavailableError: When Bedrock is unreachable or
                returns an error.
        """
        prompt = request.prompt
        if request.context:
            prompt = f"{request.context}\n\n{prompt}"

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        start = time.monotonic()
        result = await self._invoke_model(body)
        latency_ms = (time.monotonic() - start) * 1000

        content = ""
        if "content" in result and result["content"]:
            content = result["content"][0].get("text", "")

        input_tokens = result.get("usage", {}).get("input_tokens", 0)
        output_tokens = result.get("usage", {}).get("output_tokens", 0)
        tokens_used = input_tokens + output_tokens

        return LLMResponse(
            content=content,
            provider_used=LLMProvider.BEDROCK,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Check whether the Bedrock service is reachable.

        Returns:
            True if a minimal invoke succeeds.
        """
        try:
            await self._invoke_model({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1,
                "messages": [
                    {"role": "user", "content": "ping"},
                ],
            })
        except LLMUnavailableError:
            return False
        return True


__all__ = ["BedrockProvider"]
