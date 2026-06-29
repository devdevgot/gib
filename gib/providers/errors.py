"""OpenRouter / provider errors."""
from __future__ import annotations

from typing import Any

_CREDIT_KEYWORDS = (
    "credit",
    "credits",
    "balance",
    "payment",
    "billing",
    "insufficient",
    "quota",
    "afford",
    "purchase",
    "top up",
    "top-up",
    "out of funds",
    "not enough",
)


class CreditsExhaustedError(RuntimeError):
    """Raised when OpenRouter rejects a request due to missing credits."""

    def __init__(self, message: str, *, status_code: int | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


def is_credits_error(status_code: int, body: Any) -> bool:
    """Detect OpenRouter credit / billing errors."""
    if status_code == 402:
        return True
    text = str(body).lower()
    if status_code in (400, 403, 429) and any(kw in text for kw in _CREDIT_KEYWORDS):
        return True
    return False


def is_rate_limit_error(status_code: int, body: Any) -> bool:
    """Detect rate limit (429) that is not a billing/credits error."""
    if status_code != 429:
        return False
    return not is_credits_error(status_code, body)
