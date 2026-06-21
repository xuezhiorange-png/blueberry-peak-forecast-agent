from __future__ import annotations

from datetime import date

from backend.app.baseline.schemas import SelectedBuildRun
from backend.app.baseline.signature import source_signature


def test_source_signature_is_stable_regardless_of_input_order() -> None:
    a = SelectedBuildRun(
        season_id=1,
        season_code="2024-2025",
        season_start_date=date(2025, 1, 1),
        build_run_id=10,
        aggregation_version="task3-v1",
        source_max_raw_id=100,
        config_hash="aaa",
    )
    b = SelectedBuildRun(
        season_id=2,
        season_code="2025-2026",
        season_start_date=date(2026, 1, 1),
        build_run_id=20,
        aggregation_version="task3-v1",
        source_max_raw_id=200,
        config_hash="aaa",
    )
    assert source_signature([a, b]) == source_signature([b, a])
