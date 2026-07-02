from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.app.baseline.schemas import BaselineSample, SelectedBuildRun


def select_latest_build_runs(runs: list[SelectedBuildRun]) -> list[SelectedBuildRun]:
    selected: dict[str, SelectedBuildRun] = {}
    for run in sorted(
        runs,
        key=lambda item: (
            item.season_start_date,
            item.season_code,
            item.source_max_raw_id,
            item.build_run_id,
        ),
    ):
        current = selected.get(run.season_code)
        if current is None:
            selected[run.season_code] = run
            continue
        if run.source_max_raw_id > current.source_max_raw_id:
            selected[run.season_code] = run
            continue
        if (
            run.source_max_raw_id == current.source_max_raw_id
            and run.build_run_id > current.build_run_id
        ):
            selected[run.season_code] = run
    return sorted(selected.values(), key=lambda item: item.season_start_date)


def ensure_build_runs_are_consistent(runs: list[SelectedBuildRun]) -> None:
    aggregation_versions = {run.aggregation_version for run in runs}
    if len(aggregation_versions) > 1:
        raise ValueError("Selected build runs must share the same aggregation_version")
    config_hashes = {run.config_hash for run in runs}
    if len(config_hashes) > 1:
        raise ValueError("Selected build runs must share the same config_hash")


def select_source_build_runs(
    *,
    available_runs: list[SelectedBuildRun],
    season_codes: tuple[str, ...] | None,
    explicit_build_run_ids: dict[str, int],
) -> list[SelectedBuildRun]:
    available_by_season: dict[str, list[SelectedBuildRun]] = {}
    for run in available_runs:
        available_by_season.setdefault(run.season_code, []).append(run)

    if season_codes is None:
        target_seasons = tuple(sorted(available_by_season))
    else:
        target_seasons = season_codes
        unexpected = sorted(set(explicit_build_run_ids).difference(target_seasons))
        if unexpected:
            raise ValueError(
                "Explicit build runs provided for seasons outside --season selection: "
                + ", ".join(unexpected)
            )

    selected: list[SelectedBuildRun] = []
    missing = [
        season_code for season_code in target_seasons if season_code not in available_by_season
    ]
    if missing:
        raise ValueError(f"Missing completed Task 3 build runs for seasons: {', '.join(missing)}")

    for season_code in target_seasons:
        candidates = available_by_season[season_code]
        explicit_id = explicit_build_run_ids.get(season_code)
        if explicit_id is not None:
            match = next((run for run in candidates if run.build_run_id == explicit_id), None)
            if match is None:
                raise ValueError(
                    "Explicit build run "
                    f"{explicit_id} does not match completed season {season_code}"
                )
            selected.append(match)
            continue
        selected.append(select_latest_build_runs(candidates)[0])

    ensure_build_runs_are_consistent(selected)
    return sorted(selected, key=lambda item: item.season_start_date)


def source_build_run_payload(build_runs: list[SelectedBuildRun]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "season_id": item.season_id,
            "season_code": item.season_code,
            "build_run_id": item.build_run_id,
            "aggregation_version": item.aggregation_version,
            "source_max_raw_id": item.source_max_raw_id,
            "config_hash": item.config_hash,
        }
        for item in sorted(build_runs, key=lambda row: row.season_start_date)
    )


def rows_to_samples(rows: list[dict[str, Any]]) -> list[BaselineSample]:
    return [
        BaselineSample(
            season_id=int(row["season_id"]),
            season_code=str(row["season_code"]),
            season_start_date=row["season_start_date"],
            factory_id=int(row["factory_id"]),
            factory_name=str(row["factory_name"]),
            build_run_id=int(row["build_run_id"]),
            total_weight_kg=Decimal(str(row["total_weight_kg"])),
            stable_median_3d_peak_kg=Decimal(str(row["stable_median_3d_peak_kg"])),
            peak_concentration=Decimal(str(row["peak_concentration"])),
            variety_hhi=Decimal(str(row["variety_hhi"])),
            farm_hhi=Decimal(str(row["farm_hhi"])),
            subfarm_hhi=Decimal(str(row["subfarm_hhi"])),
            single_day_peak_kg=Decimal(str(row["single_day_peak_kg"])),
        )
        for row in rows
    ]
