"""Live TRAIN/VALIDATION pairing authority handoff tests (R1)."""

from __future__ import annotations

import ast
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from backend.app.forecast_quality.train_val_pairing import ACCEPTED_TRAIN_PARTITION_IDENTITY
from backend.app.forecast_quality.train_val_pairing_materialization import (
    OfficialPartitionRows,
    TrainValidationPairingMaterializationBlocker,
    _aligned_grains,
    _build_membership_index,
    _build_partition_binding_rows,
    _build_partition_s2_binding_request,
    compute_canonical_forecast_binding_key_hash,
    derive_materialization_grain_union,
    materialize_train_validation_pairing_inputs,
    materialize_train_validation_pairing_inputs_live,
)
from backend.app.rolling_backtest.schemas import S2ForecastAuthorityBundle
from backend.app.s2_materialized_dataset.lane_d.canonical import build_partition_bytes
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.forecast_port import (
    FakeIncumbentDailyCurveProvider,
    ForecastAvailability,
)
from backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain import (
    LiveIncumbentForecastDailyCurveObtainResult,
    obtain_live_incumbent_forecast_daily_curve_provider,
    reset_live_incumbent_forecast_daily_curve_provider_cache,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_loader import (
    PitVisibleDailyForecastCell,
    PitVisibleIncumbentDailyCurveIndex,
)
from backend.app.s3_daily_rowset.pit_visible_incumbent_daily_curve_provider import (
    PitVisibleIncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MODEL_ID,
)
from backend.app.s3_daily_rowset.schemas import HORIZON_DAYS, EvaluationInstanceCell
from backend.app.s3_daily_rowset.window import expected_forecast_target_date
from backend.tests.forecast_quality.test_s3_b_train_val_pairing_materialization_r1 import (
    _materializable_row,
    _materialize_deps,
    _reviewed_forecast_entries,
    _small_official_partitions,
    _target_dates,
    _test_forecast_binding_authority,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_ROOT = _REPO_ROOT / "backend" / "app"
_REVIEWED_CUTOFF = datetime.fromisoformat(REVIEW_CUTOFF_AT)
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _authority_variant(label: str) -> S2ForecastAuthorityBundle:
    base = _test_forecast_binding_authority()
    digest = f"{label}".encode().hex().zfill(64)[:64]
    return base.model_copy(update={"forecast_run_identity_hash": digest})


def _membership_index_for_partition(
    partition: str,
    rows: tuple[MaterializableRow, ...],
):
    from backend.app.forecast_quality.train_val_pairing import (
        ACCEPTED_VALIDATION_PARTITION_IDENTITY,
    )

    identity = (
        ACCEPTED_TRAIN_PARTITION_IDENTITY
        if partition == "TRAIN"
        else ACCEPTED_VALIDATION_PARTITION_IDENTITY
    )
    return _build_membership_index(partition=partition, partition_identity=identity, rows=rows)


def _union_grains(official: OfficialPartitionRows) -> frozenset[tuple[str, str, str, str]]:
    grains = derive_materialization_grain_union(official)
    assert not isinstance(grains, TrainValidationPairingMaterializationBlocker)
    return grains


def _pit_visible_provider(
    *,
    grains: frozenset[tuple[str, str, str, str]],
    authorities_by_horizon: dict[int, S2ForecastAuthorityBundle] | None = None,
) -> PitVisibleIncumbentDailyCurveProvider:
    cells: dict[tuple[str, str, str, str, str, date], PitVisibleDailyForecastCell] = {}
    grain_counts = {grain: 1 for grain in grains}
    for season, farm, subfarm, variety in grains:
        for quantile in ("P50", "P80", "P90"):
            binding_authorities: dict[int, S2ForecastAuthorityBundle] = {}
            for horizon_days in HORIZON_DAYS:
                if (
                    authorities_by_horizon is not None
                    and horizon_days not in authorities_by_horizon
                ):
                    continue
                authority = (
                    authorities_by_horizon[horizon_days]
                    if authorities_by_horizon is not None
                    else _test_forecast_binding_authority()
                )
                binding_authorities[horizon_days] = authority
            for horizon_days in HORIZON_DAYS:
                target_date = expected_forecast_target_date(_REVIEWED_CUTOFF, horizon_days)
                if horizon_days not in binding_authorities:
                    continue
                authority = binding_authorities[horizon_days]
                row_hash = authority.daily_row_identity_hash
                cells[(season, farm, subfarm, variety, quantile, target_date)] = (
                    PitVisibleDailyForecastCell(
                        forecast_kg=Decimal("5.0"),
                        task8_forecast_run_id=401,
                        task8_daily_row_id=1,
                        task8_daily_prediction_payload_hash="a" * 64,
                        core_daily_row_identity_hash=row_hash,
                        forecast_run_identity_hash=authority.forecast_run_identity_hash,
                        binding_authorities=binding_authorities,
                    )
                )
    index = PitVisibleIncumbentDailyCurveIndex(
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        cells=cells,
        grain_forecast_run_count=grain_counts,
    )
    return PitVisibleIncumbentDailyCurveProvider(index=index)


def test_live_materialization_passes_exact_union_grains() -> None:
    """A: LIVE_MATERIALIZATION_PASSES_EXACT_UNION_GRAINS."""
    official = _small_official_partitions()
    union = _union_grains(official)
    provider = _pit_visible_provider(grains=union)
    with patch(
        "backend.app.forecast_quality.train_val_pairing_materialization."
        "obtain_live_incumbent_forecast_daily_curve_provider",
    ) as obtain:
        obtain.return_value = LiveIncumbentForecastDailyCurveObtainResult(
            obtained=True,
            provider=provider,
            forecast_cutoff_at=_REVIEWED_CUTOFF,
        )
        with patch(
            "backend.app.forecast_quality.train_val_pairing_materialization."
            "attest_accepted_s2_train_val_source_002_row_level_read",
        ) as attest:
            attest.return_value = type("Attestation", (), {"attested": True})()
            with patch(
                "backend.app.forecast_quality.train_val_pairing_materialization."
                "obtain_accepted_s2_train_val_content_bytes_from_bound_live_session",
            ) as partition_obtain:
                partition_obtain.return_value = type(
                    "PartitionObtain",
                    (),
                    {
                        "obtained": True,
                        "train_content_bytes": build_partition_bytes(official.train_rows),
                        "validation_content_bytes": build_partition_bytes(official.validation_rows),
                    },
                )()
                with patch(
                    "backend.app.forecast_quality.train_val_pairing_materialization."
                    "IncumbentForecastReplaySource",
                ) as replay_cls:
                    replay_cls.return_value.uses_harvest_date_as_forecast_cutoff = False
                    replay_cls.return_value.obtain.return_value = _reviewed_forecast_entries()
                    with patch(
                        "backend.app.forecast_quality.train_val_pairing_materialization."
                        "load_official_partition_rows_from_content_bytes",
                        return_value=official,
                    ):
                        materialize_train_validation_pairing_inputs_live()
        obtain.assert_called_once()
        assert obtain.call_args.kwargs["materialization_grains"] == union


def test_no_argument_provider_call_removed() -> None:
    """B: NO_ARGUMENT_PROVIDER_CALL_REMOVED."""
    source = (_APP_ROOT / "forecast_quality" / "train_val_pairing_materialization.py").read_text(
        encoding="utf-8"
    )
    live_start = source.index("def materialize_train_validation_pairing_inputs_live")
    live_end = source.index("def build_materialization_evidence_payload", live_start)
    live_source = live_start and source[live_start:live_end]
    tree = ast.parse(live_source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == (
            "obtain_live_incumbent_forecast_daily_curve_provider"
        ):
            assert any(kw.arg == "materialization_grains" for kw in node.keywords), (
                "live obtain must pass materialization_grains"
            )
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "obtain_live_incumbent_forecast_daily_curve_provider"
        ):
            assert any(kw.arg == "materialization_grains" for kw in node.keywords)


def test_global_forecast_binding_authority_removed() -> None:
    """C: GLOBAL_FORECAST_BINDING_AUTHORITY_REMOVED."""
    materialization_source = (
        _APP_ROOT / "forecast_quality" / "train_val_pairing_materialization.py"
    ).read_text(encoding="utf-8")
    obtain_source = (
        _APP_ROOT / "s3_daily_rowset" / "incumbent_forecast_daily_curve_live_obtain.py"
    ).read_text(encoding="utf-8")
    assert (
        "forecast_binding_authority:"
        not in materialization_source.split("class TrainValidationPairingMaterializationDeps", 1)[
            1
        ].split("class ", 1)[0]
    )
    assert (
        "forecast_binding_authority:"
        not in obtain_source.split("class LiveIncumbentForecastDailyCurveObtainResult", 1)[1].split(
            "\n\n", 1
        )[0]
    )


def test_per_cell_authority_used_for_binding_key() -> None:
    """D: PER_CELL_AUTHORITY_USED_FOR_BINDING_KEY."""
    t7, t14, _ = _target_dates()
    official = OfficialPartitionRows(
        train_rows=(
            _materializable_row(
                harvest_business_date=t7,
                season="2025~2026",
                farm="farm-a",
                subfarm="subfarm-1",
                variety="variety-x",
                source_row_identity="train-a",
            ),
            _materializable_row(
                harvest_business_date=t14,
                season="2025~2026",
                farm="farm-b",
                subfarm="subfarm-2",
                variety="variety-y",
                source_row_identity="train-b",
            ),
        ),
        validation_rows=(),
        train_content_sha256="a" * 64,
        validation_content_sha256="b" * 64,
    )
    train_index, _ = _membership_index_for_partition("TRAIN", official.train_rows)
    aligned = _aligned_grains(train_index)
    authority_a = _authority_variant("cell-a")
    authority_b = _authority_variant("cell-b")
    provider = FakeIncumbentDailyCurveProvider(
        forecasts={t7: Decimal("1.0"), t14: Decimal("2.0")},
        authorities={
            (t7, 7): authority_a,
            (t14, 14): authority_b,
        },
        default_authority=authority_a,
    )
    request = _build_partition_s2_binding_request(aligned, forecast_cutoff_at=_REVIEWED_CUTOFF)
    rows_result = _build_partition_binding_rows(
        partition="TRAIN",
        membership_index=train_index,
        aligned_grains=aligned,
        forecast_entries=_reviewed_forecast_entries(),
        forecast_provider=provider,
        s2_binding_request=request,
    )
    assert not isinstance(rows_result, TrainValidationPairingMaterializationBlocker)
    rows, _ = rows_result
    comparable = [
        row
        for row in rows
        if row.s2_status == "COMPARABLE"
        and (
            (row.farm_business_key == "farm-a" and row.forecast_horizon_days == 7)
            or (row.farm_business_key == "farm-b" and row.forecast_horizon_days == 14)
        )
        and row.forecast_quantile.value == "P50"
    ]
    assert len(comparable) == 2
    keys = {row.forecast_business_key for row in comparable}
    expected_keys = {
        compute_canonical_forecast_binding_key_hash(
            request,
            season_business_key=row.season_business_key,
            farm_business_key=row.farm_business_key,
            subfarm_business_key=row.subfarm_business_key,
            variety_business_key=row.variety_business_key,
            forecast_quantile=row.forecast_quantile.value,
            horizon_days=row.forecast_horizon_days,
            target_date=row.forecast_target_date,
            forecast_authority=authority_a if row.farm_business_key == "farm-a" else authority_b,
        )
        for row in comparable
    }
    assert keys == expected_keys
    assert len(keys) == 2


def test_per_horizon_authority_used() -> None:
    """E: PER_HORIZON_AUTHORITY_USED."""
    t7, t14, t21 = _target_dates()
    official = OfficialPartitionRows(
        train_rows=(
            _materializable_row(harvest_business_date=t7, source_row_identity="train-7"),
            _materializable_row(harvest_business_date=t14, source_row_identity="train-14"),
            _materializable_row(harvest_business_date=t21, source_row_identity="train-21"),
        ),
        validation_rows=(),
        train_content_sha256="a" * 64,
        validation_content_sha256="b" * 64,
    )
    train_index, _ = _membership_index_for_partition("TRAIN", official.train_rows)
    aligned = _aligned_grains(train_index)
    authorities = {
        (t7, 7): _authority_variant("horizon-7"),
        (t14, 14): _authority_variant("horizon-14"),
        (t21, 21): _authority_variant("horizon-21"),
    }
    provider = FakeIncumbentDailyCurveProvider(
        forecasts={t7: Decimal("1.0"), t14: Decimal("1.0"), t21: Decimal("1.0")},
        authorities=authorities,
        default_authority=_test_forecast_binding_authority(),
    )
    request = _build_partition_s2_binding_request(aligned, forecast_cutoff_at=_REVIEWED_CUTOFF)
    rows_result = _build_partition_binding_rows(
        partition="TRAIN",
        membership_index=train_index,
        aligned_grains=aligned,
        forecast_entries=(_reviewed_forecast_entries()[0],),
        forecast_provider=provider,
        s2_binding_request=request,
    )
    assert not isinstance(rows_result, TrainValidationPairingMaterializationBlocker)
    rows, _ = rows_result
    comparable = [row for row in rows if row.s2_status == "COMPARABLE"]
    assert len(comparable) == 3
    keys_by_horizon = {row.forecast_horizon_days: row.forecast_business_key for row in comparable}
    for horizon_days, target_date, authority in (
        (7, t7, authorities[(t7, 7)]),
        (14, t14, authorities[(t14, 14)]),
        (21, t21, authorities[(t21, 21)]),
    ):
        expected = compute_canonical_forecast_binding_key_hash(
            request,
            season_business_key="2025~2026",
            farm_business_key="farm-a",
            subfarm_business_key="subfarm-1",
            variety_business_key="variety-x",
            forecast_quantile="P50",
            horizon_days=horizon_days,
            target_date=target_date,
            forecast_authority=authority,
        )
        assert keys_by_horizon[horizon_days] == expected
    assert len(set(keys_by_horizon.values())) == 3


def test_forecast_value_and_authority_same_cell() -> None:
    """F: FORECAST_VALUE_AND_AUTHORITY_SAME_CELL."""
    official = _small_official_partitions()
    union = _union_grains(official)
    authority = _authority_variant("same-cell")
    provider = _pit_visible_provider(grains=union, authorities_by_horizon={7: authority})
    t7, _, _ = _target_dates()
    cell = EvaluationInstanceCell(
        season="2025~2026",
        farm="farm-a",
        subfarm="subfarm-1",
        variety="variety-x",
        model_id=REVIEW_MODEL_ID,
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        forecast_quantile="P50",
    )
    value = provider.forecast_kg_for_day(cell, business_date=t7)
    resolved = provider.forecast_authority_for(cell, business_date=t7, horizon_days=7)
    assert value.availability == ForecastAvailability.AVAILABLE
    assert resolved == authority
    matched = provider._cell_for(cell, business_date=t7)
    assert matched is not None
    assert resolved.daily_row_identity_hash == matched.core_daily_row_identity_hash


def test_missing_exact_authority_fails_closed() -> None:
    """G: MISSING_EXACT_AUTHORITY_FAILS_CLOSED."""
    t7, _, _ = _target_dates()
    official = OfficialPartitionRows(
        train_rows=(_materializable_row(harvest_business_date=t7, source_row_identity="train-7"),),
        validation_rows=(),
        train_content_sha256="a" * 64,
        validation_content_sha256="b" * 64,
    )
    train_index, _ = _membership_index_for_partition("TRAIN", official.train_rows)
    aligned = _aligned_grains(train_index)
    provider = FakeIncumbentDailyCurveProvider(
        forecasts={t7: Decimal("1.0")},
        default_authority=None,
    )
    request = _build_partition_s2_binding_request(aligned, forecast_cutoff_at=_REVIEWED_CUTOFF)
    blocker = _build_partition_binding_rows(
        partition="TRAIN",
        membership_index=train_index,
        aligned_grains=aligned,
        forecast_entries=_reviewed_forecast_entries(),
        forecast_provider=provider,
        s2_binding_request=request,
    )
    assert blocker == (
        TrainValidationPairingMaterializationBlocker.MISSING_EXACT_FORECAST_BINDING_AUTHORITY
    )


def test_wrong_horizon_authority_fails_closed() -> None:
    """H: WRONG_HORIZON_AUTHORITY_FAILS_CLOSED."""
    t7, _, _ = _target_dates()
    official = _small_official_partitions()
    union = _union_grains(official)
    authority_7 = _authority_variant("horizon-7-only")
    provider = _pit_visible_provider(grains=union, authorities_by_horizon={7: authority_7})
    cell = EvaluationInstanceCell(
        season="2025~2026",
        farm="farm-a",
        subfarm="subfarm-1",
        variety="variety-x",
        model_id=REVIEW_MODEL_ID,
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        forecast_quantile="P50",
    )
    assert provider.forecast_authority_for(cell, business_date=t7, horizon_days=7) == authority_7
    assert provider.forecast_authority_for(cell, business_date=t7, horizon_days=14) is None


def test_wrong_daily_row_identity_fails_closed() -> None:
    """I: WRONG_DAILY_ROW_IDENTITY_FAILS_CLOSED."""
    authority = _test_forecast_binding_authority().model_copy(
        update={"daily_row_identity_hash": "f" * 64}
    )
    index = PitVisibleIncumbentDailyCurveIndex(
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        cells={
            (
                "2025~2026",
                "farm-a",
                "subfarm-1",
                "variety-x",
                "P50",
                _target_dates()[0],
            ): PitVisibleDailyForecastCell(
                forecast_kg=Decimal("5.0"),
                task8_forecast_run_id=401,
                task8_daily_row_id=1,
                task8_daily_prediction_payload_hash="a" * 64,
                core_daily_row_identity_hash="2" * 64,
                forecast_run_identity_hash=authority.forecast_run_identity_hash,
                binding_authorities={7: authority},
            )
        },
        grain_forecast_run_count={
            ("2025~2026", "farm-a", "subfarm-1", "variety-x"): 1,
        },
    )
    provider = PitVisibleIncumbentDailyCurveProvider(index=index)
    t7, _, _ = _target_dates()
    cell = EvaluationInstanceCell(
        season="2025~2026",
        farm="farm-a",
        subfarm="subfarm-1",
        variety="variety-x",
        model_id=REVIEW_MODEL_ID,
        forecast_cutoff_at=_REVIEWED_CUTOFF,
        forecast_quantile="P50",
    )
    assert provider.forecast_authority_for(cell, business_date=t7, horizon_days=7) is None


def test_cache_grain_set_isolation() -> None:
    """J: CACHE_GRAIN_SET_ISOLATION."""
    reset_live_incumbent_forecast_daily_curve_provider_cache()
    grains_a = frozenset({("2025~2026", "farm-a", "subfarm-1", "variety-x")})
    grains_b = frozenset({("2025~2026", "farm-b", "subfarm-2", "variety-y")})
    provider_a = _pit_visible_provider(grains=grains_a)
    provider_b = _pit_visible_provider(grains=grains_b)

    with patch(
        "backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain."
        "_obtain_with_async_session_maker",
    ) as obtain_async:
        obtain_async.side_effect = [
            LiveIncumbentForecastDailyCurveObtainResult(
                obtained=True,
                provider=provider_a,
                forecast_cutoff_at=_REVIEWED_CUTOFF,
            ),
            LiveIncumbentForecastDailyCurveObtainResult(
                obtained=True,
                provider=provider_b,
                forecast_cutoff_at=_REVIEWED_CUTOFF,
            ),
        ]
        first = obtain_live_incumbent_forecast_daily_curve_provider(materialization_grains=grains_a)
        second = obtain_live_incumbent_forecast_daily_curve_provider(
            materialization_grains=grains_b
        )
    assert first.provider is provider_a
    assert second.provider is provider_b
    reset_live_incumbent_forecast_daily_curve_provider_cache()


def test_train_validation_only_grain_derivation() -> None:
    """K: TRAIN_VALIDATION_ONLY."""
    official = _small_official_partitions()
    union = _union_grains(official)
    train_index, _ = _membership_index_for_partition("TRAIN", official.train_rows)
    validation_index, _ = _membership_index_for_partition(
        "VALIDATION",
        official.validation_rows,
    )
    train_grains = _aligned_grains(train_index)
    validation_grains = _aligned_grains(validation_index)
    assert union == train_grains | validation_grains
    assert len(train_grains) == 1
    assert len(validation_grains) == 1


def test_live_provider_production_contract() -> None:
    """L: LIVE_PROVIDER_PRODUCTION_CONTRACT."""
    provider = _pit_visible_provider(
        grains=frozenset({("2025~2026", "farm-a", "subfarm-1", "variety-x")})
    )
    assert provider.is_lawful_production_provider is True
    assert provider.is_placeholder_provider is False


def test_materialization_pure_function_regression() -> None:
    """N: MATERIALIZATION_PURE_FUNCTION_REGRESSION."""
    result = materialize_train_validation_pairing_inputs(_materialize_deps())
    assert result.completed
    assert result.test_row_count == 0
