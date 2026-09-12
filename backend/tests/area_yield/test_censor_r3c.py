from datetime import date

from backend.app.area_yield.censor_r3c import evaluation_status


def test_right_censored_peak():
    assert (
        evaluation_status(
            date(2025, 5, 28), date(2025, 5, 28), date(2024, 7, 1), date(2025, 5, 27), False
        )
        == "RIGHT_CENSORED"
    )


def test_cross_boundary_seven_day_window_is_censored():
    assert (
        evaluation_status(
            date(2025, 5, 24), date(2025, 5, 30), date(2024, 7, 1), date(2025, 5, 27), False
        )
        == "RIGHT_CENSORED"
    )


def test_internal_unknown_is_not_right_censor():
    assert (
        evaluation_status(
            date(2025, 1, 28), date(2025, 1, 28), date(2024, 7, 1), date(2025, 5, 27), False
        )
        == "NOT_COMPUTABLE_OTHER"
    )


def test_left_censor_and_exact():
    assert (
        evaluation_status(
            date(2024, 6, 30), date(2024, 6, 30), date(2024, 7, 1), date(2025, 5, 27), False
        )
        == "LEFT_CENSORED"
    )
    assert (
        evaluation_status(
            date(2025, 5, 27), date(2025, 5, 27), date(2024, 7, 1), date(2025, 5, 27), True
        )
        == "EXACT_COMPUTABLE"
    )


def test_missing_or_double_sided_coverage_is_not_exact():
    assert (
        evaluation_status(date(2025, 1, 1), date(2025, 1, 1), None, None, True)
        == "NOT_COMPUTABLE_OTHER"
    )
    assert (
        evaluation_status(
            date(2024, 6, 30), date(2025, 6, 1), date(2024, 7, 1), date(2025, 5, 27), False
        )
        == "NOT_COMPUTABLE_OTHER"
    )
