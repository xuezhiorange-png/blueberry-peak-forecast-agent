from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.harvest_state.canonical import make_source_ref_hash
from backend.app.harvest_state.schemas import (
    SourceRefCatalogEntry,
    Task8PredictionSourceRef,
    Task8PredictionVerificationSnapshot,
)
from backend.app.rolling_backtest.orchestration import _validate_source_ref_catalog


def _task8_source_ref(
    *,
    forecast_quantile: str = "P50",
    source_quantity: str = "10",
) -> Task8PredictionSourceRef:
    return Task8PredictionSourceRef.model_validate(
        {
            "maturity_model_run_id": 11,
            "maturity_model_version": "task8-v1",
            "maturity_model_config_hash": "a" * 64,
            "maturity_model_source_signature": "b" * 64,
            "maturity_model_artifact_id": 22,
            "maturity_model_artifact_hash": "c" * 64,
            "maturity_forecast_run_id": 33,
            "maturity_forecast_source_signature": "d" * 64,
            "maturity_forecast_as_of_date": "2026-03-15",
            "maturity_daily_prediction_id": 44,
            "prediction_date": "2026-03-16",
            "forecast_quantile": forecast_quantile,
            "source_quantity_kg": source_quantity,
            "plan_id": 55,
            "location_reference_id": 66,
            "weather_mapping_id": 77,
            "base_temperature_search_run_id": 88,
        }
    )


def _verification() -> Task8PredictionVerificationSnapshot:
    return Task8PredictionVerificationSnapshot.model_validate(
        {
            "maturity_model_run_id": 11,
            "maturity_model_version": "task8-v1",
            "maturity_model_config_hash": "a" * 64,
            "maturity_model_source_signature": "b" * 64,
            "maturity_model_artifact_id": 22,
            "maturity_model_artifact_run_id": 11,
            "maturity_model_artifact_hash": "c" * 64,
            "maturity_forecast_run_id": 33,
            "maturity_forecast_run_status": "completed",
            "maturity_forecast_model_run_id": 11,
            "maturity_forecast_artifact_id": 22,
            "maturity_forecast_source_signature": "d" * 64,
            "maturity_forecast_as_of_date": "2026-03-15",
            "maturity_forecast_prediction_start_date": "2026-03-16",
            "maturity_forecast_prediction_end_date": "2026-03-31",
            "maturity_daily_prediction_id": 44,
            "maturity_daily_prediction_forecast_run_id": 33,
            "prediction_date": "2026-03-16",
            "farm_id": 101,
            "subfarm_id": 202,
            "variety_id": 303,
            "plan_id": 55,
            "location_reference_id": 66,
            "p50_kg": "10",
            "p80_kg": "12",
            "p90_kg": "14",
        }
    )


def _catalog_entry(source_ref: Task8PredictionSourceRef) -> SourceRefCatalogEntry:
    payload = source_ref.model_dump(mode="python")
    return SourceRefCatalogEntry(
        source_ref_hash=make_source_ref_hash(payload),
        source_ref_type=source_ref.source_ref_type,
        source_ref_schema_version=source_ref.source_ref_schema_version,
        source_ref_payload=payload,
    )


def _orm_bundle() -> dict[str, object]:
    verification = _verification()
    source_ref = _task8_source_ref()
    return {
        "model_run": SimpleNamespace(
            id=11,
            model_version="task8-v1",
            config_hash="a" * 64,
            source_signature="b" * 64,
        ),
        "artifact": SimpleNamespace(id=22, run_id=11, artifact_hash="c" * 64),
        "forecast_run": SimpleNamespace(
            id=33,
            model_run_id=11,
            artifact_id=22,
            source_signature="d" * 64,
            as_of_date=date(2026, 3, 15),
            status="completed",
            prediction_start_date=date(2026, 3, 16),
            prediction_end_date=date(2026, 3, 31),
            plan_id=55,
            location_reference_id=66,
            weather_mapping_id=77,
            base_temperature_search_run_id=88,
        ),
        "daily_row": SimpleNamespace(
            id=44,
            forecast_run_id=33,
            prediction_date=date(2026, 3, 16),
        ),
        "plan_row": SimpleNamespace(
            id=55,
            farm_id=verification.farm_id,
            subfarm_id=verification.subfarm_id,
            variety_id=verification.variety_id,
        ),
        "location_row": SimpleNamespace(id=source_ref.location_reference_id),
        "weather_mapping": SimpleNamespace(id=source_ref.weather_mapping_id),
        "base_temperature": SimpleNamespace(id=source_ref.base_temperature_search_run_id),
    }


@pytest.mark.asyncio
async def test_valid_complete_catalog_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
    ) -> dict[str, object]:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=[],
        input_snapshot_task8_predictions=[
            {
                "prediction_date": verification.prediction_date,
                "farm_id": verification.farm_id,
                "subfarm_id": verification.subfarm_id,
                "variety_id": verification.variety_id,
                "source_ref_hash": entry.source_ref_hash,
                "verification_snapshot": verification.model_dump(mode="python"),
            }
        ],
    )

    assert result["blocked"] is False
    assert result["task8_prediction_count"] == 1
    assert isinstance(result["source_catalog_hash"], str)
    assert isinstance(result["verification_snapshot_hash"], str)


@pytest.mark.asyncio
async def test_missing_snapshot_match_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
    ) -> dict[str, object]:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=[],
        input_snapshot_task8_predictions=[],
    )

    assert result["blocked"] is True
    assert "input snapshot match" in str(result["reason"])


@pytest.mark.asyncio
async def test_duplicate_snapshot_match_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
    ) -> dict[str, object]:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    snapshot_row = {
        "prediction_date": verification.prediction_date,
        "farm_id": verification.farm_id,
        "subfarm_id": verification.subfarm_id,
        "variety_id": verification.variety_id,
        "source_ref_hash": entry.source_ref_hash,
        "verification_snapshot": verification.model_dump(mode="python"),
    }

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=[],
        input_snapshot_task8_predictions=[snapshot_row, snapshot_row],
    )

    assert result["blocked"] is True
    assert "duplicate" in str(result["reason"])


@pytest.mark.asyncio
async def test_source_quantity_mismatch_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref(forecast_quantile="P80", source_quantity="99")
    verification = _verification()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
    ) -> dict[str, object]:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=[],
        input_snapshot_task8_predictions=[
            {
                "prediction_date": verification.prediction_date,
                "farm_id": verification.farm_id,
                "subfarm_id": verification.subfarm_id,
                "variety_id": verification.variety_id,
                "source_ref_hash": entry.source_ref_hash,
                "verification_snapshot": verification.model_dump(mode="python"),
            }
        ],
    )

    assert result["blocked"] is True
    assert "source_quantity_kg" in str(result["reason"])
