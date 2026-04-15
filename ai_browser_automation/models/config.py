"""Application configuration and security policy models.

``AppConfig`` uses pydantic ``BaseModel`` with field validators to enforce
constraints defined in Requirements 8.1–8.5.  ``SecurityPolicy`` and
``LLMProvider`` are lightweight data/enum types used across the application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


class LLMProvider(Enum):
    """Supported LLM provider backends."""

    OPENAI = "openai"
    GEMINI = "gemini"
    BEDROCK = "bedrock"
    LM_STUDIO = "lm_studio"


@dataclass
class SecurityPolicy:
    """Security policy controlling sensitive-data handling.

    Args:
        sensitive_patterns: Extra regex patterns to treat as sensitive.
        force_local_on_sensitive: Route to local LLM when sensitive data
            is detected.
        encrypt_local_storage: Encrypt credentials stored on disk.
        mask_in_logs: Mask sensitive data in log output.
    """

    sensitive_patterns: list[str] = field(default_factory=list)
    force_local_on_sensitive: bool = True
    encrypt_local_storage: bool = True
    mask_in_logs: bool = True


class AppConfig(BaseModel):
    """Application-wide configuration with pydantic validation.

    Attributes:
        default_llm: Default LLM provider (defaults to LM Studio for
            local-first security).
        openai_api_key: OpenAI API key; must start with ``"sk-"`` if set.
        gemini_api_key: Google Gemini API key; optional.
        bedrock_region: AWS region for Bedrock; optional.
        lm_studio_url: Base URL for the LM Studio server.
        action_timeout_ms: Per-action timeout in milliseconds, in (0, 60000].
        max_retries: Maximum retry attempts per action step, in [0, 10].
    """

    default_llm: LLMProvider = LLMProvider.LM_STUDIO
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-pro"
    bedrock_region: Optional[str] = None
    bedrock_model: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "local-model"
    action_timeout_ms: int = 10000
    max_retries: int = 3

    @field_validator("openai_api_key")
    @classmethod
    def _validate_openai_api_key(
        cls, value: Optional[str],
    ) -> Optional[str]:
        """Ensure the OpenAI key starts with ``sk-`` when provided."""
        if value is not None and not value.startswith("sk-"):
            raise ValueError("openai_api_key must start with 'sk-'")
        return value

    @field_validator("lm_studio_url")
    @classmethod
    def _validate_lm_studio_url(cls, value: str) -> str:
        """Ensure ``lm_studio_url`` is a valid URL."""
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                "lm_studio_url must be a valid URL with scheme and host"
            )
        return value

    @field_validator("action_timeout_ms")
    @classmethod
    def _validate_action_timeout_ms(cls, value: int) -> int:
        """Ensure timeout is in the range (0, 60000]."""
        if value <= 0 or value > 60000:
            raise ValueError(
                "action_timeout_ms must be in range (0, 60000]"
            )
        return value

    @field_validator("max_retries")
    @classmethod
    def _validate_max_retries(cls, value: int) -> int:
        """Ensure max_retries is in the range [0, 10]."""
        if value < 0 or value > 10:
            raise ValueError("max_retries must be in range [0, 10]")
        return value


__all__ = [
    "LLMProvider",
    "SecurityPolicy",
    "AppConfig",
]
