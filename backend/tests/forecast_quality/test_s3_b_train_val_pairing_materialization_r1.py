"""Tests for S3-B TRAIN/VALIDATION pairing materialization R1."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from backend.app.forecast_quality.train_val_pairing import (
    EXACT_ACTUAL_PAIRING_POLICY_V1,
    TRAIN_VAL_PAIRING_POLICY_V1,
    validate_published_pairing_package_invariants,
    verify_pairing_package_hash_replay,
)
from backend.app.forecast_quality.train_val_pairing_materialization import (
    ACTUAL_PARTITION_LOOKUP_KEY,
    EXISTING_CANONICAL_SOURCE_002_PARTITION_ROW_PARSER,
    FORECAST_BINDING_KEY,
    FORECAST_BINDING_KEY_AUTHORITY_SOURCE,
    OfficialPartitionRows,
    TrainValidationPairingMaterializationBlocker,
    TrainValidationPairingMaterializationDeps,
    _build_partition_s2_binding_request,
    compute_canonical_forecast_binding_key_hash,
    load_official_partition_rows_from_content_bytes,
    materialize_train_validation_pairing_inputs,
)
from backend.app.forecast_quality.train_val_trusted_registry import (
    PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY,
)
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.rolling_backtest.signatures import s2_binding_key_hash
from backend.app.s2_materialized_dataset.lane_d.canonical import build_partition_bytes
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
)
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.forecast_port import (
    FakeIncumbentDailyCurveProvider,
    ForecastAvailability,
    IncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MODEL_ID,
    reviewed_grain_identity_set_identity_sha256,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
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


def _materializable_row(
    *,
    harvest_business_date: date,
    quantity: str = "10.0",
    season: str = "2025~2026",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    source_row_identity: str | None = None,
) -> MaterializableRow:
    identity = source_row_identity or f"src-{harvest_business_date.isoformat()}"
    return MaterializableRow(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=harvest_business_date,
        actual_harvest_quantity_kg=Decimal(quantity),
        source_row_identity=identity,
        cleaned_row_identity=f"cln-{identity}",
        pit_visibility_identity=f"pit-{identity}",
        revision_winner_identity=f"rev-{identity}",
    )


def _reviewed_forecast_entries() -> tuple[IncumbentForecastArtifactEntry, ...]:
    return tuple(
        IncumbentForecastArtifactEntry(
            model_id=REVIEW_MODEL_ID,
            forecast_cutoff_at=_REVIEWED_CUTOFF,
            forecast_quantile=quantile,
        )
        for quantile in ("P50", "P80", "P90")
    )


def _forecast_provider(
    *,
    forecasts: dict[date, Decimal] | None = None,
    unavailable: bool = False,
    default_authority: S2ForecastAuthorityBundle | None = None,
    authorities: dict[tuple[date, int], S2ForecastAuthorityBundle] | None = None,
) -> IncumbentDailyCurveProvider:
    return FakeIncumbentDailyCurveProvider(
        forecasts=forecasts,
        unavailable=unavailable,
        default_authority=default_authority or _test_forecast_binding_authority(),
        authorities=authorities,
    )


def _target_dates() -> tuple[date, date, date]:
    cutoff_date = _REVIEWED_CUTOFF.astimezone(SHANGHAI).date()
    return (
        cutoff_date.fromordinal(cutoff_date.toordinal() + 7),
        cutoff_date.fromordinal(cutoff_date.toordinal() + 14),
        cutoff_date.fromordinal(cutoff_date.toordinal() + 21),
    )


def _small_official_partitions() -> OfficialPartitionRows:
    t7, t14, t21 = _target_dates()
    train_rows = (
        _materializable_row(harvest_business_date=t7, source_row_identity="train-row-7"),
        _materializable_row(harvest_business_date=t14, source_row_identity="train-row-14"),
    )
    validation_rows = (
        _materializable_row(harvest_business_date=t21, source_row_identity="validation-row-21"),
    )
    train_bytes = build_partition_bytes(train_rows)
    validation_bytes = build_partition_bytes(validation_rows)
    return OfficialPartitionRows(
        train_rows=train_rows,
        validation_rows=validation_rows,
        train_content_sha256=content_sha256(train_bytes),
        validation_content_sha256=content_sha256(validation_bytes),
    )


def _materialize_deps(
    *,
    official: OfficialPartitionRows | None = None,
    forecasts: dict[date, Decimal] | None = None,
    replay_entries: tuple[IncumbentForecastArtifactEntry, ...] | None = None,
    forecast_unavailable: bool = False,
    forecast_provider: IncumbentDailyCurveProvider | None = None,
) -> TrainValidationPairingMaterializationDeps:
    t7, t14, t21 = _target_dates()
    if forecasts is None:
        forecasts = {t7: Decimal("5.0"), t14: Decimal("6.0"), t21: Decimal("7.0")}
    entries = _reviewed_forecast_entries() if replay_entries is None else replay_entries
    provider = forecast_provider or _forecast_provider(
        forecasts=forecasts,
        unavailable=forecast_unavailable,
    )
    return TrainValidationPairingMaterializationDeps(
        official_partitions=official or _small_official_partitions(),
        forecast_replay_entries=entries,
        forecast_provider=provider,
        forecast_cutoff_authority_identity=reviewed_grain_identity_set_identity_sha256(),
        forecast_content_identity_sha256="f" * 64,
    )


def test_canonical_discovery_constants() -> None:
    assert EXISTING_CANONICAL_SOURCE_002_PARTITION_ROW_PARSER.endswith("parse_partition_bytes")
    assert FORECAST_BINDING_KEY_AUTHORITY_SOURCE.endswith("s2_binding_key_hash")
    assert "target_date" in ACTUAL_PARTITION_LOOKUP_KEY
    assert "forecast_run_identity" in FORECAST_BINDING_KEY


def test_official_hash_mismatch_fail_closed() -> None:
    blocker = load_official_partition_rows_from_content_bytes(
        train_content_bytes=b"not-official",
        validation_content_bytes=b"not-official",
    )
    assert blocker == TrainValidationPairingMaterializationBlocker.OFFICIAL_HASH_MISMATCH


def test_forecast_replay_empty_blocks_materialization() -> None:
    result = materialize_train_validation_pairing_inputs(_materialize_deps(replay_entries=()))
    assert not result.completed
    assert (
        result.blocker
        == TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS
    )


def test_incumbent_replay_source_empty_obtain_blocks() -> None:
    source = IncumbentForecastReplaySource(replay_rows=())
    assert source.obtain() == ()


def test_unavailable_forecast_provider_blocks_before_package() -> None:
    result = materialize_train_validation_pairing_inputs(
        _materialize_deps(
            forecast_provider=FakeIncumbentDailyCurveProvider(
                unavailable=True,
                default_authority=_test_forecast_binding_authority(),
            )
        )
    )
    assert not result.completed
    assert (
        result.blocker
        == TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER
    )
    assert result.train_pairing_package is None
    assert result.validation_pairing_package is None


def test_partition_isolation_train_and_validation_packages() -> None:
    result = materialize_train_validation_pairing_inputs(_materialize_deps())
    assert result.completed
    assert result.train_pairing_package is not None
    assert result.validation_pairing_package is not None
    assert result.train_pairing_package.partition == "TRAIN"
    assert result.validation_pairing_package.partition == "VALIDATION"
    assert all(proof.partition == "TRAIN" for proof in result.train_membership_proofs)
    assert all(proof.partition == "VALIDATION" for proof in result.validation_membership_proofs)
    train_dates = {row.forecast_target_date for row in result.train_evaluation_input.rows}
    validation_dates = {row.forecast_target_date for row in result.validation_evaluation_input.rows}
    assert date(2026, 2, 23) in train_dates or date(2026, 3, 2) in train_dates
    assert date(2026, 3, 9) in validation_dates


def test_cross_partition_source_row_identity_blocks() -> None:
    t7, _, _ = _target_dates()
    shared = _materializable_row(harvest_business_date=t7, source_row_identity="shared-row")
    official = OfficialPartitionRows(
        train_rows=(shared,),
        validation_rows=(shared,),
        train_content_sha256="a" * 64,
        validation_content_sha256="b" * 64,
    )
    result = materialize_train_validation_pairing_inputs(_materialize_deps(official=official))
    assert not result.completed
    assert (
        result.blocker
        == TrainValidationPairingMaterializationBlocker.CROSS_PARTITION_SOURCE_ROW_IDENTITY
    )
    assert result.cross_partition_row_count == 1


def test_exact_pairing_missing_actual_not_zero_filled() -> None:
    t7, t14, t21 = _target_dates()
    official = OfficialPartitionRows(
        train_rows=(_materializable_row(harvest_business_date=t7),),
        validation_rows=(_materializable_row(harvest_business_date=t21),),
        train_content_sha256="a" * 64,
        validation_content_sha256="b" * 64,
    )
    result = materialize_train_validation_pairing_inputs(
        _materialize_deps(
            official=official,
            forecasts={t7: Decimal("3.0"), t21: Decimal("4.0")},
        )
    )
    assert result.completed
    missing_actual_rows = [
        row for row in result.train_evaluation_input.rows if row.forecast_target_date == t14
    ]
    assert missing_actual_rows
    assert all(row.actual_value_kg is None for row in missing_actual_rows)
    assert all(row.s2_status == "EXCLUDED" for row in missing_actual_rows)


def test_exact_pairing_comparable_when_forecast_and_actual_present() -> None:
    result = materialize_train_validation_pairing_inputs(_materialize_deps())
    comparable = [
        row for row in result.train_evaluation_input.rows if row.s2_status == "COMPARABLE"
    ]
    assert comparable
    row = comparable[0]
    assert row.actual_physical_key is not None
    assert row.stable_actual_identity is not None
    assert row.forecast_value_kg is not None
    assert row.actual_value_kg is not None
    assert isinstance(row.forecast_value_kg, Decimal)
    assert isinstance(row.actual_value_kg, Decimal)


def test_forecast_unavailable_blocks_materialization_without_packages() -> None:
    result = materialize_train_validation_pairing_inputs(
        _materialize_deps(forecast_unavailable=True)
    )
    assert not result.completed
    assert (
        result.blocker
        == TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER
    )
    assert result.train_pairing_package is None
    assert result.validation_pairing_package is None


def test_native_float_rejected() -> None:
    class _FloatProvider(IncumbentDailyCurveProvider):
        def forecast_kg_for_day(self, cell, *, business_date: date):
            from backend.app.s3_daily_rowset.forecast_port import ForecastDayResult

            return ForecastDayResult(
                availability=ForecastAvailability.AVAILABLE,
                forecast_harvest_quantity_kg=1.5,  # type: ignore[arg-type]
            )

        def forecast_authority_for(self, cell, *, business_date: date, horizon_days: int):
            return _test_forecast_binding_authority()

    deps = TrainValidationPairingMaterializationDeps(
        official_partitions=_small_official_partitions(),
        forecast_replay_entries=_reviewed_forecast_entries(),
        forecast_provider=_FloatProvider(),
        forecast_cutoff_authority_identity=reviewed_grain_identity_set_identity_sha256(),
        forecast_content_identity_sha256="a" * 64,
    )
    result = materialize_train_validation_pairing_inputs(deps)
    assert not result.completed
    assert result.blocker == (
        TrainValidationPairingMaterializationBlocker.NATIVE_FLOAT_IN_BINDING_ROW
    )


def test_deterministic_binding_rowset_and_package_identity() -> None:
    first = materialize_train_validation_pairing_inputs(_materialize_deps())
    second = materialize_train_validation_pairing_inputs(_materialize_deps())
    assert first.completed and second.completed
    assert first.train_stats.s2_binding_row_set_hash == second.train_stats.s2_binding_row_set_hash
    assert (
        first.train_pairing_package.pairing_package_identity
        == second.train_pairing_package.pairing_package_identity
    )
    assert first.train_pairing_package.canonical_hash == second.train_pairing_package.canonical_hash


def test_policy_versions_bound_on_materialized_packages() -> None:
    result = materialize_train_validation_pairing_inputs(_materialize_deps())
    assert result.train_pairing_package.pairing_policy_version == TRAIN_VAL_PAIRING_POLICY_V1
    assert (
        result.train_pairing_package.exact_actual_pairing_policy_version
        == EXACT_ACTUAL_PAIRING_POLICY_V1
    )


def test_package_hash_replay_and_invariants() -> None:
    result = materialize_train_validation_pairing_inputs(_materialize_deps())
    for package in (result.train_pairing_package, result.validation_pairing_package):
        assert verify_pairing_package_hash_replay(package)
        validate_published_pairing_package_invariants(package)
        assert package.s2_binding_row_set_hash == package.evaluation_input.s2_binding_row_set_hash


def test_production_published_registry_remains_empty() -> None:
    materialize_train_validation_pairing_inputs(_materialize_deps())
    assert PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY.count() == 0


def test_membership_proof_requires_official_partition_content() -> None:
    result = materialize_train_validation_pairing_inputs(_materialize_deps())
    assert result.train_membership_proofs
    proof = result.train_membership_proofs[0]
    assert proof.source_partition_identity_sha256
    assert proof.source_partition_content_sha256
    assert proof.source_row_identity


def test_forecast_binding_key_matches_canonical_s2_authority() -> None:
    t7, _, _ = _target_dates()
    official = _small_official_partitions()
    aligned = frozenset(
        {(row.season, row.farm, row.subfarm, row.variety) for row in official.train_rows}
    )
    request = _build_partition_s2_binding_request(
        aligned,
        forecast_cutoff_at=_REVIEWED_CUTOFF,
    )
    authority = _test_forecast_binding_authority()
    key = compute_canonical_forecast_binding_key_hash(
        request,
        season_business_key="2025~2026",
        farm_business_key="farm-a",
        subfarm_business_key="subfarm-1",
        variety_business_key="variety-x",
        forecast_quantile="P50",
        horizon_days=7,
        target_date=t7,
        forecast_authority=authority,
    )
    from backend.app.forecast_quality.train_val_pairing_materialization import (
        _provisional_s2_binding_row_for_key_hash,
    )

    provisional = _provisional_s2_binding_row_for_key_hash(
        request,
        season_business_key="2025~2026",
        farm_business_key="farm-a",
        subfarm_business_key="subfarm-1",
        variety_business_key="variety-x",
        forecast_quantile="P50",
        horizon_days=7,
        target_date=t7,
        forecast_authority=authority,
    )
    assert key == s2_binding_key_hash(request, provisional)
    assert len(key) == 64


def test_materialized_row_forecast_business_key_uses_s2_binding_key_hash() -> None:
    result = materialize_train_validation_pairing_inputs(_materialize_deps())
    comparable = next(
        row for row in result.train_evaluation_input.rows if row.s2_status == "COMPARABLE"
    )
    official = _small_official_partitions()
    aligned = frozenset(
        {(row.season, row.farm, row.subfarm, row.variety) for row in official.train_rows}
    )
    request = _build_partition_s2_binding_request(
        aligned,
        forecast_cutoff_at=_REVIEWED_CUTOFF,
    )
    authority = _test_forecast_binding_authority()
    expected = compute_canonical_forecast_binding_key_hash(
        request,
        season_business_key=comparable.season_business_key,
        farm_business_key=comparable.farm_business_key,
        subfarm_business_key=comparable.subfarm_business_key,
        variety_business_key=comparable.variety_business_key,
        forecast_quantile=comparable.forecast_quantile.value,
        horizon_days=comparable.forecast_horizon_days,
        target_date=comparable.forecast_target_date,
        forecast_authority=authority,
    )
    assert comparable.forecast_business_key == expected


def test_official_hash_constants_match_module() -> None:
    official = _small_official_partitions()
    assert official.train_content_sha256 != OFFICIAL_TRAIN_CONTENT_SHA256
    assert official.validation_content_sha256 != OFFICIAL_VALIDATION_CONTENT_SHA256
