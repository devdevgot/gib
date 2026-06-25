"""Tests for OpenRouter credit error detection."""
import pytest

from gib.providers.errors import CreditsExhaustedError, is_credits_error


def test_is_credits_error_402():
    assert is_credits_error(402, {"error": "Payment required"})


def test_is_credits_error_insufficient_balance():
    assert is_credits_error(400, {"error": "Insufficient credits balance"})


def test_is_credits_error_normal_400():
    assert not is_credits_error(400, {"error": "Invalid model id"})


def test_credits_exhausted_error_attributes():
    err = CreditsExhaustedError("no credits", status_code=402, details={"x": 1})
    assert err.status_code == 402
    assert err.details == {"x": 1}
