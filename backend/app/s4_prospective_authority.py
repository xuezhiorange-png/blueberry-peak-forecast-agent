"""Read-only feasibility checks for a prospective S4 validation cohort.

This module does not create forecasts, label snapshots, candidate runs, or
ledger events.  It only reads the already-owned production forecast-authority
retention envelope and immutable I7 ``AS_OF_EVALUATION`` label snapshots.
Historical S1 VALIDATION and TEST are deliberately outside the prospective
cohort boundary.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_labels.hashes import (
    compute_exclusion_manifest_hash,
    compute_label_row_set_hash,
    compute_label_snapshot_hash,
    compute_snapshot_instance_identity_hash,
    compute_snapshot_request_identity_hash,
    compute_winner_manifest_hash,
)
from backend.app.actual_harvest_labels.models import (
    ActualHarvestLabelSnapshotLabelModel,
    ActualHarvestLabelSnapshotModel,
)
from backend.app.actual_harvest_labels.persistence import (
    exclusion_row_hash_for,
    exclusion_row_to_value_object,
    label_row_hash_for,
    label_row_to_value_object,
    load_exclusion_rows_for_snapshot,
    load_label_rows_for_snapshot,
    load_winners_for_snapshot,
    winner_row_hash_for,
    winner_to_value_object,
)
from backend.app.forecast_authority.retention import (
    ForecastAuthorityError,
    ForecastAuthorityPostCutoffError,
    PersistedForecastAuthority,
    load_pit_visible_forecast_authority,
)
from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.models.forecast_authority import (
    FORECAST_AUTHORITY_SCOPE_PRODUCTION,
    FORECAST_AUTHORITY_STATUS_CAPTURED,
    ForecastAuthorityCaptureModel,
)
from backend.app.s3_daily_rowset.window import (
    expected_forecast_target_date,
    horizon_window_dates,
)

TEST_END_DATE = date(2026, 4, 16)
MINIMUM_POST_TEST_TARGET_DATE = date(2026, 4, 17)
TEST_START_DATE = date(2026, 3, 10)
REQUESTED_HORIZONS_DAYS: tuple[int, ...] = (7, 14, 21)
MINIMUM_COVERAGE_THRESHOLD = Decimal("0.900000")
VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_THRESHOLD = Decimal("1.000000")
MISSING_DATA_PROPORTION_THRESHOLD = Decimal("0.000000")
MIN_COMPARABLE_ROWS_FOR_REPORTING = 10
REQUIRED_BREAKDOWN_AXES: tuple[str, ...] = (
    "forecast_horizon_days",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "season_business_key",
    "model_identity",
)

ProspectiveScanStatus = Literal["READY", "NOT_READY", "BLOCKED", "NO_PROSPECTIVE_AUTHORITY"]


class ProspectiveAuthorityContractError(ValueError):
    """Sanitized rejection of a prospective authority candidate."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True, order=True)
class BusinessGrainKey:
    """The exact canonical business grain used for prospective pairing."""

    season_business_key: str
    farm_business_key: str
    subfarm_business_key: str
    variety_business_key: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (
            self.season_business_key,
            self.farm_business_key,
            self.subfarm_business_key,
            self.variety_business_key,
        )

    def payload(self) -> dict[str, str]:
        return {
            "season_business_key": self.season_business_key,
            "farm_business_key": self.farm_business_key,
            "subfarm_business_key": self.subfarm_business_key,
            "variety_business_key": self.variety_business_key,
        }


@dataclass(frozen=True, slots=True)
class ProspectiveLabelRow:
    snapshot_identity: str
    snapshot_request_identity_hash: str
    snapshot_instance_identity_hash: str
    label_snapshot_hash: str
    exclusion_manifest_hash: str
    label_row_set_hash: str
    row_hash: str
    grain: BusinessGrainKey
    harvest_business_date: date
    actual_harvest_quantity_kg: Decimal

    def payload(self) -> dict[str, Any]:
        return {
            "snapshot_identity": self.snapshot_identity,
            "snapshot_request_identity_hash": self.snapshot_request_identity_hash,
            "snapshot_instance_identity_hash": self.snapshot_instance_identity_hash,
            "label_snapshot_hash": self.label_snapshot_hash,
            "exclusion_manifest_hash": self.exclusion_manifest_hash,
            "label_row_set_hash": self.label_row_set_hash,
            "label_row_hash": self.row_hash,
            "business_grain": self.grain.payload(),
            "harvest_business_date": self.harvest_business_date,
            "actual_harvest_quantity_kg": self.actual_harvest_quantity_kg,
        }


@dataclass(frozen=True, slots=True)
class ProspectiveLabelSnapshot:
    """Verified immutable I7 snapshot projection used by the scanner."""

    snapshot_identity: str
    snapshot_request_identity_hash: str
    snapshot_instance_identity_hash: str
    label_snapshot_hash: str
    exclusion_manifest_hash: str
    label_row_set_hash: str
    rows: tuple[ProspectiveLabelRow, ...]


