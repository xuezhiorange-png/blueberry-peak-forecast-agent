from __future__ import annotations

from datetime import date, timedelta


def deterministic_season_day_index(
    target_date: date, season_start: date, season_end: date
) -> int | None:
    if season_start > season_end or target_date < season_start or target_date > season_end:
        return None
    return (target_date - season_start).days


def resolve_prior_season_analog_date(
    *,
    current_target_date: date,
    current_season_start: date,
    current_season_end: date,
    prior_season_start: date,
    prior_season_end: date,
    policy_version: str,
) -> date | None:
    del policy_version
    index = deterministic_season_day_index(
        current_target_date, current_season_start, current_season_end
    )
    if index is None or prior_season_start > prior_season_end:
        return None
    if current_target_date.month == 2 and current_target_date.day == 29:
        february_twenty_ninth = date(prior_season_start.year, 2, 28)
        try:
            february_twenty_ninth = date(prior_season_start.year, 2, 29)
        except ValueError:
            pass
        candidate = february_twenty_ninth
    else:
        candidate = prior_season_start + timedelta(days=index)
    if candidate < prior_season_start or candidate > prior_season_end:
        return None
    return candidate
