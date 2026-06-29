from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.harvest_state.canonical import make_source_ref_hash
from backend.app.harvest_state.schemas import (
    SourceRefCatalogEntry,
    Task8PredictionSourceRef,
    Task8PredictionVerificationSnapshot,
)
from backend.app.rolling_backtest.enums import (
    Task10ModelPolicy,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.orchestration import (
    Task8VerificationBundle,
    _validate_source_ref_catalog,
    _validate_task8_prediction_fields,
)
from backend.app.rolling_backtest.schemas import RollingNodeDefinition


def _make_test_node() -> RollingNodeDefinition:
    """Build a minimal RollingNodeDefinition for catalog validation tests."""
    from backend.app.rolling_backtest.enums import ScopeMode
    from backend.app.rolling_backtest.schemas import (
        HistoricalAvailableModelIdentity,
        RollingNodeScope,
        ScopeSelector,
    )

    return RollingNodeDefinition(
        season_id=2026,
        node_key="march_15",
        as_of_local_date=date(2026, 3, 15),
        forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        forecast_start_local_date=date(2026, 3, 16),
        forecast_end_local_date=date(2026, 3, 31),
        scope=RollingNodeScope(
            destination_factory_ids=ScopeSelector(mode=ScopeMode.INCLUDE_IDS, ids=(1,)),
            farm_ids=ScopeSelector(mode=ScopeMode.ALL),
            variety_ids=ScopeSelector(mode=ScopeMode.ALL),
        ),
        upstream_selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION,
        forecast_horizon_policy_version="test-v1",
        timezone="Asia/Shanghai",
        task10_model_policy=HistoricalAvailableModelIdentity(
            policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
            training_run_semantic_identity="1" * 64,
            artifact_semantic_identities=("2" * 64,),
            authority_visibility_identity="3" * 64,
        ),
        resolved_upstream_semantic_identities=(),
    )


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


def _orm_bundle() -> Task8VerificationBundle:
    verification = _verification()
    source_ref = _task8_source_ref()
    return Task8VerificationBundle(
        model_run=SimpleNamespace(
            id=11,
            model_version="task8-v1",
            config_hash="a" * 64,
            source_signature="b" * 64,
        ),
        artifact=SimpleNamespace(id=22, run_id=11, artifact_hash="c" * 64),
        forecast_run=SimpleNamespace(
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
        daily_row=SimpleNamespace(
            id=44,
            forecast_run_id=33,
            prediction_date=date(2026, 3, 16),
            p50_kg=Decimal("10"),
            p80_kg=Decimal("12"),
            p90_kg=Decimal("14"),
        ),
        plan_row=SimpleNamespace(
            id=55,
            farm_id=verification.farm_id,
            subfarm_id=verification.subfarm_id,
            variety_id=verification.variety_id,
        ),
        location_row=SimpleNamespace(id=source_ref.location_reference_id),
        weather_mapping=SimpleNamespace(
            id=source_ref.weather_mapping_id,
            location_reference_id=source_ref.location_reference_id,
            weather_source_location_id=901,
            available_at=date(2026, 3, 1),
            valid_from=date(2026, 3, 1),
            valid_to=None,
            mapping_version="map-v1",
            row_hash="m" * 64,
        ),
        base_temperature=SimpleNamespace(
            id=source_ref.base_temperature_search_run_id,
            variety_id=verification.variety_id,
            climate_zone_id=707,
            status="completed",
            config_hash="bt" * 32,
            source_signature="e" * 64,
            feature_version="bt-v1",
            finished_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        ),
        weather_feature_run=SimpleNamespace(
            id=99,
            base_temperature_search_run_id=source_ref.base_temperature_search_run_id,
            status="completed",
            feature_version="bt-v1",
            finished_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
        ),
    )


def _resolved_task8_authorities() -> list[SimpleNamespace]:
    def _resolved(
        *,
        source_role: str,
        source_type: str,
        reference_value: int,
        semantic_input_signature: str,
        result_hash: str,
        config_hash: str | None = None,
        source_signature: str | None = None,
        business_version: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            source_role=source_role,
            source_type=SimpleNamespace(value=source_type),
            resolved=SimpleNamespace(
                persistent_reference=SimpleNamespace(reference_value=reference_value),
                business_version=business_version,
                canonical_payload_hash=result_hash,
                semantic_identity=SimpleNamespace(
                    semantic=SimpleNamespace(
                        input_signature=semantic_input_signature,
                        result_hash=result_hash,
                        canonical_payload_hash=result_hash,
                        schema_version="task11-v1",
                        policy_version="task11-v1",
                        config_hash=config_hash,
                        business_version=business_version,
                        source_signature=source_signature,
                    )
                ),
            ),
        )

    return [
        _resolved(
            source_role="task8_model_run",
            source_type="task8_model_run",
            reference_value=11,
            semantic_input_signature="1" * 64,
            result_hash="2" * 64,
            config_hash="a" * 64,
            source_signature="b" * 64,
            business_version="task8-v1",
        ),
        _resolved(
            source_role="task8_model_artifact",
            source_type="task8_model_artifact",
            reference_value=22,
            semantic_input_signature="3" * 64,
            result_hash="c" * 64,
        ),
        _resolved(
            source_role="task8_forecast_run",
            source_type="task8_forecast_run",
            reference_value=33,
            semantic_input_signature="4" * 64,
            result_hash="5" * 64,
            source_signature="d" * 64,
        ),
        _resolved(
            source_role="task8_daily_prediction",
            source_type="task8_daily_prediction",
            reference_value=44,
            semantic_input_signature="6" * 64,
            result_hash="7" * 64,
        ),
        _resolved(
            source_role="task7_location_weather_mapping",
            source_type="task7_location_weather_mapping",
            reference_value=77,
            semantic_input_signature="8" * 64,
            result_hash="m" * 64,
            business_version="map-v1",
        ),
        _resolved(
            source_role="task7_weather_feature_run",
            source_type="task7_weather_feature_run",
            reference_value=99,
            semantic_input_signature="9" * 64,
            result_hash="e" * 64,
            business_version="bt-v1",
        ),
    ]


@pytest.mark.asyncio
async def test_valid_complete_catalog_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
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
        node=_make_test_node(),
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
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
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
        node=_make_test_node(),
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
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
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
        node=_make_test_node(),
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
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
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
        node=_make_test_node(),
    )

    assert result["blocked"] is True
    assert "source_quantity_kg" in str(result["reason"])


@pytest.mark.asyncio
async def test_outer_type_mismatch_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref).model_copy(
        update={"source_ref_type": "INITIAL_INVENTORY_SNAPSHOT"}
    )

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
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
        node=_make_test_node(),
    )

    assert result["blocked"] is True
    assert "task9_task8_authority_mismatch" in str(result["reason"])