@dataclass(frozen=True, slots=True)
class ProspectiveForecastAuthority:
    """Verified production retention projection, with no forecast values."""

    forecast_identity: str
    authority_hash: str
    forecast_cutoff_at: datetime
    forecast_available_at: datetime
    business_grain_hash: str
    task8_daily_artifact_hash: str
    code_authority_hash: str
    source_lineage_hash: str
    daily_row_count: int
    model_identity: str
    grains: tuple[BusinessGrainKey, ...]
    target_dates: tuple[date, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "forecast_identity": self.forecast_identity,
            "authority_hash": self.authority_hash,
            "forecast_cutoff_at": self.forecast_cutoff_at,
            "forecast_available_at": self.forecast_available_at,
            "business_grain_hash": self.business_grain_hash,
            "task8_daily_artifact_hash": self.task8_daily_artifact_hash,
            "code_authority_hash": self.code_authority_hash,
            "source_lineage_hash": self.source_lineage_hash,
            "daily_row_count": self.daily_row_count,
            "model_identity": self.model_identity,
            "grains": [grain.payload() for grain in self.grains],
            "target_dates": self.target_dates,
        }


@dataclass(frozen=True, slots=True)
class ProspectiveComparableRow:
    forecast_identity: str
    forecast_authority_hash: str
    label_snapshot_identity: str
    label_snapshot_hash: str
    label_row_hash: str
    grain: BusinessGrainKey
    forecast_horizon_days: int
    target_date: date
    model_identity: str

    def payload(self) -> dict[str, Any]:
        return {
            "forecast_identity": self.forecast_identity,
            "forecast_authority_hash": self.forecast_authority_hash,
            "label_snapshot_identity": self.label_snapshot_identity,
            "label_snapshot_hash": self.label_snapshot_hash,
            "label_row_hash": self.label_row_hash,
            "business_grain": self.grain.payload(),
            "forecast_horizon_days": self.forecast_horizon_days,
            "target_date": self.target_date,
            "model_identity": self.model_identity,
        }


@dataclass(frozen=True, slots=True)
class ProposedIdentityHashes:
    forecast_authority_set_hash: str | None
    actual_label_set_hash: str | None
    business_grain_set_hash: str | None
    horizon_set_hash: str | None
    common_comparable_set_hash: str | None


@dataclass(frozen=True, slots=True)
class ProspectiveAuthorityScanResult:
    status: ProspectiveScanStatus
    blocker: str | None
    reason_code: str | None
    prospective_forecast_capture_count: int
    post_test_forecast_capture_count: int
    pit_readable_forecast_count: int
    eligible_label_snapshot_count: int
    prospective_common_comparable_row_count: int
    prospective_coverage_ratio: Decimal | None
    valid_included_canonical_group_coverage: Decimal | None
    missing_data_proportion: Decimal | None
    earliest_eligible_forecast_cutoff: datetime | None
    latest_eligible_forecast_cutoff: datetime | None
    earliest_eligible_target_date: date | None
    latest_eligible_target_date: date | None
    proposed_hashes: ProposedIdentityHashes
    test_access: bool = False
    writes_performed: int = 0
    evaluation_ledger_events_created: int = 0

    @property
    def prospective_validation_extension_feasible(self) -> bool:
        return self.status == "READY"

    def payload(self) -> dict[str, Any]:
        return {
            "LIVE_PROSPECTIVE_SCAN_STATUS": self.status,
            "LIVE_PROSPECTIVE_SCAN_BLOCK_REASON": self.blocker,
            "LIVE_PROSPECTIVE_SCAN_REASON_CODE": self.reason_code,
            "PROSPECTIVE_FORECAST_CAPTURE_COUNT": self.prospective_forecast_capture_count,
            "POST_TEST_FORECAST_CAPTURE_COUNT": self.post_test_forecast_capture_count,
            "PIT_READABLE_FORECAST_COUNT": self.pit_readable_forecast_count,
            "ELIGIBLE_LABEL_SNAPSHOT_COUNT": self.eligible_label_snapshot_count,
            "PROSPECTIVE_COMMON_COMPARABLE_ROW_COUNT": (
                self.prospective_common_comparable_row_count
            ),
            "PROSPECTIVE_COVERAGE_RATIO": self.prospective_coverage_ratio,
            "VALID_INCLUDED_CANONICAL_GROUP_COVERAGE": (
                self.valid_included_canonical_group_coverage
            ),
            "MISSING_DATA_PROPORTION": self.missing_data_proportion,
            "EARLIEST_ELIGIBLE_FORECAST_CUTOFF": self.earliest_eligible_forecast_cutoff,
            "LATEST_ELIGIBLE_FORECAST_CUTOFF": self.latest_eligible_forecast_cutoff,
            "EARLIEST_ELIGIBLE_TARGET_DATE": self.earliest_eligible_target_date,
            "LATEST_ELIGIBLE_TARGET_DATE": self.latest_eligible_target_date,
            "PROPOSED_FORECAST_AUTHORITY_SET_HASH": (
                self.proposed_hashes.forecast_authority_set_hash
            ),
            "PROPOSED_ACTUAL_LABEL_SET_HASH": self.proposed_hashes.actual_label_set_hash,
            "PROPOSED_BUSINESS_GRAIN_SET_HASH": self.proposed_hashes.business_grain_set_hash,
            "PROPOSED_HORIZON_SET_HASH": self.proposed_hashes.horizon_set_hash,
            "PROPOSED_COMMON_COMPARABLE_SET_HASH": (
                self.proposed_hashes.common_comparable_set_hash
            ),
            "PROSPECTIVE_VALIDATION_EXTENSION_FEASIBLE": (
                self.prospective_validation_extension_feasible
            ),
            "TEST_ACCESS": self.test_access,
            "WRITES_PERFORMED": self.writes_performed,
            "EVALUATION_LEDGER_EVENTS_CREATED": self.evaluation_ledger_events_created,
        }


