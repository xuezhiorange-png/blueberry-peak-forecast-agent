"""Coverage-aware disposition, not an estimate of unobserved true peaks."""

from datetime import date


def evaluation_status(
    start: date,
    end: date,
    coverage_start: date | None,
    coverage_end: date | None,
    known: bool,
) -> str:
    if (
        coverage_start is None
        or coverage_end is None
        or coverage_start > coverage_end
        or start > end
    ):
        return "NOT_COMPUTABLE_OTHER"
    if start < coverage_start and end > coverage_end:
        return "NOT_COMPUTABLE_OTHER"
    if end > coverage_end:
        return "RIGHT_CENSORED"
    if start < coverage_start:
        return "LEFT_CENSORED"
    return "EXACT_COMPUTABLE" if known else "NOT_COMPUTABLE_OTHER"
