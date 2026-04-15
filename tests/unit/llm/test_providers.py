"""Unit tests for concrete LLM providers.

Tests use mocked external clients to verify each provider correctly:
- Inherits from BaseLLMProvider
- Returns LLMResponse with correct provider_used enum
- Tracks latency_ms and tokens_used
- Wraps external errors in LLMUnavailableError
- Receives config via constructor (DI)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_browser_automation.exceptions.errors import LLMUnavailableError
from ai_browser_automation.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai_browser_automation.models.config import AppConfig, LLMProvider


@pytest.fixture()
def config() -> AppConfig:
    """Provide a test AppConfig with dummy values."""
    return AppConfig(
        openai_api_key="sk-test-key-123",
        gemini_api_key="test-gemini-key",
        bedrock_region="us-west-2",
        lm_studio_url="http://localhost:1234/v1",
    )


@pytest.fixture()
def request_obj() -> LLMRequest:
    """Provide a basic LLMRequest for testing."""
    return LLMRequest(prompt="Hello", max_tokens=100, temperature=0.5)


# ── OpenAI Provider ──────────────────────────────────────────────

class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_inherits_base(self, config: AppConfig) -> None:
        """OpenAIProvider is a BaseLLMProvider."""
        from ai_browser_automation.llm.openai_provider import OpenAIProvider
        provider = OpenAIProvider(config)
        assert isinstance(provider, BaseLLMProvider)

    @pytest.mark.asyncio()
    async def test_complete_returns_correct_provider(
        self, config: AppConfig, request_obj: LLMRequest,
    ) -> None:
        """complete() returns LLMResponse with OPENAI provider_used."""
        from ai_browser_automation.llm.openai_provider import OpenAIProvider

        mock_usage = MagicMock(total_tokens=42)
        mock_message = MagicMock(content="Hi there")
        mock_choice = MagicMock(message=mock_message)
        mock_response = MagicMock(choices=[mock_choice], usage=mock_usage)

        provider = OpenAIProvider(config)
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=mock_response,
        )

        result = await provider.complete(request_obj)

        assert isinstance(result, LLMResponse)
        assert result.provider_used == LLMProvider.OPENAI
        assert result.content == "Hi there"
        assert result.tokens_used == 42
        assert result.latency_ms >= 0

    @pytest.mark.asyncio()
    async def test_complete_wraps_connection_error(
        self, config: AppConfig, request_obj: LLMRequest,
    ) -> None:
        """complete() wraps openai errors in LLMUnavailableError."""
        import openai as openai_mod
        from ai_browser_automation.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(config)
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=openai_mod.APIConnectionError(
                request=MagicMock(),
            ),
        )

        with pytest.raises(LLMUnavailableError):
            await provider.complete(request_obj)

    @pytest.mark.asyncio()
    async def test_health_check_returns_bool(
        self, config: AppConfig,
    ) -> None:
        """health_check() returns a boolean."""
        from ai_browser_automation.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(config)
        provider._client = MagicMock()
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(return_value=[])

        result = await provider.health_check()
        assert result is True


# ── Gemini Provider ──────────────────────────────────────────────

class TestGeminiProvider:
    """Tests for GeminiProvider."""

    def test_inherits_base(self, config: AppConfig) -> None:
        """GeminiProvider is a BaseLLMProvider."""
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel"):
                from ai_browser_automation.llm.gemini_provider import (
                    GeminiProvider,
                )
                provider = GeminiProvider(config)
                assert isinstance(provider, BaseLLMProvider)

    @pytest.mark.asyncio()
    async def test_complete_returns_correct_provider(
        self, config: AppConfig, request_obj: LLMRequest,
    ) -> None:
        """complete() returns LLMResponse with GEMINI provider_used."""
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel") as mock_cls:
                from ai_browser_automation.llm.gemini_provider import (
                    GeminiProvider,
                )

                mock_model = MagicMock()
                mock_response = MagicMock()
                mock_response.text = "Gemini says hi"
                mock_response.usage_metadata = MagicMock(
                    total_token_count=30,
                )
                mock_model.generate_content_async = AsyncMock(
                    return_value=mock_response,
                )
                mock_cls.return_value = mock_model

                provider = GeminiProvider(config)
                result = await provider.complete(request_obj)

                assert isinstance(result, LLMResponse)
                assert result.provider_used == LLMProvider.GEMINI
                assert result.content == "Gemini says hi"
                assert result.tokens_used == 30
                assert result.latency_ms >= 0

    @pytest.mark.asyncio()
    async def test_complete_raises_when_not_configured(
        self, request_obj: LLMRequest,
    ) -> None:
        """complete() raises LLMUnavailableError when no API key."""
        no_key_config = AppConfig(gemini_api_key=None)
        from ai_browser_automation.llm.gemini_provider import GeminiProvider
        provider = GeminiProvider(no_key_config)

        with pytest.raises(LLMUnavailableError, match="not configured"):
            await provider.complete(request_obj)

    @pytest.mark.asyncio()
    async def test_health_check_false_when_not_configured(self) -> None:
        """health_check() returns False when model is None."""
        no_key_config = AppConfig(gemini_api_key=None)
        from ai_browser_automation.llm.gemini_provider import GeminiProvider
        provider = GeminiProvider(no_key_config)

        assert await provider.health_check() is False


# ── Bedrock Provider ─────────────────────────────────────────────

class TestBedrockProvider:
    """Tests for BedrockProvider."""

    def test_inherits_base(self, config: AppConfig) -> None:
        """BedrockProvider is a BaseLLMProvider."""
        with patch("boto3.client"):
            from ai_browser_automation.llm.bedrock_provider import (
                BedrockProvider,
            )
            provider = BedrockProvider(config)
            assert isinstance(provider, BaseLLMProvider)

    @pytest.mark.asyncio()
    async def test_complete_returns_correct_provider(
        self, config: AppConfig, request_obj: LLMRequest,
    ) -> None:
        """complete() returns LLMResponse with BEDROCK provider_used."""
        import json

        with patch("boto3.client") as mock_boto:
            from ai_browser_automation.llm.bedrock_provider import (
                BedrockProvider,
            )

            response_body = json.dumps({
                "content": [{"text": "Bedrock says hi"}],
                "usage": {"input_tokens": 10, "output_tokens": 15},
            }).encode()
            mock_body = MagicMock()
            mock_body.read.return_value = response_body
            mock_client = MagicMock()
            mock_client.invoke_model.return_value = {"body": mock_body}
            mock_boto.return_value = mock_client

            provider = BedrockProvider(config)
            result = await provider.complete(request_obj)

            assert isinstance(result, LLMResponse)
            assert result.provider_used == LLMProvider.BEDROCK
            assert result.content == "Bedrock says hi"
            assert result.tokens_used == 25
            assert result.latency_ms >= 0

    @pytest.mark.asyncio()
    async def test_complete_wraps_boto_error(
        self, config: AppConfig, request_obj: LLMRequest,
    ) -> None:
        """complete() wraps boto3 errors in LLMUnavailableError."""
        from botocore.exceptions import ClientError

        with patch("boto3.client") as mock_boto:
            from ai_browser_automation.llm.bedrock_provider import (
                BedrockProvider,
            )

            mock_client = MagicMock()
            mock_client.invoke_model.side_effect = ClientError(
                {"Error": {"Code": "500", "Message": "fail"}},
                "InvokeModel",
            )
            mock_boto.return_value = mock_client

            provider = BedrockProvider(config)
            with pytest.raises(LLMUnavailableError):
                await provider.complete(request_obj)


# ── LM Studio Provider ──────────────────────────────────────────

class TestLMStudioProvider:
    """Tests for LMStudioProvider."""

    def test_inherits_base(self, config: AppConfig) -> None:
        """LMStudioProvider is a BaseLLMProvider."""
        from ai_browser_automation.llm.lm_studio_provider import (
            LMStudioProvider,
        )
        provider = LMStudioProvider(config)
        assert isinstance(provider, BaseLLMProvider)

    @pytest.mark.asyncio()
    async def test_complete_returns_correct_provider(
        self, config: AppConfig, request_obj: LLMRequest,
    ) -> None:
        """complete() returns LLMResponse with LM_STUDIO provider_used."""
        from ai_browser_automation.llm.lm_studio_provider import (
            LMStudioProvider,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Local says hi"}},
            ],
            "usage": {"total_tokens": 20},
        }
        mock_response.raise_for_status = MagicMock()

        provider = LMStudioProvider(config)
        provider._client = MagicMock()
        provider._client.post = AsyncMock(return_value=mock_response)

        result = await provider.complete(request_obj)

        assert isinstance(result, LLMResponse)
        assert result.provider_used == LLMProvider.LM_STUDIO
        assert result.content == "Local says hi"
        assert result.tokens_used == 20
        assert result.latency_ms >= 0

    @pytest.mark.asyncio()
    async def test_complete_wraps_connect_error(
        self, config: AppConfig, request_obj: LLMRequest,
    ) -> None:
        """complete() wraps httpx errors in LLMUnavailableError."""
        import httpx

        from ai_browser_automation.llm.lm_studio_provider import (
            LMStudioProvider,
        )

        provider = LMStudioProvider(config)
        provider._client = MagicMock()
        provider._client.post = AsyncMock(
            side_effect=httpx.ConnectError("refused"),
        )

        with pytest.raises(LLMUnavailableError):
            await provider.complete(request_obj)

    @pytest.mark.asyncio()
    async def test_health_check_returns_true_on_200(
        self, config: AppConfig,
    ) -> None:
        """health_check() returns True when /models returns 200."""
        from ai_browser_automation.llm.lm_studio_provider import (
            LMStudioProvider,
        )

        mock_response = MagicMock(status_code=200)
        provider = LMStudioProvider(config)
        provider._client = MagicMock()
        provider._client.get = AsyncMock(return_value=mock_response)

        assert await provider.health_check() is True

    @pytest.mark.asyncio()
    async def test_health_check_returns_false_on_error(
        self, config: AppConfig,
    ) -> None:
        """health_check() returns False on connection error."""
        import httpx

        from ai_browser_automation.llm.lm_studio_provider import (
            LMStudioProvider,
        )

        provider = LMStudioProvider(config)
        provider._client = MagicMock()
        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("refused"),
        )

        assert await provider.health_check() is False
