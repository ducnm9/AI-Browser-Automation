"""Property-based tests for AppConfig validation.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

Property 15: Configuration Validation
    For any AppConfig values:
    (a) openai_api_key SHALL be accepted only if it starts with "sk-" or is None,
    (b) lm_studio_url SHALL be a valid URL,
    (c) action_timeout_ms SHALL be in range (0, 60000],
    (d) max_retries SHALL be in range [0, 10].
    Invalid values SHALL be rejected during validation.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from ai_browser_automation.models.config import AppConfig


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

valid_sk_keys: st.SearchStrategy[str] = st.from_regex(r"sk-[A-Za-z0-9]{3,48}", fullmatch=True)

invalid_sk_keys: st.SearchStrategy[str] = st.text(min_size=1).filter(
    lambda s: not s.startswith("sk-")
)

valid_urls: st.SearchStrategy[str] = st.from_regex(
    r"https?://[a-z][a-z0-9]{0,20}(\.[a-z]{2,6}){0,3}(:[0-9]{2,5})?(/[a-z0-9]{0,10}){0,3}",
    fullmatch=True,
)

invalid_urls: st.SearchStrategy[str] = st.text(min_size=1).filter(
    lambda s: "://" not in s
)

valid_timeouts: st.SearchStrategy[int] = st.integers(min_value=1, max_value=60000)

invalid_timeouts: st.SearchStrategy[int] = st.integers().filter(
    lambda v: v <= 0 or v > 60000
)

valid_retries: st.SearchStrategy[int] = st.integers(min_value=0, max_value=10)

invalid_retries: st.SearchStrategy[int] = st.integers().filter(
    lambda v: v < 0 or v > 10
)


# ---------------------------------------------------------------------------
# Property 15a — openai_api_key: valid "sk-..." keys and None are accepted
# **Validates: Requirements 8.1**
# ---------------------------------------------------------------------------


@given(key=st.one_of(valid_sk_keys, st.none()))
@settings(max_examples=100)
def test_valid_openai_api_key_accepted(key: str | None) -> None:
    """Valid openai_api_key (starts with 'sk-' or None) is accepted."""
    config = AppConfig(openai_api_key=key)
    assert config.openai_api_key == key


@given(key=invalid_sk_keys)
@settings(max_examples=100)
def test_invalid_openai_api_key_rejected(key: str) -> None:
    """Non-None key that does not start with 'sk-' is rejected."""
    with pytest.raises(ValidationError):
        AppConfig(openai_api_key=key)


# ---------------------------------------------------------------------------
# Property 15b — lm_studio_url: valid URLs are accepted
# **Validates: Requirements 8.2**
# ---------------------------------------------------------------------------


@given(url=valid_urls)
@settings(max_examples=100)
def test_valid_lm_studio_url_accepted(url: str) -> None:
    """A URL with scheme and host is accepted."""
    config = AppConfig(lm_studio_url=url)
    assert config.lm_studio_url == url


@given(url=invalid_urls)
@settings(max_examples=100)
def test_invalid_lm_studio_url_rejected(url: str) -> None:
    """A string without scheme://host is rejected."""
    with pytest.raises(ValidationError):
        AppConfig(lm_studio_url=url)


# ---------------------------------------------------------------------------
# Property 15c — action_timeout_ms: must be in (0, 60000]
# **Validates: Requirements 8.3**
# ---------------------------------------------------------------------------


@given(timeout=valid_timeouts)
@settings(max_examples=100)
def test_valid_action_timeout_accepted(timeout: int) -> None:
    """Timeout in (0, 60000] is accepted."""
    config = AppConfig(action_timeout_ms=timeout)
    assert config.action_timeout_ms == timeout


@given(timeout=invalid_timeouts)
@settings(max_examples=100)
def test_invalid_action_timeout_rejected(timeout: int) -> None:
    """Timeout outside (0, 60000] is rejected."""
    with pytest.raises(ValidationError):
        AppConfig(action_timeout_ms=timeout)


# ---------------------------------------------------------------------------
# Property 15d — max_retries: must be in [0, 10]
# **Validates: Requirements 8.4**
# ---------------------------------------------------------------------------


@given(retries=valid_retries)
@settings(max_examples=100)
def test_valid_max_retries_accepted(retries: int) -> None:
    """Retries in [0, 10] are accepted."""
    config = AppConfig(max_retries=retries)
    assert config.max_retries == retries


@given(retries=invalid_retries)
@settings(max_examples=100)
def test_invalid_max_retries_rejected(retries: int) -> None:
    """Retries outside [0, 10] are rejected."""
    with pytest.raises(ValidationError):
        AppConfig(max_retries=retries)
