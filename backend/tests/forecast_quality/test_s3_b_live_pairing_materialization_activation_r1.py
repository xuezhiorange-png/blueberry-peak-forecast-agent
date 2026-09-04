"""Tests for S3-B live pairing materialization activation R1."""

from __future__ import annotations

import importlib
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.forecast_quality.train_val_pairing_materialization import (
    OfficialPartitionRows,
    TrainValidationPairingMaterializationBlocker,
    _materialization_grains_from_partitions,
    materialize_train_validation_pairing_inputs_live,
)
from backend.app.models.maturity import MaturityDailyPredictionModel
from backend.app.rolling_backtest.resolution import task8_daily_prediction_payload_hash
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    AcceptedS2TrainValSource002RowLevelReadAttestation,
    Source002RowLevelReadReasonCode,
    attest_accepted_s2_train_val_source_002_row_level_read,
)
from backend.app.s3_daily_rowset.forecast_port import ForecastAvailability
from backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain import (
    LiveIncumbentForecastDailyCurveObtainResult,
    obtain_live_incumbent_forecast_daily_curve_provider,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_loader import (
    PitVisibleDailyForecastCell,
    PitVisibleIncumbentDailyCurveIndex,
    build_pit_visible_incumbent_daily_curve_index,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_provider import (
    PitVisibleIncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_forecast_authority_loader import (
    is_synthetic_forecast_authority,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MODEL_ID,
)
from backend.app.s3_daily_rowset.schemas import EvaluationInstanceCell

_live_session = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session"
)
_live_obtain = importlib.import_module(
    "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain"
)
is_live_async_session_run_sync_provider = _live_session.is_live_async_session_run_sync_provider
source_002_row_level_read_live_session_provider = (
    _live_session.source_002_row_level_read_live_session_provider
)

_REVIEWED_CUTOFF = datetime.fromisoformat(REVIEW_CUTOFF_AT)


def _test_forecast_binding_authority(
    *,
    forecast_run_hash: str = "1" * 64,
    daily_row_hash: str = "2" * 64,
) -> S2ForecastAuthorityBundle:
    return S2ForecastAuthorityBundle(
        forecast_run_identity_hash=forecast_run_hash,
        daily_row_identity_hash=daily_row_hash,
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


def _forecast_cell(
    *,
    quantile: str = "P50",
    season: str = "2025~2026",
    farm: str = "farm-a",
    subfarm: str = "farm-a/subfarm-1",
    variety: str = "variety-x",
) -> EvaluationInstanceCell:
    return EvaluationInstanceCell(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        model_id=REVIEW_MODEL_ID,
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        forecast_quantile=quantile,
    )


def _pit_cell(
    daily: MaturityDailyPredictionModel,
    *,
    authority: S2ForecastAuthorityBundle,
    task8_run_id: int = 401,
) -> PitVisibleDailyForecastCell:
    daily_hash = task8_daily_prediction_payload_hash(daily, forecast_source_signature="b" * 64)
    return PitVisibleDailyForecastCell(
        forecast_kg=daily.p50_kg,
        task8_forecast_run_id=task8_run_id,
        task8_daily_row_id=daily.id,
        daily_row_identity_hash=daily_hash,
        forecast_run_identity_hash="b" * 64,
        forecast_binding_authority=authority,
    )


def test_task8_daily_prediction_payload_hash_maps_quantile_fields() -> None:
    daily = _daily_row(prediction_date=date(2026, 2, 20), created_at=_REVIEWED_CUTOFF)
    payload_hash = task8_daily_prediction_payload_hash(daily, forecast_source_signature="b" * 64)
    assert len(payload_hash) == 64
    assert payload_hash != ("0" * 64)


def test_pit_visible_provider_reads_p50_p80_p90_kg() -> None:
    daily = _daily_row(prediction_date=date(2026, 2, 20), created_at=_REVIEWED_CUTOFF)
    authority = _test_forecast_binding_authority()
    provider = PitVisibleIncumbentDailyCurveProvider(
        index=PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            cells={
                (
                    "2025~2026",
                    "farm-a",
                    "farm-a/subfarm-1",
                    "variety-x",
                    "P50",
                    date(2026, 2, 20),
                ): _pit_cell(daily, authority=authority),
                (
                    "2025~2026",
                    "farm-a",
                    "farm-a/subfarm-1",
                    "variety-x",
                    "P80",
                    date(2026, 2, 20),
                ): PitVisibleDailyForecastCell(
                    forecast_kg=daily.p80_kg,
                    task8_forecast_run_id=401,
                    task8_daily_row_id=1,
                    daily_row_identity_hash=task8_daily_prediction_payload_hash(
                        daily, forecast_source_signature="b" * 64
                    ),
                    forecast_run_identity_hash="b" * 64,
                    forecast_binding_authority=authority,
                ),
                (
                    "2025~2026",
                    "farm-a",
                    "farm-a/subfarm-1",
                    "variety-x",
                    "P90",
                    date(2026, 2, 20),
                ): PitVisibleDailyForecastCell(
                    forecast_kg=daily.p90_kg,
                    task8_forecast_run_id=401,
                    task8_daily_row_id=1,
                    daily_row_identity_hash=task8_daily_prediction_payload_hash(
                        daily, forecast_source_signature="b" * 64
                    ),
                    forecast_run_identity_hash="b" * 64,
                    forecast_binding_authority=authority,
                ),
            },
            grain_forecast_run_count={("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x"): 1},
        )
    )
    assert provider.forecast_kg_for_day(
        _forecast_cell(quantile="P50"), business_date=date(2026, 2, 20)
    ).forecast_harvest_quantity_kg == Decimal("10.0")
    assert provider.forecast_kg_for_day(
        _forecast_cell(quantile="P80"), business_date=date(2026, 2, 20)
    ).forecast_harvest_quantity_kg == Decimal("12.0")
    assert provider.forecast_kg_for_day(
        _forecast_cell(quantile="P90"), business_date=date(2026, 2, 20)
    ).forecast_harvest_quantity_kg == Decimal("14.0")


def test_forecast_after_cutoff_rejected() -> None:
    provider = PitVisibleIncumbentDailyCurveProvider(
        index=PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            cells={},
            grain_forecast_run_count={},
        )
    )
    late_cell = _forecast_cell().model_copy(
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
    result = provider.forecast_kg_for_day(_forecast_cell(), business_date=date(2026, 3, 1))
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
            forecast_binding_authority=_test_forecast_binding_authority(),
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
        provider.forecast_kg_for_day(_forecast_cell(), business_date=date(2026, 2, 20))


def test_synthetic_forecast_authority_rejected_for_live_path() -> None:
    assert is_synthetic_forecast_authority(_test_forecast_binding_authority())


def test_live_async_session_run_sync_provider_is_marker() -> None:
    assert is_live_async_session_run_sync_provider(source_002_row_level_read_live_session_provider)
    assert source_002_row_level_read_live_session_provider() is None


def test_source_002_attestation_uses_run_sync_path(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = AcceptedS2TrainValSource002RowLevelReadAttestation(
        attested=True,
        source_002_row_level_read=True,
        official_hashes_attested_from_a_live_read=True,
        reason_code=Source002RowLevelReadReasonCode.ATTESTED,
    )
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session."
        "attest_source_002_via_async_session_run_sync",
        lambda: expected,
    )
    result = attest_accepted_s2_train_val_source_002_row_level_read()
    assert result.attested is True
    assert result.reason_code is Source002RowLevelReadReasonCode.ATTESTED


@pytest.mark.asyncio
async def test_source_002_run_sync_attestation_executes_sync_callback() -> None:
    _attest_with_session_maker = _live_session._attest_with_session_maker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    attested = AcceptedS2TrainValSource002RowLevelReadAttestation(
        attested=True,
        source_002_row_level_read=True,
        official_hashes_attested_from_a_live_read=True,
        reason_code=Source002RowLevelReadReasonCode.ATTESTED,
    )
    with patch(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session."
        "_attest_from_session",
        return_value=attested,
    ) as attest_mock:
        result = await _attest_with_session_maker(session_maker)
    await engine.dispose()
    assert result.attested is True
    attest_mock.assert_called_once()


@pytest.mark.asyncio
async def test_source_002_run_sync_obtain_executes_sync_callback() -> None:
    AcceptedS2TrainValLiveObtainEnvelope = _live_obtain.AcceptedS2TrainValLiveObtainEnvelope
    LiveObtainReasonCode = _live_obtain.LiveObtainReasonCode
    _obtain_with_session_maker = _live_session._obtain_with_session_maker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    obtained = AcceptedS2TrainValLiveObtainEnvelope(
        obtained=True,
        source_002_row_level_read=False,
        official_hashes_attested_from_a_live_read=False,
        reason_code=LiveObtainReasonCode.OBTAINED,
        train_content_bytes=b"train",
        validation_content_bytes=b"validation",
    )
    with patch(
        "backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_session."
        "_obtain_from_session",
        return_value=obtained,
    ) as obtain_mock:
        result = await _obtain_with_session_maker(session_maker)
    await engine.dispose()
    assert result.obtained is True
    obtain_mock.assert_called_once()


def test_production_live_index_requires_exact_grains() -> None:
    import inspect

    signature = inspect.signature(build_pit_visible_incumbent_daily_curve_index)
    grains_param = signature.parameters["grains"]
    assert grains_param.default is inspect.Parameter.empty


def test_ambiguous_forecast_run_count_recorded() -> None:
    index = PitVisibleIncumbentDailyCurveIndex(
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        cells={},
        grain_forecast_run_count={("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x"): 2},
    )
    grains = frozenset({("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x")})
    assert (
        index.grain_forecast_run_count[("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x")]
        == 2
    )
    assert any(index.grain_forecast_run_count.get(grain, 0) > 1 for grain in grains)


def test_multi_grain_provider_returns_per_row_authority() -> None:
    daily_a = _daily_row(prediction_date=date(2026, 2, 20), created_at=_REVIEWED_CUTOFF, row_id=1)
    daily_b = _daily_row(prediction_date=date(2026, 2, 21), created_at=_REVIEWED_CUTOFF, row_id=2)
    hash_a = task8_daily_prediction_payload_hash(daily_a, forecast_source_signature="b" * 64)
    hash_b = task8_daily_prediction_payload_hash(daily_b, forecast_source_signature="c" * 64)
    authority_a = _test_forecast_binding_authority(
        forecast_run_hash="a" * 64, daily_row_hash=hash_a
    )
    authority_b = _test_forecast_binding_authority(
        forecast_run_hash="b" * 64, daily_row_hash=hash_b
    )
    provider = PitVisibleIncumbentDailyCurveProvider(
        index=PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            cells={
                (
                    "2025~2026",
                    "farm-a",
                    "farm-a/subfarm-1",
                    "variety-x",
                    "P50",
                    date(2026, 2, 20),
                ): PitVisibleDailyForecastCell(
                    forecast_kg=daily_a.p50_kg,
                    task8_forecast_run_id=401,
                    task8_daily_row_id=1,
                    daily_row_identity_hash=hash_a,
                    forecast_run_identity_hash="b" * 64,
                    forecast_binding_authority=authority_a,
                ),
                (
                    "2025~2026",
                    "farm-b",
                    "farm-b/subfarm-2",
                    "variety-y",
                    "P50",
                    date(2026, 2, 21),
                ): PitVisibleDailyForecastCell(
                    forecast_kg=daily_b.p50_kg,
                    task8_forecast_run_id=402,
                    task8_daily_row_id=2,
                    daily_row_identity_hash=hash_b,
                    forecast_run_identity_hash="c" * 64,
                    forecast_binding_authority=authority_b,
                ),
            },
            grain_forecast_run_count={
                ("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x"): 1,
                ("2025~2026", "farm-b", "farm-b/subfarm-2", "variety-y"): 1,
            },
        )
    )
    auth_a = provider.forecast_authority_for(
        _forecast_cell(
            season="2025~2026", farm="farm-a", subfarm="farm-a/subfarm-1", variety="variety-x"
        ),
        business_date=date(2026, 2, 20),
    )
    auth_b = provider.forecast_authority_for(
        _forecast_cell(
            season="2025~2026", farm="farm-b", subfarm="farm-b/subfarm-2", variety="variety-y"
        ),
        business_date=date(2026, 2, 21),
    )
    assert auth_a is not None
    assert auth_b is not None
    assert auth_a.forecast_run_identity_hash == "a" * 64
    assert auth_b.forecast_run_identity_hash == "b" * 64
    assert auth_a.daily_row_identity_hash != auth_b.daily_row_identity_hash


def test_daily_row_authority_mismatch_rejected() -> None:
    daily = _daily_row(prediction_date=date(2026, 2, 20), created_at=_REVIEWED_CUTOFF)
    mismatched_authority = _test_forecast_binding_authority(daily_row_hash="9" * 64)
    provider = PitVisibleIncumbentDailyCurveProvider(
        index=PitVisibleIncumbentDailyCurveIndex(
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            cells={
                (
                    "2025~2026",
                    "farm-a",
                    "farm-a/subfarm-1",
                    "variety-x",
                    "P50",
                    date(2026, 2, 20),
                ): PitVisibleDailyForecastCell(
                    forecast_kg=daily.p50_kg,
                    task8_forecast_run_id=401,
                    task8_daily_row_id=1,
                    daily_row_identity_hash=task8_daily_prediction_payload_hash(
                        daily, forecast_source_signature="b" * 64
                    ),
                    forecast_run_identity_hash="b" * 64,
                    forecast_binding_authority=mismatched_authority,
                ),
            },
            grain_forecast_run_count={("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x"): 1},
        )
    )
    assert (
        provider.forecast_authority_for(_forecast_cell(), business_date=date(2026, 2, 20)) is None
    )


def test_obtain_live_fail_closed_without_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain.asyncio.run",
        lambda _coro: LiveIncumbentForecastDailyCurveObtainResult(obtained=False, provider=None),
    )
    result = obtain_live_incumbent_forecast_daily_curve_provider(
        materialization_grains=frozenset({("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x")})
    )
    assert result.obtained is False
    assert result.provider is None


