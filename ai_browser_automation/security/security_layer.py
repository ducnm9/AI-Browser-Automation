"""Security layer for detecting, sanitizing, and restoring sensitive data.

``SecurityLayer`` protects user data by detecting sensitive information
(emails, Vietnamese phone numbers, credit-card numbers, CMND/CCCD, and
password fields), replacing them with redacted placeholders before cloud
transmission, and restoring originals on return.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

import logging
import re

from ai_browser_automation.models.config import SecurityPolicy

logger = logging.getLogger(__name__)

# Built-in patterns for common Vietnamese and international PII.
_BUILTIN_PATTERNS: dict[str, str] = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone_vn": r"(0|\+84)[0-9]{9,10}",
    "credit_card": (
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
    ),
    "cmnd_cccd": r"\b\d{9}(\d{3})?\b",
    "password_field": (
        r"(?i)(password|mật\s*khẩu|pass|pwd)\s*[:=]\s*\S+"
    ),
}


class SecurityLayer:
    """Detect, sanitize, and restore sensitive data in text.

    Args:
        policy: Security policy controlling sensitive-data handling.
    """

    def __init__(self, policy: SecurityPolicy) -> None:
        self.policy = policy

    def detect_sensitive_data(self, text: str) -> list[str]:
        """Detect sensitive data using builtin and custom patterns.

        Args:
            text: The input text to scan.

        Returns:
            A list of matched sensitive strings.
            Empty when *text* is empty.
        """
        if not text:
            return []

        found: list[str] = []

        for pattern in _BUILTIN_PATTERNS.values():
            for match in re.finditer(pattern, text):
                found.append(match.group(0))

        for pattern in self.policy.sensitive_patterns:
            for match in re.finditer(pattern, text):
                found.append(match.group(0))

        return found

    def sanitize_for_cloud(
        self, text: str,
    ) -> tuple[str, dict[str, str]]:
        """Replace sensitive data with ``<<REDACTED_N>>`` placeholders.

        Args:
            text: The input text to sanitize.

        Returns:
            A tuple of *(sanitized_text, mapping)* where *mapping*
            maps each placeholder back to its original value.
        """
        sensitive_items = self.detect_sensitive_data(text)
        mapping: dict[str, str] = {}
        sanitized = text

        for i, item in enumerate(sensitive_items):
            placeholder = f"<<REDACTED_{i}>>"
            mapping[placeholder] = item
            sanitized = sanitized.replace(item, placeholder, 1)

        return sanitized, mapping

    def restore_sensitive_data(
        self, text: str, mapping: dict[str, str],
    ) -> str:
        """Restore original values from *mapping* into *text*.

        Args:
            text: Sanitized text with ``<<REDACTED_N>>`` placeholders.
            mapping: Placeholder-to-original mapping from
                :meth:`sanitize_for_cloud`.

        Returns:
            The original text with all placeholders replaced.
        """
        restored = text
        for placeholder, original in mapping.items():
            restored = restored.replace(placeholder, original)
        return restored

    def should_use_local_llm(self, text: str) -> bool:
        """Decide whether to route to a local LLM.

        Returns ``True`` when sensitive data is detected **and**
        ``policy.force_local_on_sensitive`` is enabled.

        Args:
            text: The input text to evaluate.

        Returns:
            Whether the text should be processed locally.
        """
        if not self.policy.force_local_on_sensitive:
            return False
        return len(self.detect_sensitive_data(text)) > 0

    def mask_for_log(self, text: str) -> str:
        """Mask sensitive data with ``***`` for safe logging.

        Args:
            text: The input text to mask.

        Returns:
            Text with all sensitive items replaced by ``***``.
        """
        sensitive_items = self.detect_sensitive_data(text)
        masked = text
        for item in sensitive_items:
            masked = masked.replace(item, "***", 1)
        return masked
