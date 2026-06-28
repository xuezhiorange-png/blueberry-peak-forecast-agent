"""Task 11 rolling backtest persistence errors."""

from __future__ import annotations


class RollingBacktestPersistenceError(Exception):
    """Base exception for rolling backtest persistence failures."""

    code: str = "ROLLING_BACKTEST_PERSISTENCE_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class RollingBacktestIntegrityError(RollingBacktestPersistenceError):
    """Integrity verification failed during reload."""

    code = "ROLLING_BACKTEST_INTEGRITY_ERROR"


class RollingBacktestIdentityConflictError(RollingBacktestPersistenceError):
    """Same run_signature with different payload/hash."""

    code = "ROLLING_BACKTEST_IDENTITY_CONFLICT"


class RollingBacktestChildCountMismatchError(RollingBacktestIntegrityError):
    """Expected child count does not match actual."""

    code = "ROLLING_BACKTEST_CHILD_COUNT_MISMATCH"


class RollingBacktestCanonicalParityError(RollingBacktestIntegrityError):
    """Normalized columns do not match canonical payload."""

    code = "ROLLING_BACKTEST_CANONICAL_PARITY_ERROR"


class RollingBacktestAttemptConflictError(RollingBacktestPersistenceError):
    """Attempt creation conflict (e.g. duplicate number, overwriting completed)."""

    code = "ROLLING_BACKTEST_ATTEMPT_CONFLICT"
