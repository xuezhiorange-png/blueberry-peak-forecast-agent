from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.area_yield.base_product import (
    AreaForecastProductRequest,
    forecast_base_area,
    load_saved_base_forecast_result,
    reload_base_forecast_result,
    save_base_forecast_result,
)
from backend.app.area_yield.base_product_authority import (
    BaseAreaForecastAuthorityError,
    BaseAreaForecastPersistenceError,
    BaseAreaForecastUnsupportedError,
    BaseProductAuthority,
    load_base_product_authority,
)
from backend.app.cli import run_cli


@pytest.fixture(scope="module")
def authority() -> BaseProductAuthority:
    return load_base_product_authority()


def yangliu_request(**updates: str) -> AreaForecastProductRequest:
    payload: dict[str, str] = {
        "base_name": "保山杨柳基地",
        "target_area_mu": "394.000000",
        "target_season": "2025-2026",
    }
    payload.update(updates)
    return AreaForecastProductRequest.model_validate(payload)


def test_reference_registry_is_the_frozen_39_base_snapshot(
    authority: BaseProductAuthority,
) -> None:
    assert len(authority.registry["bases"]) == 39
    assert authority.registry["reference_area_total_mu"] == "41335.000000"
    assert len(authority.bases_by_id) == 39
    assert len(authority.bases_by_name) == 39


def test_frozen_model_artifact_is_loaded_without_fitting(
    authority: BaseProductAuthority,
) -> None:
    temporal = authority.model["temporal_model"]
    assert authority.model["total_model_id"] == "BASE_AWARE_BASELINE_R1"
    assert authority.model["temporal_model_id"] == "AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE"
    assert temporal["model_id"] == "AREA_DAILY_RIDGE_V1"
    assert temporal["fit_season"] == "2023-2024"
    assert temporal["fit_daily_row_count"] == 3042
    assert authority.model["research_artifacts"]["temporal_model_artifact_sha256"] == (
        "d75d691a74f393ed789da2300a2f3194170115d8b4f89cc78c8e5b1fc3a628af"
    )
    assert authority.model["research_artifacts"]["r9_closeout_manifest_sha256"] == (
        "782bb9d33eb100c9ff0c2ac79b46c1d75455cd4d73ea0c142904aedf7082eeb6"
    )


def test_real_yangliu_base_forecast_is_deterministic_and_conserves_total(
    authority: BaseProductAuthority,
) -> None:
    request = yangliu_request()
    first = forecast_base_area(request, authority)
    second = forecast_base_area(request, authority)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.model_status == "EXPERIMENTAL"
    assert first.season_total_status == "EXPERIMENTAL"
    assert first.daily_curve_status == "EXPLORATORY"
    assert first.single_day_peak_status == "EXPLORATORY"
    assert first.rolling_7day_peak_status == "EXPLORATORY"
    assert first.canonical_base_id == "base_a96b297b126a8cab67c4755f"
    assert first.reference_area_mu == "394.000000"
    assert first.target_area_mu == "394.000000"
    assert first.predicted_season_total_kg == "448751.251004"
    assert len(first.daily_curve) == 289
    assert all(len(row.normalized_share.split(".")[1]) == 15 for row in first.daily_curve)
    assert first.daily_curve[0].date == date(2025, 7, 1)
    assert first.daily_curve[-1].date == date(2026, 4, 15)
    assert first.result_hash == second.result_hash
    assert first.mass_balance["pass"] is True
    assert first.metadata["history_harvest_total_kg"] == "448751.251000"
    assert first.metadata["history_source_season"] == "2024-2025"
    assert first.metadata["history_source_sha256"] == (
        "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6"
    )
    assert first.metadata["identity_mapping_sha256"] == (
        "8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044"
    )
    assert abs(
        sum(Decimal(row.normalized_share) for row in first.daily_curve) - Decimal("1")
    ) <= Decimal("1e-12")
    assert first.metadata["peak_at_forecast_boundary"] is True


