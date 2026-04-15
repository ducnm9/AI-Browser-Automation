"""Property-based tests for SecurityLayer.

Uses hypothesis to verify correctness properties 9–12 from the design
document against Requirements 5.1–5.4.
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from ai_browser_automation.models.config import SecurityPolicy
from ai_browser_automation.security.security_layer import SecurityLayer


# ── Strategies ───────────────────────────────────────────────────────

_email_st = st.from_regex(
    r"[a-z]{3,8}@[a-z]{3,8}\.[a-z]{2,4}", fullmatch=True,
)
_phone_vn_st = st.from_regex(
    r"(0|\+84)[0-9]{9,10}", fullmatch=True,
)
_credit_card_st = st.from_regex(
    r"\d{4} \d{4} \d{4} \d{4}", fullmatch=True,
)
_cmnd_st = st.one_of(
    st.from_regex(r"\d{9}", fullmatch=True),
    st.from_regex(r"\d{12}", fullmatch=True),
)
_password_st = st.from_regex(
    r"password: [a-zA-Z0-9]{4,12}", fullmatch=True,
)

# Filler text that won't accidentally match sensitive patterns.
_filler_st = st.from_regex(r"[A-Z][a-z]{2,10}", fullmatch=True)


# ── Property 9: Sensitive Data Detection Completeness ────────────────


class TestDetectionCompleteness:
    """**Validates: Requirement 5.1**"""

    layer = SecurityLayer(SecurityPolicy())

    @given(email=_email_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_detects_email(self, email: str, filler: str) -> None:
        """Emails are always detected."""
        text = f"{filler} {email} {filler}"
        found = self.layer.detect_sensitive_data(text)
        assert email in found

    @given(phone=_phone_vn_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_detects_vn_phone(
        self, phone: str, filler: str,
    ) -> None:
        """Vietnamese phone numbers are always detected."""
        text = f"{filler} {phone} {filler}"
        found = self.layer.detect_sensitive_data(text)
        assert any(phone in f for f in found)

    @given(card=_credit_card_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_detects_credit_card(
        self, card: str, filler: str,
    ) -> None:
        """Credit card numbers are always detected."""
        text = f"{filler} {card} {filler}"
        found = self.layer.detect_sensitive_data(text)
        assert card in found

    @given(cmnd=_cmnd_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_detects_cmnd_cccd(
        self, cmnd: str, filler: str,
    ) -> None:
        """CMND/CCCD numbers are always detected."""
        text = f"{filler} {cmnd} {filler}"
        found = self.layer.detect_sensitive_data(text)
        assert cmnd in found

    @given(pwd=_password_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_detects_password_field(
        self, pwd: str, filler: str,
    ) -> None:
        """Password fields are always detected."""
        text = f"{filler} {pwd} {filler}"
        found = self.layer.detect_sensitive_data(text)
        assert any(pwd in f for f in found)



# ── Property 10: Sanitization Removes All Sensitive Patterns ─────────


class TestSanitizationRemovesAll:
    """**Validates: Requirement 5.2**"""

    layer = SecurityLayer(SecurityPolicy())

    @given(email=_email_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_sanitized_has_no_email(
        self, email: str, filler: str,
    ) -> None:
        """After sanitization, no email pattern remains."""
        text = f"{filler} {email} {filler}"
        sanitized, _ = self.layer.sanitize_for_cloud(text)
        assert self.layer.detect_sensitive_data(sanitized) == []

    @given(phone=_phone_vn_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_sanitized_has_no_phone(
        self, phone: str, filler: str,
    ) -> None:
        """After sanitization, no VN phone pattern remains."""
        text = f"{filler} {phone} {filler}"
        sanitized, _ = self.layer.sanitize_for_cloud(text)
        assert self.layer.detect_sensitive_data(sanitized) == []

    @given(card=_credit_card_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_sanitized_has_no_credit_card(
        self, card: str, filler: str,
    ) -> None:
        """After sanitization, no credit card pattern remains."""
        text = f"{filler} {card} {filler}"
        sanitized, _ = self.layer.sanitize_for_cloud(text)
        assert self.layer.detect_sensitive_data(sanitized) == []

    @given(pwd=_password_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_sanitized_has_no_password(
        self, pwd: str, filler: str,
    ) -> None:
        """After sanitization, no password pattern remains."""
        text = f"{filler} {pwd} {filler}"
        sanitized, _ = self.layer.sanitize_for_cloud(text)
        assert self.layer.detect_sensitive_data(sanitized) == []


# ── Property 11: Sanitize/Restore Round-Trip ─────────────────────────


class TestSanitizeRestoreRoundTrip:
    """**Validates: Requirement 5.3**"""

    layer = SecurityLayer(SecurityPolicy())

    @given(email=_email_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_roundtrip_email(
        self, email: str, filler: str,
    ) -> None:
        """sanitize then restore returns original text (email)."""
        text = f"{filler} {email} {filler}"
        sanitized, mapping = self.layer.sanitize_for_cloud(text)
        restored = self.layer.restore_sensitive_data(
            sanitized, mapping,
        )
        assert restored == text

    @given(phone=_phone_vn_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_roundtrip_phone(
        self, phone: str, filler: str,
    ) -> None:
        """sanitize then restore returns original text (phone)."""
        text = f"{filler} {phone} {filler}"
        sanitized, mapping = self.layer.sanitize_for_cloud(text)
        restored = self.layer.restore_sensitive_data(
            sanitized, mapping,
        )
        assert restored == text

    @given(card=_credit_card_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_roundtrip_credit_card(
        self, card: str, filler: str,
    ) -> None:
        """sanitize then restore returns original text (card)."""
        text = f"{filler} {card} {filler}"
        sanitized, mapping = self.layer.sanitize_for_cloud(text)
        restored = self.layer.restore_sensitive_data(
            sanitized, mapping,
        )
        assert restored == text

    @given(pwd=_password_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_roundtrip_password(
        self, pwd: str, filler: str,
    ) -> None:
        """sanitize then restore returns original text (password)."""
        text = f"{filler} {pwd} {filler}"
        sanitized, mapping = self.layer.sanitize_for_cloud(text)
        restored = self.layer.restore_sensitive_data(
            sanitized, mapping,
        )
        assert restored == text

    @given(filler=_filler_st)
    @settings(max_examples=30)
    def test_roundtrip_no_sensitive(self, filler: str) -> None:
        """Round-trip on clean text is identity."""
        text = f"{filler} {filler}"
        sanitized, mapping = self.layer.sanitize_for_cloud(text)
        restored = self.layer.restore_sensitive_data(
            sanitized, mapping,
        )
        assert restored == text


# ── Property 12: Custom Sensitive Patterns ───────────────────────────


_custom_pattern = r"CUST-\d{4,8}"
_custom_value_st = st.from_regex(
    r"CUST-\d{4,8}", fullmatch=True,
)


class TestCustomSensitivePatterns:
    """**Validates: Requirement 5.4**"""

    layer = SecurityLayer(
        SecurityPolicy(sensitive_patterns=[_custom_pattern]),
    )

    @given(
        custom=_custom_value_st,
        email=_email_st,
        filler=_filler_st,
    )
    @settings(max_examples=50)
    def test_detects_custom_and_builtin(
        self,
        custom: str,
        email: str,
        filler: str,
    ) -> None:
        """Both custom and builtin matches are returned."""
        text = f"{filler} {custom} {filler} {email} {filler}"
        found = self.layer.detect_sensitive_data(text)
        assert custom in found
        assert email in found

    @given(custom=_custom_value_st, filler=_filler_st)
    @settings(max_examples=50)
    def test_custom_only(
        self, custom: str, filler: str,
    ) -> None:
        """Custom pattern alone is detected."""
        text = f"{filler} {custom} {filler}"
        found = self.layer.detect_sensitive_data(text)
        assert custom in found
