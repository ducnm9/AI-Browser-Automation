"""Base LLM provider interface and request/response data classes.

Defines the abstract strategy interface ``BaseLLMProvider`` that all
concrete LLM providers must implement, along with the ``LLMRequest``
and ``LLMResponse`` data classes used across the LLM layer.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ai_browser_automation.models.config import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """Encapsulates a request to an LLM provider.

    Args:
        prompt: The prompt text to send to the LLM.
        context: Optional additional context for the request.
        max_tokens: Maximum number of tokens in the response.
        temperature: Sampling temperature for response generation.
        is_sensitive: Whether the request contains sensitive data.
    """

    prompt: str
    context: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.1
    is_sensitive: bool = False


@dataclass
class LLMResponse:
    """Encapsulates a response from an LLM provider.

    Args:
        content: The generated text content.
        provider_used: Which LLM provider handled the request.
        tokens_used: Number of tokens consumed.
        latency_ms: Response latency in milliseconds.
    """

    content: str
    provider_used: LLMProvider
    tokens_used: int
    latency_ms: float


class BaseLLMProvider(ABC):
    """Abstract strategy interface for LLM providers.

    All concrete providers (OpenAI, Gemini, Bedrock, LM Studio) must
    implement ``complete`` and ``health_check``.
    """

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the LLM and return the response.

        Args:
            request: LLM request containing prompt and metadata.

        Returns:
            LLMResponse with generated content and usage info.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check whether the provider is available and healthy.

        Returns:
            True if the provider is ready to accept requests.
        """
        ...


__all__ = [
    "LLMRequest",
    "LLMResponse",
    "BaseLLMProvider",
]