@pytest.mark.asyncio
async def test_outer_schema_version_mismatch_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref).model_copy(
        update={"source_ref_schema_version": "task9a-source-ref-v999"}
    )

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
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
        node=_make_test_node(),
    )

    assert result["blocked"] is True
    assert "schema version" in str(result["reason"]).lower()


@pytest.mark.asyncio
async def test_payload_discriminator_mismatch_blocks() -> None:
    source_ref = _task8_source_ref()
    payload = source_ref.model_dump(mode="python")
    payload["source_ref_type"] = "INITIAL_INVENTORY_SNAPSHOT"
    entry = SourceRefCatalogEntry(
        source_ref_hash=make_source_ref_hash(payload),
        source_ref_type=source_ref.source_ref_type,
        source_ref_schema_version=source_ref.source_ref_schema_version,
        source_ref_payload=payload,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=[],
        input_snapshot_task8_predictions=[],
        node=_make_test_node(),
    )

    assert result["blocked"] is True
    assert "task9_task8_authority_mismatch" in str(result["reason"])


@pytest.mark.asyncio
async def test_valid_type_schema_parity_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
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
        node=_make_test_node(),
    )

    assert result["blocked"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    [
        ("p50_kg", Decimal("999")),
        ("p80_kg", Decimal("999")),
        ("p90_kg", Decimal("999")),
    ],
)
async def test_orm_quantile_mismatch_blocks(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    tampered_value: Decimal,
) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
        bundle = _orm_bundle()
        payload = dict(bundle.daily_row.__dict__)
        payload[field_name] = tampered_value
        bundle = Task8VerificationBundle(
            model_run=bundle.model_run,
            artifact=bundle.artifact,
            forecast_run=bundle.forecast_run,
            daily_row=SimpleNamespace(**payload),
            plan_row=bundle.plan_row,
            location_row=bundle.location_row,
            weather_mapping=bundle.weather_mapping,
            base_temperature=bundle.base_temperature,
            weather_feature_run=bundle.weather_feature_run,
        )
        return bundle

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
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
        node=_make_test_node(),
    )

    assert result["blocked"] is True
    assert field_name in str(result["reason"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    [
        ("maturity_model_run_id", 999),
        ("maturity_model_artifact_id", 999),
        ("maturity_forecast_run_id", 999),
        ("prediction_date", date(2026, 3, 20)),
    ],
)
async def test_source_ref_and_verification_mismatch_blocks(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    tampered_value: object,
) -> None:
    source_ref = _task8_source_ref()
    verification = _verification().model_copy(update={field_name: tampered_value})
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
        return _orm_bundle()

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
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
        node=_make_test_node(),
    )

    assert result["blocked"] is True
    assert "task9_task8_authority_mismatch" in str(result["reason"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bundle_field", "override"),
    [
        ("weather_mapping", {"location_reference_id": 999}),
        ("weather_mapping", {"available_at": date(2026, 3, 20)}),
        ("weather_mapping", {"valid_from": date(2026, 3, 20)}),
        ("weather_mapping", {"mapping_version": "map-v999"}),
        ("weather_mapping", {"row_hash": "z" * 64}),
        ("base_temperature", {"status": "failed"}),
        ("base_temperature", {"finished_at": datetime(2026, 3, 20, 12, 0, tzinfo=UTC)}),
    ],
)
async def test_weather_mapping_and_base_temperature_mismatch_blocks(
    monkeypatch: pytest.MonkeyPatch,
    bundle_field: str,
    override: dict[str, object],
) -> None:
    source_ref = _task8_source_ref()
    verification = _verification()
    entry = _catalog_entry(source_ref)

    async def _fake_bundle(
        _session: object,
        _typed_sr: Task8PredictionSourceRef,
        *,
        forecast_cutoff_at: object = None,
        timezone: object = None,
    ) -> Task8VerificationBundle:
        bundle = _orm_bundle()
        current = getattr(bundle, bundle_field)
        payload = dict(current.__dict__)
        payload.update(override)
        bundle = Task8VerificationBundle(
            model_run=bundle.model_run,
            artifact=bundle.artifact,
            forecast_run=bundle.forecast_run,
            daily_row=bundle.daily_row,
            plan_row=bundle.plan_row,
            location_row=bundle.location_row,
            weather_mapping=(
                SimpleNamespace(**payload)
                if bundle_field == "weather_mapping"
                else bundle.weather_mapping
            ),
            base_temperature=(
                SimpleNamespace(**payload)
                if bundle_field == "base_temperature"
                else bundle.base_temperature
            ),
            weather_feature_run=bundle.weather_feature_run,
        )
        return bundle

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_verification_bundle",
        _fake_bundle,
    )

    result = await _validate_source_ref_catalog(
        session=object(),  # type: ignore[arg-type]
        catalog=[entry],
        resolutions=_resolved_task8_authorities(),  # type: ignore[arg-type]
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
        node=_make_test_node(),
    )

    assert result["blocked"] is True
    assert "task9_task8_authority_mismatch" in str(result["reason"])


