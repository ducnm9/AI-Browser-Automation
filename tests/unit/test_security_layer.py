"""Unit tests for SecurityLayer.

Tests cover all public methods of SecurityLayer against Requirements 5.1–5.6.
"""

from __future__ import annotations

import pytest

from ai_browser_automation.models.config import SecurityPolicy
from ai_browser_automation.security.security_layer import SecurityLayer


@pytest.fixture()
def default_layer() -> SecurityLayer:
    """SecurityLayer with default policy."""
    return SecurityLayer(SecurityPolicy())


@pytest.fixture()
def custom_layer() -> SecurityLayer:
    """SecurityLayer with a custom sensitive pattern."""
    return SecurityLayer(
        SecurityPolicy(sensitive_patterns=[r"SSN-\d{3}-\d{2}-\d{4}"]),
    )


# ── detect_sensitive_data ────────────────────────────────────────────


class TestDetectSensitiveData:
    """Requirement 5.1, 5.4, 5.5."""

    def test_empty_text_returns_empty(
        self, default_layer: SecurityLayer,
    ) -> None:
        assert default_layer.detect_sensitive_data("") == []

    def test_no_sensitive_data(
        self, default_layer: SecurityLayer,
    ) -> None:
        assert default_layer.detect_sensitive_data("hello world") == []

    def test_detects_email(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data(
            "contact: user@example.com",
        )
        assert "user@example.com" in found

    def test_detects_vn_phone_0_prefix(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data("SĐT: 0912345678")
        assert "0912345678" in found

    def test_detects_vn_phone_84_prefix(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data("Phone: +84912345678")
        assert "+84912345678" in found

    def test_detects_credit_card_spaces(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data(
            "Card: 4111 1111 1111 1111",
        )
        assert "4111 1111 1111 1111" in found

    def test_detects_credit_card_dashes(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data(
            "Card: 4111-1111-1111-1111",
        )
        assert "4111-1111-1111-1111" in found

    def test_detects_cmnd_9_digits(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data("CMND: 123456789")
        assert "123456789" in found

    def test_detects_cccd_12_digits(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data(
            "CCCD: 012345678901",
        )
        assert "012345678901" in found

    def test_detects_password_field(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data(
            "password: secret123",
        )
        assert "password: secret123" in found

    def test_detects_pwd_field(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data("pwd=mypass")
        assert "pwd=mypass" in found

    def test_detects_mat_khau(
        self, default_layer: SecurityLayer,
    ) -> None:
        found = default_layer.detect_sensitive_data(
            "mật khẩu: abc123",
        )
        assert "mật khẩu: abc123" in found

    def test_custom_pattern(self, custom_layer: SecurityLayer) -> None:
        found = custom_layer.detect_sensitive_data(
            "ID: SSN-123-45-6789",
        )
        assert "SSN-123-45-6789" in found

    def test_multiple_items(
        self, default_layer: SecurityLayer,
    ) -> None:
        text = "Email: a@b.com, phone: 0912345678"
        found = default_layer.detect_sensitive_data(text)
        assert "a@b.com" in found
        assert "0912345678" in found


# ── sanitize_for_cloud ───────────────────────────────────────────────


class TestSanitizeForCloud:
    """Requirement 5.2."""

    def test_no_sensitive_data(
        self, default_layer: SecurityLayer,
    ) -> None:
        sanitized, mapping = default_layer.sanitize_for_cloud("hello")
        assert sanitized == "hello"
        assert mapping == {}

    def test_replaces_with_placeholders(
        self, default_layer: SecurityLayer,
    ) -> None:
        text = "Email: user@example.com"
        sanitized, mapping = default_layer.sanitize_for_cloud(text)
        assert "user@example.com" not in sanitized
        assert "<<REDACTED_0>>" in sanitized
        assert mapping["<<REDACTED_0>>"] == "user@example.com"

    def test_multiple_items_unique_placeholders(
        self, default_layer: SecurityLayer,
    ) -> None:
        text = "a@b.com and c@d.com"
        sanitized, mapping = default_layer.sanitize_for_cloud(text)
        assert "a@b.com" not in sanitized
        assert "c@d.com" not in sanitized
        assert len(mapping) == 2


# ── restore_sensitive_data ───────────────────────────────────────────


class TestRestoreSensitiveData:
    """Requirement 5.3."""

    def test_roundtrip(
        self, default_layer: SecurityLayer,
    ) -> None:
        text = "My email is user@example.com and phone 0912345678"
        sanitized, mapping = default_layer.sanitize_for_cloud(text)
        restored = default_layer.restore_sensitive_data(
            sanitized, mapping,
        )
        assert restored == text

    def test_empty_mapping(
        self, default_layer: SecurityLayer,
    ) -> None:
        result = default_layer.restore_sensitive_data("hello", {})
        assert result == "hello"


# ── should_use_local_llm ────────────────────────────────────────────


class TestShouldUseLocalLLM:
    """Requirement 5.1 routing."""

    def test_sensitive_with_force_local(
        self, default_layer: SecurityLayer,
    ) -> None:
        assert default_layer.should_use_local_llm(
            "user@example.com",
        ) is True

    def test_clean_text(
        self, default_layer: SecurityLayer,
    ) -> None:
        assert default_layer.should_use_local_llm("hello") is False

    def test_sensitive_without_force_local(self) -> None:
        layer = SecurityLayer(
            SecurityPolicy(force_local_on_sensitive=False),
        )
        assert layer.should_use_local_llm("user@example.com") is False


# ── mask_for_log ─────────────────────────────────────────────────────


class TestMaskForLog:
    """Requirement 5.6."""

    def test_masks_sensitive_data(
        self, default_layer: SecurityLayer,
    ) -> None:
        masked = default_layer.mask_for_log("Email: user@example.com")
        assert "user@example.com" not in masked
        assert "***" in masked

    def test_clean_text_unchanged(
        self, default_layer: SecurityLayer,
    ) -> None:
        assert default_layer.mask_for_log("hello") == "hello"