def test_target_area_scales_total_curve_and_peaks_without_changing_shape(
    authority: BaseProductAuthority,
) -> None:
    reference_area = Decimal("394.000000")
    base = forecast_base_area(yangliu_request(), authority)
    half = forecast_base_area(
        yangliu_request(target_area_mu=format(reference_area / 2, "f")), authority
    )
    one_and_half = forecast_base_area(
        yangliu_request(target_area_mu=format(reference_area * Decimal("1.5"), "f")),
        authority,
    )

    for scaled, factor in ((half, Decimal("0.5")), (one_and_half, Decimal("1.5"))):
        assert scaled.result_hash != base.result_hash
        assert scaled.target_area_mu != base.target_area_mu
        assert [row.normalized_share for row in scaled.daily_curve] == [
            row.normalized_share for row in base.daily_curve
        ]
        assert Decimal(scaled.predicted_season_total_kg) == (
            Decimal(base.predicted_season_total_kg) * factor
        )
        for scaled_row, base_row in zip(scaled.daily_curve, base.daily_curve, strict=True):
            assert abs(
                Decimal(scaled_row.predicted_quantity_kg)
                - Decimal(base_row.predicted_quantity_kg) * factor
            ) <= Decimal("0.000001")
        assert scaled.single_day_peak.date == base.single_day_peak.date
        assert abs(
            Decimal(scaled.single_day_peak.quantity_kg)
            - Decimal(base.single_day_peak.quantity_kg) * factor
        ) <= Decimal("0.000001")
        assert scaled.rolling_7day_peak.start_date == base.rolling_7day_peak.start_date
        assert scaled.rolling_7day_peak.end_date == base.rolling_7day_peak.end_date
        assert abs(
            Decimal(scaled.rolling_7day_peak.cumulative_quantity_kg)
            - Decimal(base.rolling_7day_peak.cumulative_quantity_kg) * factor
        ) <= Decimal("0.000001")


def test_name_and_base_id_resolution_have_identical_results(
    authority: BaseProductAuthority,
) -> None:
    by_name = forecast_base_area(yangliu_request(), authority)
    by_id = forecast_base_area(
        AreaForecastProductRequest(
            base_id="base_a96b297b126a8cab67c4755f",
            target_area_mu="394.000000",
            target_season="2025-2026",
        ),
        authority,
    )
    assert by_name.model_dump(mode="json") == by_id.model_dump(mode="json")


def test_history_provenance_covers_all_registry_bases_and_uses_reconstructed_totals(
    authority: BaseProductAuthority,
) -> None:
    assert len(authority.registry["bases"]) == 39
    assert authority.model["history_provenance"]["base_count"] == 39
    assert authority.model["history_provenance"]["history_row_count"] == 43
    rows = authority.history
    assert len(rows) == 43
    assert len({row["base_id"] for row in rows}) == 30
    assert {row["base_id"] for row in rows} <= set(
        authority.model["history_provenance"]["base_ids"]
    )
    assert authority.model["research_artifacts"]["total_model_source_canonical_hash"] == (
        "76698d128074021117c764a77fa224768a8803fb57ac90ef8a8804dd3213f3e4"
    )
    assert all(
        row["identity_mapping_sha256"]
        == "8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044"
        for row in rows
    )
    assert {row["source_sha256"] for row in rows} == {
        "8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20",
        "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6",
    }
    yangliu = [
        row
        for row in rows
        if row["base_id"] == "base_a96b297b126a8cab67c4755f" and row["season"] == "2024-2025"
    ]
    assert len(yangliu) == 1
    assert yangliu[0]["harvest_total_kg"] == "448751.251000"


def test_temporal_window_diagnostics_do_not_reallocate_clipped_mass(
    authority: BaseProductAuthority,
) -> None:
    full = forecast_base_area(yangliu_request(), authority)
    full_shape = full.metadata["temporal_shape_diagnostics"]
    assert full_shape["temporal_curve_truncated"] is False
    assert full_shape["renormalization_applied"] is False
    assert full_shape["clipped_mass_reallocated"] is False
    assert full_shape["normalized_share_sum_pre_window"] == "1.000000000000000"
    assert full_shape["normalized_share_sum_in_window"] == "1.000000000000000"

    window = forecast_base_area(
        yangliu_request(forecast_start_date="2026-04-01", forecast_end_date="2026-04-15"),
        authority,
    )
    window_shape = window.metadata["temporal_shape_diagnostics"]
    assert window_shape["temporal_curve_truncated"] is True
    assert window_shape["renormalization_applied"] is True
    assert window_shape["clipped_mass_reallocated"] is False
    assert window_shape["normalized_share_sum_in_window"] == "1.000000000000000"
    assert Decimal(window_shape["in_window_share_mass_before_renormalization"]) < 1