# ══════════════════════════════════════════════════════════════════════════════
# P0-5E: Pure-validator tests — direct calls to _validate_task8_prediction_fields
# without session, without monkeypatch, proving the validator is pure.
# ══════════════════════════════════════════════════════════════════════════════


def test_pure_validator_complete_bundle_passes() -> None:
    """Full typed bundle with all authorities → zero issues."""
    bundle = _orm_bundle()
    authorities = _resolved_task8_authorities()
    authority_by_type = {r.source_type.value: r for r in authorities}
    authority_map = {r.source_role: r for r in authorities}
    node = _make_test_node()

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type=authority_by_type,
        authority_map=authority_map,
        forecast_cutoff_at=node.forecast_cutoff_at,
        timezone=node.timezone,
        bundle=bundle,
    )
    assert issues == []


def test_pure_validator_missing_model_run_fail_closed() -> None:
    """model_run=None → fail closed."""
    bundle = _orm_bundle()
    bundle = Task8VerificationBundle(
        model_run=None,
        artifact=bundle.artifact,
        forecast_run=bundle.forecast_run,
        daily_row=bundle.daily_row,
        plan_row=bundle.plan_row,
        location_row=bundle.location_row,
        weather_mapping=bundle.weather_mapping,
        base_temperature=bundle.base_temperature,
        weather_feature_run=bundle.weather_feature_run,
    )

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type={},
        authority_map={},
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert "maturity_model_run not found" in issues


def test_pure_validator_missing_artifact_fail_closed() -> None:
    """artifact=None → fail closed."""
    bundle = _orm_bundle()
    bundle = Task8VerificationBundle(
        model_run=bundle.model_run,
        artifact=None,
        forecast_run=bundle.forecast_run,
        daily_row=bundle.daily_row,
        plan_row=bundle.plan_row,
        location_row=bundle.location_row,
        weather_mapping=bundle.weather_mapping,
        base_temperature=bundle.base_temperature,
        weather_feature_run=bundle.weather_feature_run,
    )

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type={},
        authority_map={},
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert "maturity_model_artifact not found" in issues


