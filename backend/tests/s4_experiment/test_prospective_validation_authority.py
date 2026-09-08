"""Hostile, synthetic contract tests for the prospective S4 authority scanner."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.app.forecast_authority.retention import (
    ForecastAuthorityMissingError,
    ForecastAuthorityPostCutoffError,
    PersistedForecastAuthority,
    PersistedForecastAuthorityDaily,
)
from backend.app.s4_prospective_authority import (
    MINIMUM_POST_TEST_TARGET_DATE,
    BusinessGrainKey,
    ProspectiveAuthorityContractError,
    ProspectiveComparableRow,
    ProspectiveForecastAuthority,
    ProspectiveLabelRow,
    ProspectiveLabelSnapshot,
    _contains_test_marker,
    _forecast_evidence_from_capture,
    _load_verified_label_snapshot,
    _pair,
    _read_capture,
    build_proposed_identity_hashes,
    is_post_test_target_date,
    require_complete_daily_curve,
    scan_prospective_validation_authority,
    target_dates_for_cutoff,
)

UTC_CUTOFF = datetime(2026, 4, 17, 0, 0, tzinfo=UTC)
GRAIN = BusinessGrainKey("2025-2026", "farm-a", "subfarm-a", "variety-a")
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _forecast_pair() -> tuple[Any, PersistedForecastAuthority]:
    daily = tuple(
        PersistedForecastAuthorityDaily(
            prediction_date=UTC_CUTOFF.date() + timedelta(days=index),
            p50_kg=Decimal("1.000000"),
            p80_kg=Decimal("2.000000"),
            p90_kg=Decimal("3.000000"),
            cumulative_p50_kg=Decimal("1.000000"),
            cumulative_p80_kg=Decimal("2.000000"),
            cumulative_p90_kg=Decimal("3.000000"),
            phenology_coordinate_day=Decimal("1.000000"),
            curve_share=Decimal("0.0476190476"),
            confidence_level="PRODUCTION",
            quality_flags=(),
            source_daily_prediction_id=index,
            source_created_at=UTC_CUTOFF,
            row_hash=HASH_C,
        )
        for index in range(1, 22)
    )
    authority = PersistedForecastAuthority(
        forecast_identity=HASH_A,
        forecast_cutoff_at=UTC_CUTOFF,
        forecast_available_at=UTC_CUTOFF,
        business_grain_snapshot={
            "grain": "SEASON_X_FARM_X_SUBFARM_X_VARIETY",
            "season": {"id": 1},
            "factory": {"id": 1},
            "grains": [GRAIN.payload()],
        },
        plan_snapshot={"id": 1},
        weather_snapshot={"id": 1},
        task8_snapshot={"daily_row_ids": list(range(1, 22))},
        task9_snapshot={"run": {"id": 1}, "member_row_count": 1},
        task10_snapshot={},
        core_snapshot={"run": {"id": 1}, "daily_row_hashes": [HASH_C]},
        governance_snapshot={"model_identity": "V0_2_CURRENT_MODEL"},
        daily_predictions=daily,
        authority_hash=HASH_B,
    )
    capture = SimpleNamespace(
        authority_scope="PRODUCTION",
        status="CAPTURED",
        canonical_payload={"authority_scope": "PRODUCTION"},
        forecast_identity=HASH_A,
        authority_hash=HASH_B,
        business_grain_hash=HASH_A,
        task8_daily_artifact_hash=HASH_B,
        code_authority_hash=HASH_C,
        source_lineage_hash=HASH_A,
        daily_row_count=21,
        forecast_cutoff_at=UTC_CUTOFF,
        forecast_created_at=UTC_CUTOFF,
        forecast_available_at=UTC_CUTOFF,
        code_authority_available_at=UTC_CUTOFF,
    )
    return capture, authority


def _forecast_evidence() -> ProspectiveForecastAuthority:
    capture, authority = _forecast_pair()
    return _forecast_evidence_from_capture(capture, authority)


def _label_snapshot(
    *, date_value: date | None = None, quantity: str = "10.000000"
) -> ProspectiveLabelSnapshot:
    value = date_value or date(2026, 4, 24)
    row = ProspectiveLabelRow(
        snapshot_identity="snapshot-1",
        snapshot_request_identity_hash=HASH_A,
        snapshot_instance_identity_hash=HASH_B,
        label_snapshot_hash=HASH_C,
        exclusion_manifest_hash=HASH_A,
        label_row_set_hash=HASH_B,
        row_hash=HASH_C,
        grain=GRAIN,
        harvest_business_date=value,
        actual_harvest_quantity_kg=Decimal(quantity),
    )
    return ProspectiveLabelSnapshot(
        snapshot_identity="snapshot-1",
        snapshot_request_identity_hash=HASH_A,
        snapshot_instance_identity_hash=HASH_B,
        label_snapshot_hash=HASH_C,
        exclusion_manifest_hash=HASH_A,
        label_row_set_hash=HASH_B,
        rows=(row,),
    )


def test_historical_validation_date_cannot_be_relabelled_prospective() -> None:
    assert not is_post_test_target_date(date(2026, 3, 9))
    assert not is_post_test_target_date(date(2026, 1, 31))


def test_test_start_target_date_is_rejected() -> None:
    assert not is_post_test_target_date(date(2026, 3, 10))


def test_test_end_target_date_is_rejected() -> None:
    assert not is_post_test_target_date(date(2026, 4, 16))


def test_first_post_test_target_date_is_permitted() -> None:
    assert MINIMUM_POST_TEST_TARGET_DATE == date(2026, 4, 17)
    assert is_post_test_target_date(date(2026, 4, 17))


def test_synthetic_authority_marker_is_rejected() -> None:
    with pytest.raises(ProspectiveAuthorityContractError, match="TEST_OR_INVALID"):
        capture, authority = _forecast_pair()
        authority = replace(
            authority,
            business_grain_snapshot={"grain": "S2-FIXTURE", "grains": []},
        )
        _forecast_evidence_from_capture(capture, authority)


@pytest.mark.asyncio
async def test_missing_forecast_authority_is_blocked() -> None:
    async def loader(_session: Any, **_: Any) -> PersistedForecastAuthority:
        raise ForecastAuthorityMissingError()

    with pytest.raises(ProspectiveAuthorityContractError, match="FORECAST_AUTHORITY_MISSING"):
        await _read_capture(
            cast(Any, SimpleNamespace()),
            cast(
                Any,
                SimpleNamespace(
                    forecast_identity=HASH_A,
                    forecast_cutoff_at=UTC_CUTOFF,
                    forecast_created_at=UTC_CUTOFF,
                    forecast_available_at=UTC_CUTOFF,
                    code_authority_available_at=UTC_CUTOFF,
                ),
            ),
            loader=loader,
        )


@pytest.mark.asyncio
async def test_pit_post_cutoff_authority_is_blocked() -> None:
    async def loader(_session: Any, **_: Any) -> PersistedForecastAuthority:
        raise ForecastAuthorityPostCutoffError()

    with pytest.raises(ProspectiveAuthorityContractError, match="PIT_POST_CUTOFF"):
        # The production reader is deliberately replaced only for this pure
        # contract test; the scanner's official default remains the reader.
        await _read_capture(
            cast(Any, SimpleNamespace()),
            cast(
                Any,
                SimpleNamespace(
                    forecast_identity=HASH_A,
                    forecast_cutoff_at=UTC_CUTOFF,
                    forecast_created_at=UTC_CUTOFF,
                    forecast_available_at=UTC_CUTOFF,
                    code_authority_available_at=UTC_CUTOFF,
                ),
            ),
            loader=loader,
        )


def test_forecast_authority_hash_mismatch_is_blocked() -> None:
    capture, authority = _forecast_pair()
    authority = PersistedForecastAuthority(
        forecast_identity=HASH_C,
        forecast_cutoff_at=authority.forecast_cutoff_at,
        forecast_available_at=authority.forecast_available_at,
        business_grain_snapshot=authority.business_grain_snapshot,
        plan_snapshot=authority.plan_snapshot,
        weather_snapshot=authority.weather_snapshot,
        task8_snapshot=authority.task8_snapshot,
        task9_snapshot=authority.task9_snapshot,
        task10_snapshot=authority.task10_snapshot,
        core_snapshot=authority.core_snapshot,
        governance_snapshot=authority.governance_snapshot,
        daily_predictions=authority.daily_predictions,
        authority_hash=authority.authority_hash,
    )
    with pytest.raises(ProspectiveAuthorityContractError, match="HASH_MISMATCH"):
        _forecast_evidence_from_capture(capture, authority)


def test_final_adjudicated_snapshot_is_not_substituted() -> None:
    # The production label loader admits only AS_OF_EVALUATION.  A final
    # snapshot cannot be represented as a prospective evidence object.
    assert not hasattr(ProspectiveLabelSnapshot, "visibility_mode")


@pytest.mark.asyncio
async def test_final_adjudicated_snapshot_is_rejected_by_loader() -> None:
    with pytest.raises(ProspectiveAuthorityContractError, match="FINAL_ADJUDICATED"):
        await _load_verified_label_snapshot(
            cast(Any, SimpleNamespace()),
            cast(Any, SimpleNamespace(visibility_mode="FINAL_ADJUDICATED")),
        )


class _TestRowSession:
    async def scalar(self, _query: Any) -> int:
        return 1


@pytest.mark.asyncio
async def test_label_snapshot_with_test_row_is_rejected_by_loader() -> None:
    with pytest.raises(ProspectiveAuthorityContractError, match="TEST_LABEL_ROW"):
        await _load_verified_label_snapshot(
            cast(Any, _TestRowSession()),
            cast(
                Any,
                SimpleNamespace(
                    id=1,
                    visibility_mode="AS_OF_EVALUATION",
                    label_observation_cutoff_at_or_null=UTC_CUTOFF,
                    source_system="production",
                    snapshot_idempotency_key="snapshot-1",
                    created_by_identity="owner",
                ),
            ),
        )


def test_label_snapshot_with_test_row_is_not_pairable() -> None:
    comparable, reason, _, _ = _pair(
        (_forecast_evidence(),), (_label_snapshot(date_value=date(2026, 4, 16)),)
    )
    assert comparable == ()
    assert reason in {"BUSINESS_GRAIN_MISMATCH", "HORIZON_SET_MISMATCH"}


def test_business_grain_mismatch_is_rejected() -> None:
    other = BusinessGrainKey("2025-2026", "farm-b", "subfarm-a", "variety-a")
    label = _label_snapshot()
    row = replace(label.rows[0], grain=other)
    label = replace(label, rows=(row,))
    comparable, reason, _, _ = _pair((_forecast_evidence(),), (label,))
    assert comparable == ()
    assert reason == "BUSINESS_GRAIN_MISMATCH"


def test_horizon_set_mismatch_is_rejected() -> None:
    label = _label_snapshot(date_value=date(2026, 5, 1))
    comparable, reason, _, _ = _pair((_forecast_evidence(),), (label,))
    assert len(comparable) == 1
    assert reason in {"BUSINESS_GRAIN_MISMATCH", "HORIZON_SET_MISMATCH"}


def test_missing_one_of_the_three_horizons_is_not_complete() -> None:
    comparable, reason, expected, complete = _pair((_forecast_evidence(),), (_label_snapshot(),))
    assert expected == 3
    assert len(comparable) == 1
    assert complete == 0
    assert reason == "HORIZON_SET_MISMATCH"


def test_sparse_daily_curve_is_rejected() -> None:
    with pytest.raises(ProspectiveAuthorityContractError, match="INCOMPLETE"):
        require_complete_daily_curve(UTC_CUTOFF, (UTC_CUTOFF.date() + timedelta(days=1),))


def test_canonical_horizon_dates_are_used() -> None:
    assert target_dates_for_cutoff(UTC_CUTOFF) == (
        date(2026, 4, 24),
        date(2026, 5, 1),
        date(2026, 5, 8),
    )


def test_duplicate_label_snapshots_are_ambiguous() -> None:
    first = _label_snapshot()
    second = ProspectiveLabelSnapshot(
        snapshot_identity="snapshot-2",
        snapshot_request_identity_hash=HASH_A,
        snapshot_instance_identity_hash=HASH_B,
        label_snapshot_hash=HASH_C,
        exclusion_manifest_hash=HASH_A,
        label_row_set_hash=HASH_B,
        rows=(replace(first.rows[0], snapshot_identity="snapshot-2"),),
    )
    comparable, reason, _, _ = _pair((_forecast_evidence(),), (first, second))
    assert comparable == ()
    assert reason == "AMBIGUOUS_LABEL_SNAPSHOT"


def test_insufficient_coverage_is_not_ready() -> None:
    comparable, _, expected, complete = _pair((_forecast_evidence(),), ())
    assert comparable == ()
    assert expected == 3
    assert complete == 0


def test_six_required_breakdown_axes_are_frozen() -> None:
    from backend.app.s4_prospective_authority import REQUIRED_BREAKDOWN_AXES

    assert len(REQUIRED_BREAKDOWN_AXES) == 6
    assert set(REQUIRED_BREAKDOWN_AXES) == {
        "forecast_horizon_days",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "season_business_key",
        "model_identity",
    }


def test_proposed_identity_hashes_are_order_stable() -> None:
    forecast = _forecast_evidence()
    labels = _label_snapshot()
    row = ProspectiveComparableRow(
        forecast_identity=forecast.forecast_identity,
        forecast_authority_hash=forecast.authority_hash,
        label_snapshot_identity=labels.snapshot_identity,
        label_snapshot_hash=labels.label_snapshot_hash,
        label_row_hash=labels.rows[0].row_hash,
        grain=GRAIN,
        forecast_horizon_days=7,
        target_date=date(2026, 4, 24),
        model_identity=forecast.model_identity,
    )
    first = build_proposed_identity_hashes((forecast,), (labels,), (row,))
    second = build_proposed_identity_hashes((forecast,), (labels,), (row,))
    assert first == second
    assert all(
        value is not None and len(value) == 64
        for value in (
            first.forecast_authority_set_hash,
            first.actual_label_set_hash,
            first.business_grain_set_hash,
            first.horizon_set_hash,
            first.common_comparable_set_hash,
        )
    )


def test_source_mutation_changes_proposed_identity() -> None:
    forecast = _forecast_evidence()
    labels = _label_snapshot()
    row = ProspectiveComparableRow(
        forecast_identity=forecast.forecast_identity,
        forecast_authority_hash=forecast.authority_hash,
        label_snapshot_identity=labels.snapshot_identity,
        label_snapshot_hash=labels.label_snapshot_hash,
        label_row_hash=labels.rows[0].row_hash,
        grain=GRAIN,
        forecast_horizon_days=7,
        target_date=date(2026, 4, 24),
        model_identity=forecast.model_identity,
    )
    changed = _label_snapshot(quantity="11.000000")
    changed_row = replace(row, label_row_hash="d" * 64)
    assert build_proposed_identity_hashes((forecast,), (labels,), (row,)) != (
        build_proposed_identity_hashes((forecast,), (changed,), (changed_row,))
    )


def test_test_marker_detection_is_recursive() -> None:
    assert _contains_test_marker({"nested": ["S2-FIXTURE"]})
    assert not _contains_test_marker({"scope": "PRODUCTION"})


class _EmptyReadOnlySession:
    def __init__(self) -> None:
        self.write_count = 0

    async def scalars(self, _query: Any) -> list[Any]:
        return []


class _CaptureThenEmptySession:
    def __init__(self, capture: Any) -> None:
        self.capture = capture
        self.calls = 0

    async def scalars(self, _query: Any) -> list[Any]:
        self.calls += 1
        return [self.capture] if self.calls == 1 else []


@pytest.mark.asyncio
async def test_post_test_forecast_without_label_snapshot_is_not_ready() -> None:
    capture, authority = _forecast_pair()
    session = _CaptureThenEmptySession(capture)

    async def loader(_session: Any, **_: Any) -> PersistedForecastAuthority:
        return authority

    result = await scan_prospective_validation_authority(
        session,  # type: ignore[arg-type]
        forecast_loader=loader,
    )
    assert result.status == "NOT_READY"
    assert result.blocker == "NO_EXISTING_LABEL_SNAPSHOT"
    assert result.prospective_forecast_capture_count == 1
    assert result.post_test_forecast_capture_count == 1
    assert result.pit_readable_forecast_count == 1


@pytest.mark.asyncio
async def test_scan_missing_authority_does_not_write() -> None:
    session = _EmptyReadOnlySession()
    result = await scan_prospective_validation_authority(session)  # type: ignore[arg-type]
    assert result.status == "NO_PROSPECTIVE_AUTHORITY"
    assert result.writes_performed == 0
    assert result.evaluation_ledger_events_created == 0
    assert session.write_count == 0


@pytest.mark.asyncio
async def test_scan_creates_no_s4_evaluation_ledger_event() -> None:
    session = _EmptyReadOnlySession()
    result = await scan_prospective_validation_authority(session)  # type: ignore[arg-type]
    assert result.evaluation_ledger_events_created == 0


def test_proposed_hashes_do_not_use_placeholder_preimages() -> None:
    hashes = build_proposed_identity_hashes((_forecast_evidence(),), (_label_snapshot(),), ())
    assert hashes.forecast_authority_set_hash not in {
        None,
        "sha256(label)",
        "sha256(validation)",
        "sha256(prospective)",
    }
