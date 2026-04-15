"""Natural-language processor for extracting user intents.

``NLProcessor`` analyses free-form user commands (Vietnamese or English),
extracts structured ``ParsedIntent`` objects via an LLM, and generates
clarification questions when the input is ambiguous.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

from __future__ import annotations

import json
import logging

from ai_browser_automation.exceptions.errors import NLProcessingError
from ai_browser_automation.llm.base import LLMRequest, LLMResponse
from ai_browser_automation.llm.router import LLMRouter
from ai_browser_automation.models.intents import IntentType, ParsedIntent
from ai_browser_automation.security.security_layer import SecurityLayer

logger = logging.getLogger(__name__)

_PARSE_PROMPT_TEMPLATE = """\
You are an intent parser for a browser automation system.
Analyse the following user command and extract structured intents.

Return ONLY valid JSON (no markdown fences) with this schema:
{{
  "intents": [
    {{
      "intent_type": "<one of: navigate, click, type_text, \
extract_data, login, scroll, wait, screenshot, composite>",
      "target_description": "<natural-language description>",
      "parameters": {{}},
      "confidence": <float 0.0-1.0>,
      "sub_intents": []
    }}
  ]
}}

Rules:
- If the command contains multiple combined actions, return a \
single intent with intent_type "composite" and populate sub_intents.
- Each sub_intent follows the same schema (no nested sub_intents).
- confidence must be between 0.0 and 1.0.
- Always return at least one intent.

User command: {user_input}
"""

_CLARIFY_PROMPT_TEMPLATE = """\
You are a helpful assistant for a browser automation system.
The user gave a command that is ambiguous. Generate a short, \
friendly clarification question addressing the listed ambiguities.

User command: {user_input}
Ambiguities: {ambiguities}

Return ONLY the clarification question as plain text.
"""


class NLProcessor:
    """Parse natural-language commands into structured intents.

    Args:
        llm_router: Router used to send prompts to an LLM provider.
        security: Security layer for sensitive-data detection
            and sanitisation.
    """

    def __init__(
        self,
        llm_router: LLMRouter,
        security: SecurityLayer,
    ) -> None:
        self.llm_router = llm_router
        self.security = security

    async def parse(
        self, user_input: str,
    ) -> list[ParsedIntent]:
        """Analyse *user_input* and return a non-empty intent list.

        Args:
            user_input: Raw natural-language command from the user.

        Returns:
            A non-empty list of ``ParsedIntent`` objects.

        Raises:
            NLProcessingError: When *user_input* is empty/whitespace
                or the LLM response cannot be parsed.
        """
        cleaned = user_input.strip()
        if not cleaned:
            raise NLProcessingError(
                "Input must not be empty or whitespace-only."
            )

        is_sensitive = self.security.should_use_local_llm(cleaned)
        if is_sensitive:
            text_for_llm, mapping = (
                self.security.sanitize_for_cloud(cleaned)
            )
        else:
            text_for_llm = cleaned
            mapping = {}

        prompt = _PARSE_PROMPT_TEMPLATE.format(
            user_input=text_for_llm,
        )

        logger.debug(
            "Sending parse request: %s",
            self.security.mask_for_log(cleaned),
        )

        try:
            response: LLMResponse = await self.llm_router.route(
                LLMRequest(
                    prompt=prompt,
                    is_sensitive=is_sensitive,
                ),
            )
        except Exception as exc:
            raise NLProcessingError(
                f"LLM request failed: {exc}"
            ) from exc

        content = response.content.strip()
        if is_sensitive and mapping:
            content = self.security.restore_sensitive_data(
                content, mapping,
            )

        return self._parse_response(content)

    async def clarify(
        self,
        user_input: str,
        ambiguities: list[str],
    ) -> str:
        """Generate a clarification question for ambiguous input.

        Args:
            user_input: The original user command.
            ambiguities: Descriptions of what is unclear.

        Returns:
            A clarification question string.

        Raises:
            NLProcessingError: When the LLM call fails.
        """
        prompt = _CLARIFY_PROMPT_TEMPLATE.format(
            user_input=user_input,
            ambiguities=", ".join(ambiguities),
        )

        try:
            response: LLMResponse = await self.llm_router.route(
                LLMRequest(prompt=prompt),
            )
        except Exception as exc:
            raise NLProcessingError(
                f"Clarification request failed: {exc}"
            ) from exc

        return response.content.strip()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_response(
        self, content: str,
    ) -> list[ParsedIntent]:
        """Convert raw LLM JSON into ``ParsedIntent`` objects.

        Args:
            content: JSON string returned by the LLM.

        Returns:
            A non-empty list of parsed intents.

        Raises:
            NLProcessingError: On invalid JSON or missing fields.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise NLProcessingError(
                f"Failed to parse LLM response as JSON: {exc}"
            ) from exc

        raw_intents = data.get("intents")
        if (
            not isinstance(raw_intents, list)
            or len(raw_intents) == 0
        ):
            raise NLProcessingError(
                "LLM response must contain a non-empty "
                "'intents' list."
            )

        return [self._build_intent(raw) for raw in raw_intents]

    def _build_intent(self, raw: dict) -> ParsedIntent:
        """Build a single ``ParsedIntent`` from a raw dict.

        Args:
            raw: Dictionary with intent fields from the LLM.

        Returns:
            A validated ``ParsedIntent``.

        Raises:
            NLProcessingError: On invalid or missing fields.
        """
        try:
            intent_type = IntentType(raw["intent_type"])
        except (KeyError, ValueError) as exc:
            raise NLProcessingError(
                f"Invalid or missing intent_type: {exc}"
            ) from exc

        target = raw.get("target_description", "")
        params = raw.get("parameters", {})
        confidence = self._clamp_confidence(
            raw.get("confidence", 0.0),
        )

        sub_intents: list[ParsedIntent] = []
        if intent_type is IntentType.COMPOSITE:
            raw_subs = raw.get("sub_intents", [])
            if isinstance(raw_subs, list):
                sub_intents = [
                    self._build_intent(s) for s in raw_subs
                ]

        return ParsedIntent(
            intent_type=intent_type,
            target_description=target,
            parameters=params,
            confidence=confidence,
            sub_intents=sub_intents,
        )

    @staticmethod
    def _clamp_confidence(value: object) -> float:
        """Clamp *value* to the ``[0.0, 1.0]`` range.

        Args:
            value: Raw confidence value from the LLM.

        Returns:
            A float clamped between 0.0 and 1.0.
        """
        try:
            f = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))


__all__ = ["NLProcessor"]