def test_pure_validator_missing_forecast_run_fail_closed() -> None:
    """forecast_run=None → fail closed."""
    bundle = _orm_bundle()
    bundle = Task8VerificationBundle(
        model_run=bundle.model_run,
        artifact=bundle.artifact,
        forecast_run=None,
        daily_row=bundle.daily_row,
        plan_row=bundle.plan_row,
        location_row=bundle.location_row,
        weather_mapping=bundle.weather_mapping,
        base_temperature=bundle.base_temperature,
        weather_feature_run=bundle.weather_feature_run,
    )

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type={},
        authority_map={},
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert "maturity_forecast_run not found" in issues


def test_pure_validator_missing_daily_prediction_fail_closed() -> None:
    """daily_row=None → fail closed."""
    bundle = _orm_bundle()
    bundle = Task8VerificationBundle(
        model_run=bundle.model_run,
        artifact=bundle.artifact,
        forecast_run=bundle.forecast_run,
        daily_row=None,
        plan_row=bundle.plan_row,
        location_row=bundle.location_row,
        weather_mapping=bundle.weather_mapping,
        base_temperature=bundle.base_temperature,
        weather_feature_run=bundle.weather_feature_run,
    )

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type={},
        authority_map={},
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert "maturity_daily_prediction not found" in issues


def test_pure_validator_mapping_authority_correct_type_passes() -> None:
    """TASK7_LOCATION_WEATHER_MAPPING authority validates mapping, not observation."""
    bundle = _orm_bundle()
    authorities = _resolved_task8_authorities()
    authority_by_type = {r.source_type.value: r for r in authorities}
    authority_map = {r.source_role: r for r in authorities}

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type=authority_by_type,
        authority_map=authority_map,
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert not any("mapping" in i for i in issues)
    assert not any("weather mapping" in i for i in issues)


def test_pure_validator_cross_model_identity_blocked() -> None:
    """Feature-run authority must NOT validate mapping fields."""
    bundle = _orm_bundle()
    authorities = _resolved_task8_authorities()
    authority_by_type = {r.source_type.value: r for r in authorities}
    authority_map = {r.source_role: r for r in authorities}

    authority_by_type.pop("task7_location_weather_mapping", None)

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type=authority_by_type,
        authority_map=authority_map,
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert not any("mapping version does not match resolved authority" in i for i in issues)


def test_pure_validator_feature_run_authority_correct_type_passes() -> None:
    """TASK7_WEATHER_FEATURE_RUN validates its own type, not mapping."""
    bundle = _orm_bundle()
    authorities = _resolved_task8_authorities()
    authority_by_type = {r.source_type.value: r for r in authorities}
    authority_map = {r.source_role: r for r in authorities}

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type=authority_by_type,
        authority_map=authority_map,
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert not any("feature_version" in i for i in issues)
    assert not any("WeatherFeatureRun" in i for i in issues)


def test_pure_validator_feature_version_mismatch_blocks() -> None:
    """feature_version mismatch → blocked."""
    bundle = _orm_bundle()
    tampered_wfr = SimpleNamespace(
        id=99,
        base_temperature_search_run_id=_task8_source_ref().base_temperature_search_run_id,
        status="completed",
        feature_version="bt-v999",
        finished_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
    )
    bundle = Task8VerificationBundle(
        model_run=bundle.model_run,
        artifact=bundle.artifact,
        forecast_run=bundle.forecast_run,
        daily_row=bundle.daily_row,
        plan_row=bundle.plan_row,
        location_row=bundle.location_row,
        weather_mapping=bundle.weather_mapping,
        base_temperature=bundle.base_temperature,
        weather_feature_run=tampered_wfr,
    )

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type={},
        authority_map={},
        forecast_cutoff_at=_make_test_node().forecast_cutoff_at,
        timezone="Asia/Shanghai",
        bundle=bundle,
    )
    assert any("feature_version" in i for i in issues)


def test_pure_validator_no_session_or_orm_calls() -> None:
    """Validator accepts only typed bundle — no session, no ORM."""
    bundle = _orm_bundle()
    authorities = _resolved_task8_authorities()
    authority_by_type = {r.source_type.value: r for r in authorities}
    authority_map = {r.source_role: r for r in authorities}
    node = _make_test_node()

    issues = _validate_task8_prediction_fields(
        typed_sr=_task8_source_ref(),
        typed_verification=_verification(),
        authority_by_type=authority_by_type,
        authority_map=authority_map,
        forecast_cutoff_at=node.forecast_cutoff_at,
        timezone=node.timezone,
        bundle=bundle,
    )
    assert isinstance(issues, list)
