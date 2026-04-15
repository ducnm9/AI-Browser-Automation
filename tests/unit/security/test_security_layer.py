"""Unit tests for SecurityLayer — edge cases and mask_for_log.

Covers Requirements 5.1, 5.5, 5.6 with focus on empty input,
mask_for_log behaviour, and overlapping pattern edge cases.
"""

from __future__ import annotations

import pytest

from ai_browser_automation.models.config import SecurityPolicy
from ai_browser_automation.security.security_layer import SecurityLayer


@pytest.fixture()
def layer() -> SecurityLayer:
    """SecurityLayer with default policy."""
    return SecurityLayer(SecurityPolicy())


# ── Requirement 5.5: empty text ──────────────────────────────────────


class TestEmptyText:
    """Empty text must return empty list without errors."""

    def test_detect_empty_string(self, layer: SecurityLayer) -> None:
        """Req 5.5 — empty string returns []."""
        assert layer.detect_sensitive_data("") == []

    def test_detect_none_like_empty(
        self, layer: SecurityLayer,
    ) -> None:
        """Whitespace-only text has no sensitive data."""
        assert layer.detect_sensitive_data("   ") == []


# ── Requirement 5.6: mask_for_log ────────────────────────────────────


class TestMaskForLog:
    """mask_for_log must replace every sensitive item with ***."""

    def test_masks_email(self, layer: SecurityLayer) -> None:
        masked = layer.mask_for_log("contact user@test.com now")
        assert "user@test.com" not in masked
        assert "***" in masked

    def test_masks_phone(self, layer: SecurityLayer) -> None:
        masked = layer.mask_for_log("call 0912345678 today")
        assert "0912345678" not in masked
        assert "***" in masked

    def test_masks_credit_card(self, layer: SecurityLayer) -> None:
        masked = layer.mask_for_log(
            "card 4111 1111 1111 1111 ok",
        )
        assert "4111 1111 1111 1111" not in masked
        assert "***" in masked

    def test_masks_password(self, layer: SecurityLayer) -> None:
        masked = layer.mask_for_log("password: secret123 end")
        assert "secret123" not in masked
        assert "***" in masked

    def test_masks_multiple_items(
        self, layer: SecurityLayer,
    ) -> None:
        text = "a@b.com and 0912345678"
        masked = layer.mask_for_log(text)
        assert "a@b.com" not in masked
        assert "0912345678" not in masked

    def test_clean_text_unchanged(
        self, layer: SecurityLayer,
    ) -> None:
        assert layer.mask_for_log("hello world") == "hello world"



# ── Edge cases: overlapping / adjacent patterns ──────────────────────


class TestOverlappingPatterns:
    """Edge cases where multiple patterns may overlap."""

    def test_email_containing_digits(
        self, layer: SecurityLayer,
    ) -> None:
        """Email with digits should be detected as email."""
        found = layer.detect_sensitive_data(
            "info user123@test.com end",
        )
        assert "user123@test.com" in found

    def test_password_with_email_value(
        self, layer: SecurityLayer,
    ) -> None:
        """password: user@test.com triggers both patterns."""
        text = "password: user@test.com"
        found = layer.detect_sensitive_data(text)
        assert any(
            "password:" in f or "password: " in f for f in found
        )
        assert "user@test.com" in found

    def test_adjacent_sensitive_items(
        self, layer: SecurityLayer,
    ) -> None:
        """Two sensitive items separated by a single space."""
        text = "data a@b.com 0912345678 end"
        found = layer.detect_sensitive_data(text)
        assert "a@b.com" in found
        assert "0912345678" in found

    def test_cmnd_not_in_longer_number(
        self, layer: SecurityLayer,
    ) -> None:
        """CMND pattern uses word boundary — 15-digit number
        should not produce a 9 or 12 digit match."""
        text = "ref 123456789012345 end"
        found = layer.detect_sensitive_data(text)
        nine_or_twelve = [
            f for f in found
            if len(f) in (9, 12) and f.isdigit()
        ]
        assert nine_or_twelve == []

    def test_sanitize_then_detect_empty(
        self, layer: SecurityLayer,
    ) -> None:
        """After sanitization, detect returns nothing."""
        text = "email a@b.com phone 0912345678"
        sanitized, _ = layer.sanitize_for_cloud(text)
        assert layer.detect_sensitive_data(sanitized) == []
