from __future__ import annotations

from backend.app.baseline.schemas import SelectedBuildRun


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
