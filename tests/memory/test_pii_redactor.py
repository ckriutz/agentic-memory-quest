"""Unit tests for PII redaction."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "memoryquest_server"))

# Override env before importing the module.
os.environ["PII_REDACTION_ENABLED"] = "true"
os.environ["PII_REDACTION_MODE"] = "mask"

from memory.ingestion.pii_redactor import redact


def test_email_masked():
    result = redact("Contact me at john@example.com please.")
    assert "[REDACTED:EMAIL]" in result.text
    assert "EMAIL" in result.pii_types
    assert result.pii_detected is True


def test_phone_masked():
    result = redact("Call me at 555-123-4567.")
    assert "[REDACTED:PHONE]" in result.text
    assert "PHONE" in result.pii_types


def test_ssn_masked():
    result = redact("My SSN is 123-45-6789.")
    assert "[REDACTED:SSN]" in result.text
    assert "SSN" in result.pii_types


def test_no_pii():
    result = redact("I love hiking in the mountains.")
    assert result.text == "I love hiking in the mountains."
    assert result.pii_detected is False
    assert result.pii_types == []


def test_drop_mode():
    result = redact("Email me at test@example.org ok", mode="drop")
    assert "test@example.org" not in result.text
    assert "[REDACTED" not in result.text


def test_tag_mode():
    result = redact("Email me at test@example.org ok", mode="tag")
    # Text is left intact in tag mode.
    assert "test@example.org" in result.text
    assert result.pii_detected is True


def test_multiple_pii_types():
    result = redact("My email is a@b.com and SSN is 111-22-3333.")
    assert result.pii_detected is True
    assert "EMAIL" in result.pii_types
    assert "SSN" in result.pii_types
