"""Unit tests for the deterministic Farm-total baseline estimator."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from typing import Literal

import pytest

from backend.app.forecast_quality.farm_total_baseline_estimator import (
    FarmTotalBaselineDerivationBlocker,
    FarmTotalBaselineDerivationError,
    FarmTotalBaselineGroupStatus,
    FarmTotalBaselinePoint,
    FarmTotalBaselineTargetKey,
    FarmTotalBaselineTargetStatus,
    derive_farm_total_baseline_estimator,
    project_farm_total_baseline,
)
from backend.app.forecast_quality.farm_total_dataset import (
    FarmTotalDatasetDiagnostics,
    FarmTotalDatasetRow,
    FarmTotalPartitionDataset,
    FarmTotalTrainingDataset,
    compute_partition_dataset_sha256,
)
from backend.app.forecast_quality.farm_total_policy import (
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
)

SEASON = "2025~2026"


def _synthetic_row(
    *,
    group: str,
    harvest_date: date,
    quantity_kg: Decimal,
    area_mu: Decimal = Decimal("100.0"),
    partition: Literal["TRAIN", "VALIDATION"] = "TRAIN",
) -> FarmTotalDatasetRow:
    return FarmTotalDatasetRow(
        season_business_key=SEASON,
        baseline_farm_group_key=group,
        harvest_business_date=harvest_date,
        partition=partition,
        area_mu=area_mu,
        area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
        actual_harvest_quantity_kg=quantity_kg,
        actual_harvest_kg_per_mu=quantity_kg / area_mu,
        source_actual_row_count=1,
        source_farm_business_keys=(f"farm-{group}",),
        area_authority_row_hash=f"area-hash-{group}",
        actual_projection_hash=f"proj-{group}-{harvest_date.isoformat()}",
        row_hash=f"row-{group}-{harvest_date.isoformat()}",
    )


def _synthetic_diagnostics(
    *,
    partition: Literal["TRAIN", "VALIDATION", "TRAIN_PLUS_VALIDATION_AUDIT"],
    row_count: int,
    farm_group_count: int,
    date_count: int,
) -> FarmTotalDatasetDiagnostics:
    return FarmTotalDatasetDiagnostics(
        partition=partition,
        farm_group_count=farm_group_count,
        date_count=date_count,
        row_count=row_count,
        total_area_mu="100.0",
        total_actual_harvest_kg="0",
        kg_per_mu_min=None,
        kg_per_mu_p25=None,
        kg_per_mu_median=None,
        kg_per_mu_p75=None,
        kg_per_mu_max=None,
    )


def _train_dataset(rows: tuple[FarmTotalDatasetRow, ...]) -> FarmTotalTrainingDataset:
    partition_dataset = FarmTotalPartitionDataset(
        partition="TRAIN",
        schema_version="test-schema",
        rows=rows,
        dataset_sha256=compute_partition_dataset_sha256(rows),
    )
    groups = {row.baseline_farm_group_key for row in rows}
    dates = {row.harvest_business_date for row in rows}
    return FarmTotalTrainingDataset(
        partition_dataset=partition_dataset,
        diagnostics=_synthetic_diagnostics(
            partition="TRAIN",
            row_count=len(rows),
            farm_group_count=len(groups),
            date_count=len(dates),
        ),
    )


def _validation_training_dataset(
    rows: tuple[FarmTotalDatasetRow, ...],
) -> FarmTotalTrainingDataset:
    partition_dataset = FarmTotalPartitionDataset(
        partition="VALIDATION",
        schema_version="test-schema",
        rows=rows,
        dataset_sha256=compute_partition_dataset_sha256(rows),
    )
    groups = {row.baseline_farm_group_key for row in rows}
    dates = {row.harvest_business_date for row in rows}
    return FarmTotalTrainingDataset(
        partition_dataset=partition_dataset,
        diagnostics=_synthetic_diagnostics(
            partition="VALIDATION",
            row_count=len(rows),
            farm_group_count=len(groups),
            date_count=len(dates),
        ),
    )


def _target(
    group: str,
    harvest_date: date,
    season: str = SEASON,
) -> FarmTotalBaselineTargetKey:
    return FarmTotalBaselineTargetKey(
        season_business_key=season,
        baseline_farm_group_key=group,
        harvest_business_date=harvest_date,
    )


def _five_date_rows(
    group: str,
    quantities: tuple[Decimal, Decimal, Decimal, Decimal, Decimal],
) -> tuple[FarmTotalDatasetRow, ...]:
    dates = (
        date(2025, 9, 1),
        date(2025, 9, 2),
        date(2025, 9, 3),
        date(2025, 9, 4),
        date(2025, 9, 5),
    )
    return tuple(
        _synthetic_row(group=group, harvest_date=harvest_date, quantity_kg=quantity)
        for harvest_date, quantity in zip(dates, quantities, strict=True)
    )


def test_odd_count_median() -> None:
    rows = (
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 2), quantity_kg=Decimal("2")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 3), quantity_kg=Decimal("9")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 4), quantity_kg=Decimal("10")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 5), quantity_kg=Decimal("100")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    estimate = state.group_estimates[0]
    assert estimate.status is FarmTotalBaselineGroupStatus.READY
    assert estimate.baseline_harvest_quantity_kg == Decimal("9")


def test_even_count_median_requires_six_dates() -> None:
    rows = (
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 2), quantity_kg=Decimal("2")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 3), quantity_kg=Decimal("8")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 4), quantity_kg=Decimal("20")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 5), quantity_kg=Decimal("30")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 6), quantity_kg=Decimal("40")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    estimate = state.group_estimates[0]
    assert estimate.baseline_harvest_quantity_kg == Decimal("14")


def test_decimal_preservation() -> None:
    rows = _five_date_rows(
        "g1",
        (
            Decimal("1.25"),
            Decimal("2.50"),
            Decimal("3.75"),
            Decimal("4.00"),
            Decimal("9.50"),
        ),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    assert state.group_estimates[0].baseline_harvest_quantity_kg == Decimal("3.75")


def test_exactly_five_distinct_train_dates_succeeds() -> None:
    rows = _five_date_rows(
        "g1",
        (
            Decimal("10"),
            Decimal("20"),
            Decimal("30"),
            Decimal("40"),
            Decimal("50"),
        ),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    estimate = state.group_estimates[0]
    assert estimate.train_support_count == 5
    assert estimate.status is FarmTotalBaselineGroupStatus.READY
    projection = project_farm_total_baseline(
        state,
        (_target("g1", date(2025, 9, 1)),),
    )
    assert len(projection.points) == 1


def test_four_distinct_train_dates_fails_closed() -> None:
    rows = (
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 2), quantity_kg=Decimal("2")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 3), quantity_kg=Decimal("3")),
        _synthetic_row(group="g1", harvest_date=date(2025, 9, 4), quantity_kg=Decimal("4")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    estimate = state.group_estimates[0]
    assert estimate.train_support_count == 4
    assert estimate.baseline_harvest_quantity_kg is None
    projection = project_farm_total_baseline(
        state,
        (_target("g1", date(2025, 9, 1)),),
    )
    assert projection.points == ()
    assert (
        projection.target_outcomes[0].status
        is FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT
    )


def test_two_groups_derive_independently() -> None:
    rows = (
        *_five_date_rows(
            "g1",
            (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
        ),
        *_five_date_rows(
            "g2",
            (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
        ),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    by_group = {estimate.baseline_farm_group_key: estimate for estimate in state.group_estimates}
    assert by_group["g1"].baseline_harvest_quantity_kg == Decimal("3")
    assert by_group["g2"].baseline_harvest_quantity_kg == Decimal("30")


def test_unsupported_group_does_not_block_supported_group() -> None:
    rows = (
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 2), quantity_kg=Decimal("2")),
        *_five_date_rows(
            "strong",
            (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
        ),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    projection = project_farm_total_baseline(
        state,
        (
            _target("weak", date(2025, 9, 1)),
            _target("strong", date(2025, 9, 1)),
        ),
    )
    assert projection.points[0].baseline_farm_group_key == "strong"
    assert projection.points[0].baseline_harvest_quantity_kg == Decimal("30")
    outcomes_by_group = {
        outcome.target_key.baseline_farm_group_key: outcome.status
        for outcome in projection.target_outcomes
    }
    assert outcomes_by_group["weak"] is FarmTotalBaselineTargetStatus.INSUFFICIENT_TRAIN_SUPPORT
    assert outcomes_by_group["strong"] is FarmTotalBaselineTargetStatus.READY


def test_no_cross_group_pooling() -> None:
    rows = (
        *_five_date_rows(
            "g1",
            (Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1")),
        ),
        *_five_date_rows(
            "g2",
            (Decimal("9"), Decimal("9"), Decimal("9"), Decimal("9"), Decimal("9")),
        ),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    by_group = {estimate.baseline_farm_group_key: estimate for estimate in state.group_estimates}
    assert by_group["g1"].baseline_harvest_quantity_kg == Decimal("1")
    assert by_group["g2"].baseline_harvest_quantity_kg == Decimal("9")


def test_area_mu_invariance() -> None:
    rows = (
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 1),
            quantity_kg=Decimal("10"),
            area_mu=Decimal("100.0"),
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 2),
            quantity_kg=Decimal("20"),
            area_mu=Decimal("200.0"),
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 3),
            quantity_kg=Decimal("30"),
            area_mu=Decimal("300.0"),
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 4),
            quantity_kg=Decimal("40"),
            area_mu=Decimal("400.0"),
        ),
        _synthetic_row(
            group="g1",
            harvest_date=date(2025, 9, 5),
            quantity_kg=Decimal("50"),
            area_mu=Decimal("500.0"),
        ),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    assert state.group_estimates[0].baseline_harvest_quantity_kg == Decimal("30")


def test_unseen_target_group_fails_closed() -> None:
    rows = _five_date_rows(
        "known",
        (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    projection = project_farm_total_baseline(
        state,
        (_target("missing", date(2025, 9, 1)),),
    )
    assert projection.points == ()
    assert projection.target_outcomes[0].status is FarmTotalBaselineTargetStatus.UNSEEN_GROUP


def test_missing_target_date_is_skipped() -> None:
    rows = _five_date_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    projection = project_farm_total_baseline(
        state,
        (_target("g1", date(2025, 9, 2)),),
    )
    assert len(projection.points) == 1
    assert projection.points[0].harvest_business_date == date(2025, 9, 2)
    assert projection.points[0].baseline_harvest_quantity_kg == Decimal("30")


def test_deterministic_group_ordering() -> None:
    rows = (
        *_five_date_rows(
            "zeta",
            (Decimal("5"), Decimal("5"), Decimal("5"), Decimal("5"), Decimal("5")),
        ),
        *_five_date_rows(
            "alpha",
            (Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1")),
        ),
    )
    shuffled = (
        rows[5],
        rows[0],
        rows[6],
        rows[1],
        rows[7],
        rows[2],
        rows[8],
        rows[3],
        rows[9],
        rows[4],
    )
    state_a = derive_farm_total_baseline_estimator(_train_dataset(rows))
    state_b = derive_farm_total_baseline_estimator(_train_dataset(shuffled))
    assert state_a == state_b
    assert [estimate.baseline_farm_group_key for estimate in state_a.group_estimates] == [
        "alpha",
        "zeta",
    ]


def test_deterministic_target_ordering() -> None:
    rows = _five_date_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    targets = (
        _target("g1", date(2025, 9, 3)),
        _target("g1", date(2025, 9, 1)),
        _target("g1", date(2025, 9, 2)),
    )
    projection = project_farm_total_baseline(state, targets)
    emitted_dates = [point.harvest_business_date for point in projection.points]
    outcome_dates = [
        outcome.target_key.harvest_business_date for outcome in projection.target_outcomes
    ]
    assert emitted_dates == [date(2025, 9, 1), date(2025, 9, 2), date(2025, 9, 3)]
    assert outcome_dates == emitted_dates


def test_validation_actual_leakage_protection() -> None:
    rows = _five_date_rows(
        "g1",
        (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(rows))
    target = _target("g1", date(2025, 9, 1))
    projection_a = project_farm_total_baseline(state, (target,))

    validation_row_a = _synthetic_row(
        group="g1",
        harvest_date=date(2025, 9, 1),
        quantity_kg=Decimal("999"),
        partition="VALIDATION",
    )
    validation_row_b = _synthetic_row(
        group="g1",
        harvest_date=date(2025, 9, 1),
        quantity_kg=Decimal("1"),
        partition="VALIDATION",
    )
    assert (
        validation_row_a.actual_harvest_quantity_kg != validation_row_b.actual_harvest_quantity_kg
    )
    key_from_a = FarmTotalBaselineTargetKey(
        season_business_key=validation_row_a.season_business_key,
        baseline_farm_group_key=validation_row_a.baseline_farm_group_key,
        harvest_business_date=validation_row_a.harvest_business_date,
    )
    key_from_b = FarmTotalBaselineTargetKey(
        season_business_key=validation_row_b.season_business_key,
        baseline_farm_group_key=validation_row_b.baseline_farm_group_key,
        harvest_business_date=validation_row_b.harvest_business_date,
    )
    assert key_from_a == key_from_b
    projection_b = project_farm_total_baseline(state, (key_from_b,))
    assert projection_a == projection_b


def test_derivation_rejects_non_train_partition() -> None:
    rows = _five_date_rows(
        "g1",
        (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")),
    )
    validation_rows = tuple(
        _synthetic_row(
            group=row.baseline_farm_group_key,
            harvest_date=row.harvest_business_date,
            quantity_kg=row.actual_harvest_quantity_kg,
            partition="VALIDATION",
        )
        for row in rows
    )
    with pytest.raises(FarmTotalBaselineDerivationError) as exc_info:
        derive_farm_total_baseline_estimator(_validation_training_dataset(validation_rows))
    assert exc_info.value.blocker is FarmTotalBaselineDerivationBlocker.NON_TRAIN_PARTITION


def test_no_p80_p90_surface() -> None:
    point_fields = {field.name for field in dataclasses.fields(FarmTotalBaselinePoint)}
    assert "baseline_harvest_quantity_kg" in point_fields
    forbidden = {name for name in point_fields if "p80" in name.lower() or "p90" in name.lower()}
    assert forbidden == set()


def test_target_blockers_emit_no_numeric_baseline_point() -> None:
    insufficient_rows = (
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 1), quantity_kg=Decimal("1")),
        _synthetic_row(group="weak", harvest_date=date(2025, 9, 2), quantity_kg=Decimal("2")),
    )
    state = derive_farm_total_baseline_estimator(_train_dataset(insufficient_rows))
    projection = project_farm_total_baseline(
        state,
        (
            _target("weak", date(2025, 9, 1)),
            _target("missing", date(2025, 9, 1)),
        ),
    )
    assert projection.points == ()
    assert all(outcome.point is None for outcome in projection.target_outcomes)
