from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.train_maturity_curve import _manifest_rows, _normalize_csv_row


def test_normalize_csv_row_maps_nullable_empty_values_to_none() -> None:
    normalized = _normalize_csv_row(
        {
            "subfarm_id": "",
            "exclusion_reason": "",
        }
    )

    assert normalized["subfarm_id"] is None
    assert normalized["exclusion_reason"] is None


def test_normalize_csv_row_maps_nullable_whitespace_to_none() -> None:
    normalized = _normalize_csv_row(
        {
            "subfarm_id": "   ",
            "exclusion_reason": "  ",
        }
    )

    assert normalized["subfarm_id"] is None
    assert normalized["exclusion_reason"] is None


def test_manifest_rows_parses_nullable_and_required_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "\n".join(
            [
                "season_id,analytics_build_run_id,farm_key,farm_id,subfarm_key,subfarm_id,variety_id,location_reference_id,production_plan_id,base_temperature_search_run_id,anchor_event,facility_type,include,sample_weight,exclusion_reason",
                "1,101,farm-a,1,__UNKNOWN_SUBFARM__,,2,11,201,301,flowering_start_date,open_field,true,1,",
                "2,102,farm-b,2,sf-1,123,3,12,202,302,flowering_start_date,greenhouse,true,2.5,manual",
            ]
        ),
        encoding="utf-8",
    )

    rows = _manifest_rows(manifest)

    assert rows[0].subfarm_id is None
    assert rows[0].exclusion_reason is None
    assert rows[1].subfarm_id == 123
    assert rows[1].exclusion_reason == "manual"


def test_manifest_rows_still_rejects_missing_required_field(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "\n".join(
            [
                "season_id,analytics_build_run_id,farm_key,farm_id,subfarm_key,subfarm_id,variety_id,location_reference_id,production_plan_id,base_temperature_search_run_id,anchor_event,facility_type,include,sample_weight,exclusion_reason",
                ",101,farm-a,1,__UNKNOWN_SUBFARM__,,2,11,201,301,flowering_start_date,open_field,true,1,",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        _manifest_rows(manifest)
