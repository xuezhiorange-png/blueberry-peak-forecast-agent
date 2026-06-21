from __future__ import annotations

from datetime import date

import pytest

from backend.app.baseline.dataset import (
    ensure_build_runs_are_consistent,
    select_latest_build_runs,
)
from backend.app.baseline.schemas import SelectedBuildRun


def _run(
    *,
    season_id: int,
    season_code: str,
    season_start_date: date,
    build_run_id: int,
    aggregation_version: str = "task3-v1",
    source_max_raw_id: int = 100,
    config_hash: str = "cfg-a",
) -> SelectedBuildRun:
    return SelectedBuildRun(
        season_id=season_id,
        season_code=season_code,
        season_start_date=season_start_date,
        build_run_id=build_run_id,
        aggregation_version=aggregation_version,
        source_max_raw_id=source_max_raw_id,
        config_hash=config_hash,
    )


def test_select_latest_build_runs_prefers_highest_cutoff_then_id() -> None:
    runs = [
        _run(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            build_run_id=10,
            source_max_raw_id=100,
        ),
        _run(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            build_run_id=11,
            source_max_raw_id=150,
        ),
        _run(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            build_run_id=20,
            source_max_raw_id=200,
        ),
        _run(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            build_run_id=21,
            source_max_raw_id=200,
        ),
    ]
    selected = select_latest_build_runs(runs)
    assert [row.build_run_id for row in selected] == [11, 21]


def test_select_latest_build_runs_prefers_higher_id_when_cutoff_matches() -> None:
    runs = [
        _run(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            build_run_id=100,
            source_max_raw_id=199,
            config_hash="task3-cfg",
        ),
        _run(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            build_run_id=101,
            source_max_raw_id=200,
            config_hash="task3-old-cfg",
        ),
        _run(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            build_run_id=102,
            source_max_raw_id=200,
            config_hash="task3-cfg",
        ),
    ]
    selected = select_latest_build_runs(runs)
    assert len(selected) == 1
    assert selected[0].build_run_id == 102
    assert selected[0].config_hash == "task3-cfg"


def test_consistency_check_rejects_mixed_aggregation_version() -> None:
    runs = [
        _run(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            build_run_id=10,
            aggregation_version="task3-v1",
        ),
        _run(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            build_run_id=20,
            aggregation_version="task3-v2",
        ),
    ]
    with pytest.raises(ValueError, match="aggregation_version"):
        ensure_build_runs_are_consistent(runs)


def test_consistency_check_rejects_mixed_config_hash() -> None:
    runs = [
        _run(
            season_id=1,
            season_code="2024-2025",
            season_start_date=date(2025, 1, 1),
            build_run_id=10,
            config_hash="cfg-a",
        ),
        _run(
            season_id=2,
            season_code="2025-2026",
            season_start_date=date(2026, 1, 1),
            build_run_id=20,
            config_hash="cfg-b",
        ),
    ]
    with pytest.raises(ValueError, match="config_hash"):
        ensure_build_runs_are_consistent(runs)
