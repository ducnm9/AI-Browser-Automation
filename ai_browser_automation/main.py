"""Entry point for AI Browser Automation.

Loads configuration from ``config.yaml`` and environment variables,
constructs the application facade, and starts the CLI chat interface.

API keys are read exclusively from environment variables — they are
never hardcoded or stored in plain-text config files.

Requirements: 5.7, 8.5
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from ai_browser_automation.app import AIBrowserAutomation
from ai_browser_automation.interfaces.chat_interface import ChatInterface
from ai_browser_automation.models.config import AppConfig, LLMProvider

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "config.yaml"
_LLM_PROVIDER_MAP: dict[str, LLMProvider] = {
    "openai": LLMProvider.OPENAI,
    "gemini": LLMProvider.GEMINI,
    "bedrock": LLMProvider.BEDROCK,
    "lm_studio": LLMProvider.LM_STUDIO,
}


def _find_config_path() -> Optional[Path]:
    """Locate ``config.yaml`` next to this package or in the CWD.

    Returns:
        Path to the config file, or ``None`` if not found.
    """
    candidates = [
        Path.cwd() / _CONFIG_FILENAME,
        Path(__file__).resolve().parent.parent / _CONFIG_FILENAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _load_yaml_config(path: Path) -> dict[str, Any]:
    """Read and parse a YAML configuration file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed configuration dictionary.
    """
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from file + environment variables.

    Loads ``.env`` file (if present) so that environment variables
    defined there are available via ``os.environ``.
    Environment variables take precedence over file values.
    API keys are loaded **only** from env vars.

    Returns:
        A validated ``AppConfig`` instance.
    """
    load_dotenv()
    file_cfg: dict[str, Any] = {}
    config_path = _find_config_path()
    if config_path is not None:
        logger.info("Loading config from %s", config_path)
        file_cfg = _load_yaml_config(config_path)

    # Resolve default LLM provider
    provider_str = os.environ.get(
        "AI_BROWSER_DEFAULT_LLM",
        file_cfg.get("default_llm", "lm_studio"),
    )
    default_llm = _LLM_PROVIDER_MAP.get(
        provider_str.lower(), LLMProvider.LM_STUDIO,
    )

    return AppConfig(
        default_llm=default_llm,
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_model=os.environ.get(
            "OPENAI_MODEL",
            file_cfg.get("openai_model", "gpt-4"),
        ),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        gemini_model=os.environ.get(
            "GEMINI_MODEL",
            file_cfg.get("gemini_model", "gemini-pro"),
        ),
        bedrock_region=os.environ.get(
            "AWS_DEFAULT_REGION",
            file_cfg.get("bedrock_region"),
        ),
        bedrock_model=os.environ.get(
            "BEDROCK_MODEL",
            file_cfg.get(
                "bedrock_model",
                "anthropic.claude-3-sonnet-20240229-v1:0",
            ),
        ),
        lm_studio_url=os.environ.get(
            "LM_STUDIO_URL",
            file_cfg.get(
                "lm_studio_url", "http://localhost:1234/v1",
            ),
        ),
        lm_studio_model=os.environ.get(
            "LM_STUDIO_MODEL",
            file_cfg.get("lm_studio_model", "local-model"),
        ),
        action_timeout_ms=int(
            os.environ.get(
                "ACTION_TIMEOUT_MS",
                file_cfg.get("action_timeout_ms", 10000),
            ),
        ),
        max_retries=int(
            os.environ.get(
                "MAX_RETRIES",
                file_cfg.get("max_retries", 3),
            ),
        ),
    )


def main() -> None:
    """CLI entry point registered as ``ai-browser`` console script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()
    app = AIBrowserAutomation(config)
    chat = ChatInterface(app)

    try:
        asyncio.run(chat.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()


__all__ = ["load_config", "main"]
