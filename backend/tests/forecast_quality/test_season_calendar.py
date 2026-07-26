from datetime import date

from backend.app.forecast_quality.season_calendar import resolve_prior_season_analog_date


def test_eight_calendar_boundaries_and_february_policy() -> None:
    cases = [
        (
            date(2025, 2, 10),
            date(2025, 1, 1),
            date(2025, 3, 31),
            date(2024, 1, 1),
            date(2024, 3, 31),
            date(2024, 2, 10),
        ),
        (
            date(2024, 2, 29),
            date(2024, 1, 1),
            date(2024, 3, 31),
            date(2020, 1, 1),
            date(2020, 3, 31),
            date(2020, 2, 29),
        ),
        (
            date(2024, 2, 29),
            date(2024, 1, 1),
            date(2024, 3, 31),
            date(2023, 1, 1),
            date(2023, 3, 31),
            date(2023, 2, 28),
        ),
        (
            date(2025, 3, 31),
            date(2025, 1, 1),
            date(2025, 3, 31),
            date(2024, 1, 1),
            date(2024, 3, 1),
            None,
        ),
        (
            date(2025, 4, 1),
            date(2025, 1, 1),
            date(2025, 3, 31),
            date(2024, 1, 1),
            date(2024, 3, 31),
            None,
        ),
        (
            date(2025, 1, 1),
            date(2025, 1, 1),
            date(2025, 3, 31),
            date(2024, 1, 1),
            date(2024, 3, 31),
            date(2024, 1, 1),
        ),
        (
            date(2025, 3, 31),
            date(2025, 1, 1),
            date(2025, 3, 31),
            date(2024, 2, 1),
            date(2024, 3, 31),
            None,
        ),
        (
            date(2025, 1, 15),
            date(2025, 1, 1),
            date(2025, 3, 31),
            date(2024, 1, 1),
            date(2024, 3, 31),
            date(2024, 1, 15),
        ),
    ]
    for target, current_start, current_end, prior_start, prior_end, expected in cases:
        assert (
            resolve_prior_season_analog_date(
                current_target_date=target,
                current_season_start=current_start,
                current_season_end=current_end,
                prior_season_start=prior_start,
                prior_season_end=prior_end,
                policy_version="v0.2-s3-season-analog-mapping-v1",
            )
            == expected
        )