LabelLoader = Callable[
    [AsyncSession, ActualHarvestLabelSnapshotModel], Awaitable[ProspectiveLabelSnapshot]
]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _contains_test_marker(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(
            marker in lowered
            for marker in ("test_fixture", "test-fixture", "s2-fixture", "synthetic", "2026-demo")
        )
    if isinstance(value, Mapping):
        return any(
            _contains_test_marker(key) or _contains_test_marker(item) for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_test_marker(item) for item in value)
    return False


def is_post_test_target_date(target_date: date) -> bool:
    """Return whether a target date is strictly outside the sealed TEST interval."""

    return target_date >= MINIMUM_POST_TEST_TARGET_DATE


def target_dates_for_cutoff(
    forecast_cutoff_at: datetime,
    *,
    horizons_days: Iterable[int] = REQUESTED_HORIZONS_DAYS,
) -> tuple[date, ...]:
    """Use the repository-owned cutoff-to-target semantics."""

    horizons = tuple(horizons_days)
    if tuple(sorted(horizons)) != REQUESTED_HORIZONS_DAYS:
        raise ProspectiveAuthorityContractError("HORIZON_SET_MISMATCH")
    return tuple(expected_forecast_target_date(forecast_cutoff_at, horizon) for horizon in horizons)


def require_complete_daily_curve(
    forecast_cutoff_at: datetime,
    daily_dates: Iterable[date],
    *,
    horizons_days: Iterable[int] = REQUESTED_HORIZONS_DAYS,
) -> None:
    """Require the complete daily curve through the largest requested horizon."""

    expected = set(horizon_window_dates(forecast_cutoff_at, max(REQUESTED_HORIZONS_DAYS)))
    actual = set(daily_dates)
    if not expected.issubset(actual):
        raise ProspectiveAuthorityContractError("INCOMPLETE_DAILY_FORECAST_CURVE")
    if tuple(sorted(horizons_days)) != REQUESTED_HORIZONS_DAYS:
        raise ProspectiveAuthorityContractError("HORIZON_SET_MISMATCH")


def _grain_from_mapping(value: Mapping[str, Any]) -> BusinessGrainKey:
    keys = (
        "season_business_key",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
    )
    if any(not isinstance(value.get(key), str) or not value[key] for key in keys):
        raise ProspectiveAuthorityContractError("BUSINESS_GRAIN_MISMATCH")
    return BusinessGrainKey(*(cast(str, value[key]) for key in keys))


def _grains_from_snapshot(snapshot: Mapping[str, Any]) -> tuple[BusinessGrainKey, ...]:
    if (
        _contains_test_marker(snapshot)
        or snapshot.get("grain") != "SEASON_X_FARM_X_SUBFARM_X_VARIETY"
    ):
        raise ProspectiveAuthorityContractError("TEST_OR_INVALID_FORECAST_AUTHORITY")
    raw_grains = snapshot.get("grains")
    if not isinstance(raw_grains, list) or not raw_grains:
        raise ProspectiveAuthorityContractError("BUSINESS_GRAIN_MISMATCH")
    grains = tuple(_grain_from_mapping(cast(Mapping[str, Any], item)) for item in raw_grains)
    if len(set(grains)) != len(grains):
        raise ProspectiveAuthorityContractError("DUPLICATE_BUSINESS_GRAIN")
    return tuple(sorted(grains))


def _model_identity_from_authority(authority: PersistedForecastAuthority) -> str:
    governance = authority.governance_snapshot
    value = governance.get("model_identity")
    if not isinstance(value, str) or not value or _contains_test_marker(value):
        raise ProspectiveAuthorityContractError("MISSING_MODEL_IDENTITY")
    return value


def breakdown_axis_values(row: ProspectiveComparableRow) -> dict[str, str | int]:
    """Return the exact six S4-B breakdown axes for one comparable row."""

    return {
        "forecast_horizon_days": row.forecast_horizon_days,
        "farm_business_key": row.grain.farm_business_key,
        "subfarm_business_key": row.grain.subfarm_business_key,
        "variety_business_key": row.grain.variety_business_key,
        "season_business_key": row.grain.season_business_key,
        "model_identity": row.model_identity,
    }


def has_required_breakdown_axes(row: ProspectiveComparableRow) -> bool:
    axes = breakdown_axis_values(row)
    return set(axes) == set(REQUIRED_BREAKDOWN_AXES) and all(value != "" for value in axes.values())


def _forecast_evidence_from_capture(
    capture: ForecastAuthorityCaptureModel,
    authority: PersistedForecastAuthority,
) -> ProspectiveForecastAuthority:
    if capture.authority_scope != FORECAST_AUTHORITY_SCOPE_PRODUCTION:
        raise ProspectiveAuthorityContractError("TEST_OR_INVALID_FORECAST_AUTHORITY")
    if capture.status != FORECAST_AUTHORITY_STATUS_CAPTURED:
        raise ProspectiveAuthorityContractError("TEST_OR_INVALID_FORECAST_AUTHORITY")
    if _contains_test_marker(capture.canonical_payload):
        raise ProspectiveAuthorityContractError("TEST_OR_SYNTHETIC_FORECAST_AUTHORITY")
    for value in (
        capture.forecast_identity,
        capture.authority_hash,
        capture.business_grain_hash,
        capture.task8_daily_artifact_hash,
        capture.code_authority_hash,
        capture.source_lineage_hash,
    ):
        if not isinstance(value, str) or len(value) != 64:
            raise ProspectiveAuthorityContractError("FORECAST_AUTHORITY_HASH_MISMATCH")
    if capture.daily_row_count <= 0 or len(authority.daily_predictions) != capture.daily_row_count:
        raise ProspectiveAuthorityContractError("INCOMPLETE_DAILY_FORECAST_CURVE")
    if (
        authority.forecast_identity != capture.forecast_identity
        or authority.authority_hash != capture.authority_hash
    ):
        raise ProspectiveAuthorityContractError("FORECAST_AUTHORITY_HASH_MISMATCH")
    grains = _grains_from_snapshot(authority.business_grain_snapshot)
    target_dates = target_dates_for_cutoff(authority.forecast_cutoff_at)
    if not all(is_post_test_target_date(item) for item in target_dates):
        raise ProspectiveAuthorityContractError("NO_POST_TEST_TARGET_ROWS")
    require_complete_daily_curve(
        authority.forecast_cutoff_at,
        (row.prediction_date for row in authority.daily_predictions),
    )
    return ProspectiveForecastAuthority(
        forecast_identity=capture.forecast_identity,
        authority_hash=capture.authority_hash,
        forecast_cutoff_at=_utc(capture.forecast_cutoff_at),
        forecast_available_at=_utc(capture.forecast_available_at),
        business_grain_hash=capture.business_grain_hash,
        task8_daily_artifact_hash=capture.task8_daily_artifact_hash,
        code_authority_hash=capture.code_authority_hash,
        source_lineage_hash=capture.source_lineage_hash,
        daily_row_count=capture.daily_row_count,
        model_identity=_model_identity_from_authority(authority),
        grains=grains,
        target_dates=target_dates,
    )


def _required_readback_cutoff(capture: ForecastAuthorityCaptureModel) -> datetime:
    return max(
        _utc(capture.forecast_cutoff_at),
        _utc(capture.forecast_created_at),
        _utc(capture.forecast_available_at),
        _utc(capture.code_authority_available_at),
    )


async def _read_capture(
    session: AsyncSession,
    capture: ForecastAuthorityCaptureModel,
    *,
    loader: Callable[..., Awaitable[PersistedForecastAuthority]] | None = None,
) -> PersistedForecastAuthority:
    read_loader = loader or load_pit_visible_forecast_authority
    try:
        return await read_loader(
            session,
            forecast_identity=capture.forecast_identity,
            cutoff_at=_required_readback_cutoff(capture),
        )
    except ForecastAuthorityPostCutoffError:
        raise ProspectiveAuthorityContractError("PIT_POST_CUTOFF_AUTHORITY") from None
    except ForecastAuthorityError as exc:
        raise ProspectiveAuthorityContractError(exc.reason_code) from None


async def _load_verified_label_snapshot(
    session: AsyncSession,
    snapshot: ActualHarvestLabelSnapshotModel,
) -> ProspectiveLabelSnapshot:
    """Round-trip the complete I7 identity using existing production helpers."""

    if snapshot.visibility_mode != "AS_OF_EVALUATION":
        raise ProspectiveAuthorityContractError("FINAL_ADJUDICATED_NOT_ALLOWED")
    if snapshot.label_observation_cutoff_at_or_null is None:
        raise ProspectiveAuthorityContractError("INVALID_AS_OF_LABEL_SNAPSHOT")
    if _contains_test_marker(
        {
            "source_system": snapshot.source_system,
            "snapshot_idempotency_key": snapshot.snapshot_idempotency_key,
            "created_by_identity": snapshot.created_by_identity,
        }
    ):
        raise ProspectiveAuthorityContractError("TEST_OR_SYNTHETIC_LABEL_AUTHORITY")

    test_row_count = await session.scalar(
        select(func.count())
        .select_from(ActualHarvestLabelSnapshotLabelModel)
        .where(
            ActualHarvestLabelSnapshotLabelModel.snapshot_id == snapshot.id,
            ActualHarvestLabelSnapshotLabelModel.harvest_business_date >= TEST_START_DATE,
            ActualHarvestLabelSnapshotLabelModel.harvest_business_date <= TEST_END_DATE,
        )
    )
    if int(test_row_count or 0) != 0:
        raise ProspectiveAuthorityContractError("TEST_LABEL_ROW_REJECTED")

    label_rows = await load_label_rows_for_snapshot(session, snapshot.id)
    winners = await load_winners_for_snapshot(session, snapshot.id)
    exclusions = await load_exclusion_rows_for_snapshot(session, snapshot.id)
    winner_values = tuple(winner_to_value_object(item) for item in winners)
    label_values = tuple(label_row_to_value_object(item) for item in label_rows)
    exclusion_values = tuple(exclusion_row_to_value_object(item) for item in exclusions)
    if any(_contains_test_marker(item.model_dump(mode="python")) for item in label_values):
        raise ProspectiveAuthorityContractError("TEST_LABEL_ROW_REJECTED")
    if any(
        winner_row_hash_for(item.model_dump(mode="python")) != item.winner_row_hash
        for item in winner_values
    ):
        raise ProspectiveAuthorityContractError("LABEL_WINNER_HASH_MISMATCH")
    if any(
        label_row_hash_for(item.model_dump(mode="python")) != item.label_row_hash
        for item in label_values
    ):
        raise ProspectiveAuthorityContractError("LABEL_ROW_HASH_MISMATCH")
    if any(
        exclusion_row_hash_for(item.model_dump(mode="python")) != item.exclusion_row_hash
        for item in exclusion_values
    ):
        raise ProspectiveAuthorityContractError("LABEL_EXCLUSION_HASH_MISMATCH")
    try:
        raw_scopes = (
            json.loads(snapshot.season_business_keys),
            json.loads(snapshot.farm_business_keys_or_empty_for_all),
            json.loads(snapshot.variety_business_keys_or_empty_for_all),
        )
    except (TypeError, json.JSONDecodeError):
        raise ProspectiveAuthorityContractError("LABEL_SCOPE_MALFORMED") from None
    if any(
        not isinstance(scope, list) or any(not isinstance(item, str) for item in scope)
        for scope in raw_scopes
    ):
        raise ProspectiveAuthorityContractError("LABEL_SCOPE_MALFORMED")
    season_keys, farm_keys, variety_keys = (tuple(scope) for scope in raw_scopes)
    request_hash = compute_snapshot_request_identity_hash(
        snapshot_idempotency_key=snapshot.snapshot_idempotency_key,
        source_system=snapshot.source_system,
        visibility_mode=snapshot.visibility_mode,
        label_observation_cutoff_at_or_null=snapshot.label_observation_cutoff_at_or_null,
        harvest_date_start=snapshot.harvest_date_start,
        harvest_date_end=snapshot.harvest_date_end,
        season_business_keys=season_keys,
        farm_business_keys_or_empty_for_all=farm_keys,
        variety_business_keys_or_empty_for_all=variety_keys,
        snapshot_policy_version=snapshot.snapshot_policy_version,
        winner_policy_version=snapshot.winner_policy_version,
        aggregation_policy_version=snapshot.aggregation_policy_version,
    )
    instance_hash = compute_snapshot_instance_identity_hash(
        request_identity_hash=request_hash,
        source_commit_manifest_set_hash=snapshot.source_commit_manifest_set_hash,
    )
    winner_hash = compute_winner_manifest_hash(
        item.model_dump(mode="python") for item in winner_values
    )
    label_hash = compute_label_row_set_hash(item.model_dump(mode="python") for item in label_values)
    exclusion_hash = compute_exclusion_manifest_hash(
        item.model_dump(mode="python") for item in exclusion_values
    )
    snapshot_hash = compute_label_snapshot_hash(
        instance_identity_hash=instance_hash,
        winner_manifest_hash=winner_hash,
        label_row_set_hash=label_hash,
        exclusion_manifest_hash=exclusion_hash,
        winner_count=len(winner_values),
        label_row_count=len(label_values),
        exclusion_row_count=len(exclusion_values),
        snapshot_policy_version=snapshot.snapshot_policy_version,
        winner_policy_version=snapshot.winner_policy_version,
        aggregation_policy_version=snapshot.aggregation_policy_version,
    )
    if (
        snapshot.snapshot_request_identity_hash != request_hash
        or snapshot.snapshot_instance_identity_hash != instance_hash
        or snapshot.winner_manifest_hash != winner_hash
        or snapshot.label_row_set_hash != label_hash
        or snapshot.exclusion_manifest_hash != exclusion_hash
        or snapshot.label_snapshot_hash != snapshot_hash
        or snapshot.winner_count != len(winner_values)
        or snapshot.label_row_count != len(label_values)
        or snapshot.exclusion_row_count != len(exclusion_values)
    ):
        raise ProspectiveAuthorityContractError("LABEL_SNAPSHOT_HASH_MISMATCH")
    if _utc(snapshot.snapshot_executed_at) > _utc(snapshot.label_observation_cutoff_at_or_null):
        raise ProspectiveAuthorityContractError("LABEL_SNAPSHOT_POST_CUTOFF")
    rows: list[ProspectiveLabelRow] = []
    for item in label_values:
        if not is_post_test_target_date(item.harvest_business_date):
            continue
        if (
            not isinstance(item.exact_decimal_quantity_sum_kg, Decimal)
            or not item.exact_decimal_quantity_sum_kg.is_finite()
            or item.exact_decimal_quantity_sum_kg < 0
        ):
            raise ProspectiveAuthorityContractError("INVALID_ACTUAL_LABEL_DECIMAL")
        rows.append(
            ProspectiveLabelRow(
                snapshot_identity=snapshot.snapshot_idempotency_key,
                snapshot_request_identity_hash=request_hash,
                snapshot_instance_identity_hash=instance_hash,
                label_snapshot_hash=snapshot_hash,
                exclusion_manifest_hash=exclusion_hash,
                label_row_set_hash=label_hash,
                row_hash=item.label_row_hash,
                grain=BusinessGrainKey(
                    item.season_business_key,
                    item.farm_business_key,
                    item.subfarm_business_key,
                    item.variety_business_key,
                ),
                harvest_business_date=item.harvest_business_date,
                actual_harvest_quantity_kg=item.exact_decimal_quantity_sum_kg,
            )
        )
    if not rows:
        raise ProspectiveAuthorityContractError("NO_POST_TEST_LABEL_ROWS")
    return ProspectiveLabelSnapshot(
        snapshot_identity=snapshot.snapshot_idempotency_key,
        snapshot_request_identity_hash=request_hash,
        snapshot_instance_identity_hash=instance_hash,
        label_snapshot_hash=snapshot_hash,
        exclusion_manifest_hash=exclusion_hash,
        label_row_set_hash=label_hash,
        rows=tuple(
            sorted(rows, key=lambda item: (item.grain.as_tuple(), item.harvest_business_date))
        ),
    )


def build_proposed_identity_hashes(
    forecast_authorities: Iterable[ProspectiveForecastAuthority],
    label_snapshots: Iterable[ProspectiveLabelSnapshot],
    comparable_rows: Iterable[ProspectiveComparableRow],
) -> ProposedIdentityHashes:
    """Hash only actual durable projections; empty sets remain unissued."""

    forecasts = tuple(sorted(forecast_authorities, key=lambda item: item.forecast_identity))
    labels = tuple(sorted(label_snapshots, key=lambda item: item.snapshot_identity))
    comparable = tuple(
        sorted(
            comparable_rows,
            key=lambda item: (
                item.grain.as_tuple(),
                item.target_date,
                item.forecast_horizon_days,
                item.forecast_identity,
            ),
        )
    )
    actual_rows = tuple(
        sorted(
            (row for snapshot in labels for row in snapshot.rows),
            key=lambda item: (item.grain.as_tuple(), item.harvest_business_date, item.row_hash),
        )
    )
    forecast_hash = (
        _digest(
            {
                "policy": "prospective-forecast-authority-set-v1",
                "members": [item.payload() for item in forecasts],
            }
        )
        if forecasts
        else None
    )
    actual_hash = (
        _digest(
            {
                "policy": "prospective-actual-label-set-v1",
                "members": [item.payload() for item in actual_rows],
            }
        )
        if actual_rows
        else None
    )
    business_grains = sorted({row.grain for row in comparable})
    business_hash = (
        _digest(
            {
                "policy": "prospective-business-grain-set-v1",
                "members": [item.payload() for item in business_grains],
            }
        )
        if business_grains
        else None
    )
    horizon_hash = (
        _digest(
            {
                "policy": "prospective-horizon-set-v1",
                "members": [
                    {
                        "forecast_identity": row.forecast_identity,
                        "grain": row.grain.payload(),
                        "forecast_horizon_days": row.forecast_horizon_days,
                        "target_date": row.target_date,
                    }
                    for row in comparable
                ],
            }
        )
        if comparable
        else None
    )
    common_hash = (
        _digest(
            {
                "policy": "prospective-common-comparable-set-v1",
                "members": [item.payload() for item in comparable],
            }
        )
        if comparable
        else None
    )
    return ProposedIdentityHashes(
        forecast_hash, actual_hash, business_hash, horizon_hash, common_hash
    )


def _pair(
    forecasts: Sequence[ProspectiveForecastAuthority],
    labels: Sequence[ProspectiveLabelSnapshot],
) -> tuple[tuple[ProspectiveComparableRow, ...], str | None, int, int]:
    label_maps = [
        {(row.grain, row.harvest_business_date): row for row in snapshot.rows}
        for snapshot in labels
    ]
    comparables: list[ProspectiveComparableRow] = []
    expected_count = 0
    complete_group_count = 0
    expected_group_count = 0
    reason: str | None = None
    seen_keys: set[tuple[BusinessGrainKey, date, int]] = set()
    for forecast in forecasts:
        expected_group_count += len(forecast.grains)
        for grain in forecast.grains:
            expected_count += len(REQUESTED_HORIZONS_DAYS)
            group_rows: list[ProspectiveComparableRow] = []
            group_ok = True
            for horizon in REQUESTED_HORIZONS_DAYS:
                target_date = expected_forecast_target_date(forecast.forecast_cutoff_at, horizon)
                matches = [mapping.get((grain, target_date)) for mapping in label_maps]
                matches = [item for item in matches if item is not None]
                if len(matches) == 0:
                    group_ok = False
                    has_same_grain = any(
                        any(key[0] == grain for key in mapping) for mapping in label_maps
                    )
                    has_same_date = any(
                        any(key[1] == target_date for key in mapping) for mapping in label_maps
                    )
                    reason = reason or (
                        "HORIZON_SET_MISMATCH"
                        if has_same_grain
                        else "BUSINESS_GRAIN_MISMATCH"
                        if has_same_date
                        else "BUSINESS_GRAIN_MISMATCH"
                    )
                    continue
                if len(matches) > 1:
                    group_ok = False
                    reason = reason or "AMBIGUOUS_LABEL_SNAPSHOT"
                    continue
                label = matches[0]
                if label is None:
                    group_ok = False
                    reason = reason or "BUSINESS_GRAIN_MISMATCH"
                    continue
                key = (grain, target_date, horizon)
                if key in seen_keys:
                    group_ok = False
                    reason = reason or "BUSINESS_GRAIN_MISMATCH"
                    continue
                comparable = ProspectiveComparableRow(
                    forecast_identity=forecast.forecast_identity,
                    forecast_authority_hash=forecast.authority_hash,
                    label_snapshot_identity=label.snapshot_identity,
                    label_snapshot_hash=label.label_snapshot_hash,
                    label_row_hash=label.row_hash,
                    grain=grain,
                    forecast_horizon_days=horizon,
                    target_date=target_date,
                    model_identity=forecast.model_identity,
                )
                if not has_required_breakdown_axes(comparable):
                    group_ok = False
                    reason = reason or "MISSING_REQUIRED_BREAKDOWN_AXIS"
                    continue
                seen_keys.add(key)
                group_rows.append(comparable)
            if group_ok:
                complete_group_count += 1
            comparables.extend(group_rows)
    return (
        tuple(comparables),
        reason,
        expected_count,
        complete_group_count if expected_group_count else 0,
    )


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


async def scan_prospective_validation_authority(
    session: AsyncSession,
    *,
    forecast_loader: Callable[..., Awaitable[PersistedForecastAuthority]] | None = None,
    label_loader: LabelLoader | None = None,
) -> ProspectiveAuthorityScanResult:
    """Perform one read-only feasibility scan against the authority store."""

    load_forecast = forecast_loader or load_pit_visible_forecast_authority
    load_label = label_loader or _load_verified_label_snapshot
    captures = list(
        await session.scalars(
            select(ForecastAuthorityCaptureModel)
            .where(
                ForecastAuthorityCaptureModel.authority_scope
                == FORECAST_AUTHORITY_SCOPE_PRODUCTION,
                ForecastAuthorityCaptureModel.status == FORECAST_AUTHORITY_STATUS_CAPTURED,
            )
            .order_by(ForecastAuthorityCaptureModel.id.asc())
        )
    )
    forecast_count = len(captures)
    post_test_captures: list[ForecastAuthorityCaptureModel] = []
    for capture in captures:
        try:
            target_dates = target_dates_for_cutoff(capture.forecast_cutoff_at)
        except (ValueError, ProspectiveAuthorityContractError):
            continue
        if all(is_post_test_target_date(target_date) for target_date in target_dates):
            post_test_captures.append(capture)
    post_test_count = len(post_test_captures)
    if post_test_count == 0:
        status: ProspectiveScanStatus = "NO_PROSPECTIVE_AUTHORITY"
        reason = (
            "NO_PRODUCTION_FORECAST_CAPTURE" if forecast_count == 0 else "NO_POST_TEST_TARGET_ROWS"
        )
        return ProspectiveAuthorityScanResult(
            status=status,
            blocker=reason,
            reason_code=reason,
            prospective_forecast_capture_count=forecast_count,
            post_test_forecast_capture_count=0,
            pit_readable_forecast_count=0,
            eligible_label_snapshot_count=0,
            prospective_common_comparable_row_count=0,
            prospective_coverage_ratio=Decimal("0.000000"),
            valid_included_canonical_group_coverage=Decimal("0.000000"),
            missing_data_proportion=Decimal("1.000000"),
            earliest_eligible_forecast_cutoff=None,
            latest_eligible_forecast_cutoff=None,
            earliest_eligible_target_date=None,
            latest_eligible_target_date=None,
            proposed_hashes=ProposedIdentityHashes(None, None, None, None, None),
        )

    forecast_evidence: list[ProspectiveForecastAuthority] = []
    for capture in post_test_captures:
        try:
            authority = await load_forecast(
                session,
                forecast_identity=capture.forecast_identity,
                cutoff_at=_required_readback_cutoff(capture),
            )
            forecast_evidence.append(_forecast_evidence_from_capture(capture, authority))
        except (ForecastAuthorityError, ProspectiveAuthorityContractError, ValueError, TypeError):
            continue
    pit_count = len(forecast_evidence)
    if pit_count == 0:
        return ProspectiveAuthorityScanResult(
            status="BLOCKED",
            blocker="PIT_READBACK_FAILURE",
            reason_code="PIT_READBACK_FAILURE",
            prospective_forecast_capture_count=forecast_count,
            post_test_forecast_capture_count=post_test_count,
            pit_readable_forecast_count=0,
            eligible_label_snapshot_count=0,
            prospective_common_comparable_row_count=0,
            prospective_coverage_ratio=Decimal("0.000000"),
            valid_included_canonical_group_coverage=Decimal("0.000000"),
            missing_data_proportion=Decimal("1.000000"),
            earliest_eligible_forecast_cutoff=None,
            latest_eligible_forecast_cutoff=None,
            earliest_eligible_target_date=None,
            latest_eligible_target_date=None,
            proposed_hashes=ProposedIdentityHashes(None, None, None, None, None),
        )

    snapshots = list(
        await session.scalars(
            select(ActualHarvestLabelSnapshotModel)
            .where(ActualHarvestLabelSnapshotModel.visibility_mode == "AS_OF_EVALUATION")
            .order_by(ActualHarvestLabelSnapshotModel.id.asc())
        )
    )
    label_evidence: list[ProspectiveLabelSnapshot] = []
    label_failure: str | None = None
    for snapshot in snapshots:
        try:
            label_evidence.append(await load_label(session, snapshot))
        except ProspectiveAuthorityContractError as exc:
            label_failure = label_failure or exc.reason_code
    if not label_evidence:
        reason = (
            "NO_EXISTING_LABEL_SNAPSHOT"
            if not snapshots
            else (label_failure or "NO_POST_TEST_LABEL_ROWS")
        )
        hashes = build_proposed_identity_hashes(forecast_evidence, (), ())
        return ProspectiveAuthorityScanResult(
            status="NOT_READY",
            blocker=reason,
            reason_code=reason,
            prospective_forecast_capture_count=forecast_count,
            post_test_forecast_capture_count=post_test_count,
            pit_readable_forecast_count=pit_count,
            eligible_label_snapshot_count=0,
            prospective_common_comparable_row_count=0,
            prospective_coverage_ratio=Decimal("0.000000"),
            valid_included_canonical_group_coverage=Decimal("0.000000"),
            missing_data_proportion=Decimal("1.000000"),
            earliest_eligible_forecast_cutoff=min(
                item.forecast_cutoff_at for item in forecast_evidence
            ),
            latest_eligible_forecast_cutoff=max(
                item.forecast_cutoff_at for item in forecast_evidence
            ),
            earliest_eligible_target_date=min(item.target_dates[0] for item in forecast_evidence),
            latest_eligible_target_date=max(item.target_dates[-1] for item in forecast_evidence),
            proposed_hashes=hashes,
        )

    comparable, pair_reason, expected_count, complete_groups = _pair(
        forecast_evidence, label_evidence
    )
    coverage = _ratio(len(comparable), expected_count)
    total_groups = sum(len(item.grains) for item in forecast_evidence)
    group_coverage = _ratio(complete_groups, total_groups)
    missing = Decimal("1.000000") - coverage
    hashes = build_proposed_identity_hashes(forecast_evidence, label_evidence, comparable)
    if (
        len(comparable) < MIN_COMPARABLE_ROWS_FOR_REPORTING
        or coverage < MINIMUM_COVERAGE_THRESHOLD
        or group_coverage < VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_THRESHOLD
        or missing > MISSING_DATA_PROPORTION_THRESHOLD
    ):
        reason = pair_reason or "INSUFFICIENT_COVERAGE"
        if pair_reason in {
            "BUSINESS_GRAIN_MISMATCH",
            "AMBIGUOUS_LABEL_SNAPSHOT",
            "HORIZON_SET_MISMATCH",
        }:
            reason = pair_reason
        return ProspectiveAuthorityScanResult(
            status="NOT_READY",
            blocker=reason,
            reason_code=reason,
            prospective_forecast_capture_count=forecast_count,
            post_test_forecast_capture_count=post_test_count,
            pit_readable_forecast_count=pit_count,
            eligible_label_snapshot_count=len(label_evidence),
            prospective_common_comparable_row_count=len(comparable),
            prospective_coverage_ratio=coverage,
            valid_included_canonical_group_coverage=group_coverage,
            missing_data_proportion=missing,
            earliest_eligible_forecast_cutoff=min(
                item.forecast_cutoff_at for item in forecast_evidence
            ),
            latest_eligible_forecast_cutoff=max(
                item.forecast_cutoff_at for item in forecast_evidence
            ),
            earliest_eligible_target_date=min(item.target_dates[0] for item in forecast_evidence),
            latest_eligible_target_date=max(item.target_dates[-1] for item in forecast_evidence),
            proposed_hashes=hashes,
        )
    return ProspectiveAuthorityScanResult(
        status="READY",
        blocker=None,
        reason_code=None,
        prospective_forecast_capture_count=forecast_count,
        post_test_forecast_capture_count=post_test_count,
        pit_readable_forecast_count=pit_count,
        eligible_label_snapshot_count=len(label_evidence),
        prospective_common_comparable_row_count=len(comparable),
        prospective_coverage_ratio=coverage,
        valid_included_canonical_group_coverage=group_coverage,
        missing_data_proportion=missing,
        earliest_eligible_forecast_cutoff=min(
            item.forecast_cutoff_at for item in forecast_evidence
        ),
        latest_eligible_forecast_cutoff=max(item.forecast_cutoff_at for item in forecast_evidence),
        earliest_eligible_target_date=min(item.target_dates[0] for item in forecast_evidence),
        latest_eligible_target_date=max(item.target_dates[-1] for item in forecast_evidence),
        proposed_hashes=hashes,
    )


__all__ = [
    "BusinessGrainKey",
    "MINIMUM_COVERAGE_THRESHOLD",
    "MINIMUM_POST_TEST_TARGET_DATE",
    "MIN_COMPARABLE_ROWS_FOR_REPORTING",
    "MISSING_DATA_PROPORTION_THRESHOLD",
    "POST_TEST_TARGET_DATE_REQUIRED",
    "ProspectiveAuthorityContractError",
    "ProspectiveAuthorityScanResult",
    "ProspectiveComparableRow",
    "ProspectiveForecastAuthority",
    "ProspectiveLabelRow",
    "ProspectiveLabelSnapshot",
    "ProposedIdentityHashes",
    "REQUESTED_HORIZONS_DAYS",
    "REQUIRED_BREAKDOWN_AXES",
    "TEST_END_DATE",
    "build_proposed_identity_hashes",
    "breakdown_axis_values",
    "has_required_breakdown_axes",
    "is_post_test_target_date",
    "require_complete_daily_curve",
    "scan_prospective_validation_authority",
    "target_dates_for_cutoff",
]


POST_TEST_TARGET_DATE_REQUIRED = True