def test_obtain_live_fail_closed_on_ambiguous_grain(monkeypatch: pytest.MonkeyPatch) -> None:
    grains = frozenset({("2025~2026", "farm-a", "farm-a/subfarm-1", "variety-x")})
    monkeypatch.setattr(
        "backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain.asyncio.run",
        lambda _coro: LiveIncumbentForecastDailyCurveObtainResult(
            obtained=False,
            provider=None,
            ambiguous_grain_count=1,
            unavailable_grain_count=1,
        ),
    )
    result = obtain_live_incumbent_forecast_daily_curve_provider(materialization_grains=grains)
    assert result.obtained is False
    assert result.ambiguous_grain_count == 1


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


def test_live_materialization_blocks_on_ambiguous_forecast_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
        AcceptedS2TrainValSource002RowLevelReadAttestation,
    )
    AcceptedS2TrainValLiveObtainEnvelope = _live_obtain.AcceptedS2TrainValLiveObtainEnvelope
    LiveObtainReasonCode = _live_obtain.LiveObtainReasonCode

    monkeypatch.setattr(
        "backend.app.forecast_quality.train_val_pairing_materialization."
        "attest_accepted_s2_train_val_source_002_row_level_read",
        lambda: AcceptedS2TrainValSource002RowLevelReadAttestation(
            attested=True,
            source_002_row_level_read=True,
            official_hashes_attested_from_a_live_read=True,
            reason_code=Source002RowLevelReadReasonCode.ATTESTED,
        ),
    )
    monkeypatch.setattr(
        "backend.app.forecast_quality.train_val_pairing_materialization."
        "obtain_accepted_s2_train_val_content_bytes_from_bound_live_session",
        lambda: AcceptedS2TrainValLiveObtainEnvelope(
            obtained=True,
            source_002_row_level_read=False,
            official_hashes_attested_from_a_live_read=False,
            reason_code=LiveObtainReasonCode.OBTAINED,
            train_content_bytes=b"train",
            validation_content_bytes=b"validation",
        ),
    )
    monkeypatch.setattr(
        "backend.app.forecast_quality.train_val_pairing_materialization."
        "load_official_partition_rows_from_content_bytes",
        lambda **_: OfficialPartitionRows(
            train_rows=(),
            validation_rows=(),
            train_content_sha256="a" * 64,
            validation_content_sha256="b" * 64,
        ),
    )
    from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry

    reviewed_entries = tuple(
        IncumbentForecastArtifactEntry(
            model_id=REVIEW_MODEL_ID,
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            forecast_quantile=quantile,
        )
        for quantile in ("P50", "P80", "P90")
    )
    monkeypatch.setattr(
        "backend.app.forecast_quality.train_val_pairing_materialization."
        "IncumbentForecastReplaySource",
        lambda: SimpleNamespace(
            uses_harvest_date_as_forecast_cutoff=False,
            obtain=lambda: reviewed_entries,
        ),
    )
    monkeypatch.setattr(
        "backend.app.forecast_quality.train_val_pairing_materialization."
        "obtain_live_incumbent_forecast_daily_curve_provider",
        lambda **_: LiveIncumbentForecastDailyCurveObtainResult(
            obtained=False,
            provider=None,
            ambiguous_grain_count=1,
        ),
    )
    result = materialize_train_validation_pairing_inputs_live()
    assert result.completed is False
    assert result.blocker == TrainValidationPairingMaterializationBlocker.AMBIGUOUS_FORECAST_RUN


def test_materialization_grains_union_train_and_validation() -> None:
    from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow

    official = OfficialPartitionRows(
        train_rows=(
            MaterializableRow(
                season="s1",
                farm="f1",
                subfarm="sf1",
                variety="v1",
                harvest_business_date=date(2026, 2, 20),
                actual_harvest_quantity_kg=Decimal("1"),
                source_row_identity="a",
                cleaned_row_identity="b",
                pit_visibility_identity="c",
                revision_winner_identity="d",
            ),
        ),
        validation_rows=(
            MaterializableRow(
                season="s2",
                farm="f2",
                subfarm="sf2",
                variety="v2",
                harvest_business_date=date(2026, 2, 21),
                actual_harvest_quantity_kg=Decimal("2"),
                source_row_identity="e",
                cleaned_row_identity="f",
                pit_visibility_identity="g",
                revision_winner_identity="h",
            ),
        ),
        train_content_sha256="a" * 64,
        validation_content_sha256="b" * 64,
    )
    grains = _materialization_grains_from_partitions(official)
    assert grains == frozenset({("s1", "f1", "sf1", "v1"), ("s2", "f2", "sf2", "v2")})
