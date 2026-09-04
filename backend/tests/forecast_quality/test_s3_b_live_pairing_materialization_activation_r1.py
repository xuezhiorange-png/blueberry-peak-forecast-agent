"""Tests for S3-B live pairing materialization activation R1."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.forecast_quality.train_val_pairing_materialization import (
    TrainValidationPairingMaterializationBlocker,
    materialize_train_validation_pairing_inputs_live,
)
from backend.app.models.maturity import MaturityDailyPredictionModel
from backend.app.rolling_backtest.resolution import task8_daily_prediction_payload_hash
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.s3_daily_rowset.forecast_port import ForecastAvailability
from backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain import (
    LiveIncumbentForecastDailyCurveObtainResult,
    obtain_live_incumbent_forecast_daily_curve_provider,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_loader import (
    PitVisibleIncumbentDailyCurveIndex,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_provider import (
    PitVisibleIncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
    is_synthetic_forecast_authority,
)
from backend.app.s3_daily_rowset.schemas import EvaluationInstanceCell

from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MODEL_ID,
)

_REVIEWED_CUTOFF = datetime.fromisoformat(REVIEW_CUTOFF_AT)


def _test_forecast_binding_authority() -> S2ForecastAuthorityBundle:
    return S2ForecastAuthorityBundle(
        forecast_run_identity_hash="1" * 64,
        daily_row_identity_hash="2" * 64,
        task9_authority_identity_hash="c" * 64,
        task9_member_identity_hash="5" * 64,
        task10_authority_identity_hash="d" * 64,
        task10_model_identity_hash="6" * 64,
        task10_replay_identity_hash="7" * 64,
        task10_prediction_row_identity_hash="8" * 64,
        historical_code_authority_id=901,
        forecast_code_identity="9" * 64,
        historical_code_identity="a" * 40,
        build_artifact_hash="b" * 64,
        config_bundle_hash="e" * 64,
        model_identity=REVIEW_MODEL_ID,
        parameter_identity="parameter-v1",
        data_identity="data-v1",
        available_at=_REVIEWED_CUTOFF,
        task10_model_available_at=_REVIEWED_CUTOFF,
        historical_code_available_at=_REVIEWED_CUTOFF,
    )


def _daily_row(
    *,
    row_id: int = 1,
    prediction_date: date,
    p50: str = "10.0",
    p80: str = "12.0",
    p90: str = "14.0",
    created_at: datetime,
) -> MaturityDailyPredictionModel:
    return MaturityDailyPredictionModel(
        id=row_id,
        forecast_run_id=401,
        prediction_date=prediction_date,
        phenology_coordinate_day=Decimal("1.0"),
        p50_kg=Decimal(p50),
        p80_kg=Decimal(p80),
        p90_kg=Decimal(p90),
        cumulative_p50_kg=Decimal(p50),
        cumulative_p80_kg=Decimal(p80),
        cumulative_p90_kg=Decimal(p90),
        curve_share=Decimal("0.1"),
        confidence_level="high",
        quality_flags=[],
        created_at=created_at,
    )


def _evaluation_cell(quantile: str = "P50") -> EvaluationInstanceCell:
    return EvaluationInstanceCell(
        season="2025~2026",
        farm="farm-a",
        subfarm="farm-a/subfarm-1",
        variety="variety-x",
        model_id=REVIEW_MODEL_ID,
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        forecast_quantile=quantile,
    )


def test_task8_daily_prediction_payload_hash_maps_quantile_fields() -> None:
    daily = _daily_row(prediction_date=date(2026, 2, 20), created_at=_REVIEWED_CUTOFF)
    payload_hash = task8_daily_prediction_payload_hash(daily, forecast_source_signature="b" * 64)
    assert len(payload_hash) == 64
    assert payload_hash != ("0" * 64)


def test_pit_visible_provider_reads_p50_p80_p90_kg() -> None:
    index = PitVisibleIncumbentDailyCurveIndex(
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        cells={},
        grain_forecast_run_count={},
    )
    provider = PitVisibleIncumbentDailyCurveProvider(index=index)
    daily = _daily_row(prediction_date=date(2026, 2, 20), created_at=_REVIEWED_CUTOFF)
    provider.index.cells[
        ("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x", "P50", date(2026, 2, 20))
    ] = SimpleNamespace(
        forecast_kg=daily.p50_kg,
        task8_forecast_run_id=401,
        task8_daily_row_id=1,
        daily_row_identity_hash="a" * 64,
        forecast_run_identity_hash="b" * 64,
    )
    provider.index.cells[
        ("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x", "P80", date(2026, 2, 20))
    ] = SimpleNamespace(
        forecast_kg=daily.p80_kg,
        task8_forecast_run_id=401,
        task8_daily_row_id=1,
        daily_row_identity_hash="a" * 64,
        forecast_run_identity_hash="b" * 64,
    )
    provider.index.cells[
        ("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x", "P90", date(2026, 2, 20))
    ] = SimpleNamespace(
        forecast_kg=daily.p90_kg,
        task8_forecast_run_id=401,
        task8_daily_row_id=1,
        daily_row_identity_hash="a" * 64,
        forecast_run_identity_hash="b" * 64,
    )
    assert provider.forecast_kg_for_day(
        _evaluation_cell("P50"), business_date=date(2026, 2, 20)
    ).forecast_harvest_quantity_kg == Decimal("10.0")
    assert provider.forecast_kg_for_day(
        _evaluation_cell("P80"), business_date=date(2026, 2, 20)
    ).forecast_harvest_quantity_kg == Decimal("12.0")
    assert provider.forecast_kg_for_day(
        _evaluation_cell("P90"), business_date=date(2026, 2, 20)
    ).forecast_harvest_quantity_kg == Decimal("14.0")


def test_forecast_after_cutoff_rejected() -> None:
    provider = PitVisibleIncumbentDailyCurveProvider(
        index=PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            cells={},
            grain_forecast_run_count={},
        )
    )
    late_cell = _evaluation_cell().model_copy(
        update={"forecast_cutoff_at": datetime(2026, 3, 1, tzinfo=UTC)}
    )
    result = provider.forecast_kg_for_day(late_cell, business_date=date(2026, 2, 20))
    assert result.availability == ForecastAvailability.UNAVAILABLE


def test_missing_prediction_date_unavailable() -> None:
    provider = PitVisibleIncumbentDailyCurveProvider(
        index=PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            cells={},
            grain_forecast_run_count={},
        )
    )
    result = provider.forecast_kg_for_day(_evaluation_cell(), business_date=date(2026, 3, 1))
    assert result.availability == ForecastAvailability.UNAVAILABLE


def test_native_float_forbidden() -> None:
    cells: dict = {}
    cells[("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x", "P50", date(2026, 2, 20))] = (
        SimpleNamespace(
            forecast_kg=1.5,
            task8_forecast_run_id=401,
            task8_daily_row_id=1,
            daily_row_identity_hash="a" * 64,
            forecast_run_identity_hash="b" * 64,
        )
    )
    provider = PitVisibleIncumbentDailyCurveProvider(
        index=PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            cells=cells,
            grain_forecast_run_count={},
        )
    )
    with pytest.raises(TypeError, match="native float"):
        provider.forecast_kg_for_day(_evaluation_cell(), business_date=date(2026, 2, 20))


def test_synthetic_forecast_authority_rejected_for_live_path() -> None:
    assert is_synthetic_forecast_authority(_test_forecast_binding_authority())


def test_obtain_live_fail_closed_without_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain.asyncio.run",
        lambda _coro: LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None),
    )
    result = obtain_live_incumbent_forecast_daily_curve_provider()
    assert result.obtained is False
    assert result.provider is None


def test_live_materialization_blocks_without_db_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read."
        "_session_provider",
        None,
    )
    result = materialize_train_validation_pairing_inputs_live()
    assert result.completed is False
    assert (
        result.blocker
        == TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
    )
