"""Stable, sanitized failure codes for S4 validation-budget persistence."""

from __future__ import annotations


class ValidationBudgetError(RuntimeError):
    """Fail-closed persistence error with a stable governance reason code."""

    status = "BLOCKED"

    def __init__(self, reason_code: str, message: str | None = None) -> None:
        self.reason_code = reason_code
        super().__init__(message or reason_code)


class ValidationBudgetBlocked(ValidationBudgetError):
    """Explicit alias for callers that distinguish a blocked operation."""


__all__ = ["ValidationBudgetBlocked", "ValidationBudgetError"]
