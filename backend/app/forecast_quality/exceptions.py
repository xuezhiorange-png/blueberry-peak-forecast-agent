from __future__ import annotations


class ForecastQualityError(Exception):
    """Base error for fail-closed domain contract violations."""


class S3StructuralDuplicateError(ForecastQualityError):
    """Raised when a physical or forecast business key conflicts."""


class S3DecimalAssertionError(ForecastQualityError):
    """Raised when a business numeric is not a finite Decimal."""


class S3CanonicalIdentityConflictError(ForecastQualityError, ValueError):
    """Raised when canonical identity evidence disagrees."""


class S3ContractInvariantViolationError(ForecastQualityError, ValueError):
    """Raised when a frozen schema or nullability invariant is violated."""