def test_unknown_base_and_missing_immediate_prior_fail_closed(
    authority: BaseProductAuthority,
) -> None:
    with pytest.raises(BaseAreaForecastUnsupportedError) as unknown:
        forecast_base_area(
            AreaForecastProductRequest(
                base_name="不存在的基地", target_area_mu="394", target_season="2025-2026"
            ),
            authority,
        )
    assert unknown.value.code == "AREA_FORECAST_UNSUPPORTED_BASE"
    with pytest.raises(BaseAreaForecastUnsupportedError) as missing:
        forecast_base_area(
            AreaForecastProductRequest(
                base_name="保山杨柳基地", target_area_mu="394", target_season="2026-2027"
            ),
            authority,
        )
    assert missing.value.reason == "PRIOR_SEASON_HISTORY_MISSING"


def test_request_rejects_native_float_and_partial_window() -> None:
    with pytest.raises(ValidationError):
        AreaForecastProductRequest(
            base_name="保山杨柳基地", target_area_mu=394.0, target_season="2025-2026"
        )
    with pytest.raises(ValidationError):
        AreaForecastProductRequest(
            base_name="保山杨柳基地",
            target_area_mu="394",
            target_season="2025-2026",
            forecast_start_date="2025-07-01",
        )


def test_save_reload_and_immutable_conflict(
    authority: BaseProductAuthority, tmp_path: Path
) -> None:
    result = forecast_base_area(yangliu_request(), authority)
    path = tmp_path / "yangliu.json"
    save_base_forecast_result(path, result)
    assert load_saved_base_forecast_result(path).model_dump(mode="json") == result.model_dump(
        mode="json"
    )
    save_base_forecast_result(path, result)

    changed = forecast_base_area(yangliu_request(target_area_mu="395.000000"), authority)
    with pytest.raises(BaseAreaForecastPersistenceError) as conflict:
        save_base_forecast_result(path, changed)
    assert conflict.value.code == "AREA_FORECAST_PERSISTENCE_CONFLICT"


def test_reload_integrity_rejects_corrupt_result_hash(
    authority: BaseProductAuthority,
) -> None:
    result = forecast_base_area(yangliu_request(), authority)
    payload = result.model_dump(mode="json")
    payload["result_hash"] = "0" * 64
    with pytest.raises(BaseAreaForecastPersistenceError) as error:
        reload_base_forecast_result(payload)
    assert error.value.code == "AREA_FORECAST_PERSISTENCE_INTEGRITY_ERROR"
    assert error.value.reason == "RESULT_HASH_MISMATCH"


def test_artifact_mutation_is_rejected(tmp_path: Path) -> None:
    source = Path("configs/v0_5_area_forecast_model_v1.json")
    mutated = tmp_path / source.name
    text = source.read_text(encoding="utf-8").replace(
        '"known_base_total_wape": "0.379265725"',
        '"known_base_total_wape": "0.379265726"',
        1,
    )
    mutated.write_text(text, encoding="utf-8")
    with pytest.raises(BaseAreaForecastAuthorityError) as error:
        load_base_product_authority(model_path=mutated)
    assert error.value.code == "AREA_FORECAST_AUTHORITY_UNAVAILABLE"
    assert error.value.reason == "MODEL_ARTIFACT_HASH_MISMATCH"


def test_peak_tie_break_is_earliest_date() -> None:
    from backend.app.area_yield.evaluation import summaries

    dates = [date(2025, 7, 1) + timedelta(days=index) for index in range(8)]
    quantities = [Decimal("1") for _ in dates]
    metrics = summaries(dates, quantities)
    assert metrics["single_day_peak"]["date"] == "2025-07-01"
    assert metrics["rolling_7day_peak"]["start_date"] == "2025-07-01"


def test_cli_base_mode_is_an_additive_formal_entrypoint() -> None:
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_cli(
        [
            "area-forecast",
            "--base",
            "保山杨柳基地",
            "--area-mu",
            "394.000000",
            "--season",
            "2025-2026",
        ],
        stdout=stdout,
        stderr=stderr,
    )
    assert exit_code == 0, stderr.getvalue()
    payload = json.loads(stdout.getvalue())
    assert payload["canonical_base_id"] == "base_a96b297b126a8cab67c4755f"
    assert payload["model_status"] == "EXPERIMENTAL"
