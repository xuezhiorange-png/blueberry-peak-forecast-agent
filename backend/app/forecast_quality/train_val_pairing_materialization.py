"""TRAIN/VALIDATION pairing materialization producer (R1).

Binds official SOURCE-002 partition content membership to incumbent forecast
replay grains and materializes partition-scoped S3EvaluationInput and pairing
packages. Does not publish packages or execute Coverage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, cast

from backend.app.forecast_quality.enums import FrozenVersion, SupportedQuantile
from backend.app.forecast_quality.schemas import S3BindingRow, S3EvaluationInput
from backend.app.forecast_quality.train_val_pairing import (
    ACCEPTED_SOURCE_DATASET_IDENTITY,
    ACCEPTED_TRAIN_PARTITION_IDENTITY,
    ACCEPTED_VALIDATION_PARTITION_IDENTITY,
    EXACT_ACTUAL_PAIRING_POLICY_V1,
    TRAIN_VAL_PAIRING_POLICY_V1,
    PartitionIdentity,
    TrainValidationS3BindingPairingPackage,
    build_candidate_train_validation_pairing_package,
    validate_published_pairing_package_invariants,
    verify_pairing_package_hash_replay,
)
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.schemas import (
    S2ForecastAuthorityBundle,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingRow,
)
from backend.app.rolling_backtest.signatures import s2_binding_key_hash
from backend.app.s2_materialized_dataset.lane_d.canonical import (
    MalformedPartitionBytesError,
    parse_partition_bytes,
)
from backend.app.s2_materialized_dataset.lane_d.hashing import content_sha256
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
    OFFICIAL_TRAIN_CONTENT_SHA256,
    OFFICIAL_TRAIN_ROW_COUNT,
    OFFICIAL_VALIDATION_CONTENT_SHA256,
    OFFICIAL_VALIDATION_ROW_COUNT,
    attest_accepted_s2_train_val_source_002_row_level_read,
)
from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read_live_obtain import (  # noqa: E501
    obtain_accepted_s2_train_val_content_bytes_from_bound_live_session,
)
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.exclusion import is_bason_factory, is_forbidden_variety
from backend.app.s3_daily_rowset.forecast_port import (
    ForecastAvailability,
    IncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    compute_content_identity_sha256,
    project_incumbent_forecast_artifact_entries,
)
from backend.app.s3_daily_rowset.incumbent_forecast_daily_curve_live_obtain import (
    LAWFUL_PIT_VISIBLE_INCUMBENT_DAILY_FORECAST_VALUE_SOURCE,
    obtain_live_incumbent_forecast_daily_curve_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF,
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.registry import (
    V0_3_S3_ACTUALS_AUTHORITY,
    V0_3_S3_FORECASTS_AUTHORITY,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    reviewed_grain_identity_set_identity_sha256,
)
from backend.app.s3_daily_rowset.schemas import HORIZON_DAYS, EvaluationInstanceCell
from backend.app.s3_daily_rowset.window import (
    DEFAULT_IN_SEASON_MONTHS,
    expected_forecast_target_date,
)

TRAIN_VAL_PAIRING_MATERIALIZATION_PRODUCER_V1 = (
    "v0-3-s3-b-train-val-pairing-materialization-producer-v1"
)
EXISTING_CANONICAL_SOURCE_002_PARTITION_ROW_PARSER = (
    "backend/app/s2_materialized_dataset/lane_d/canonical.py:parse_partition_bytes"
)
ACTUAL_PARTITION_LOOKUP_KEY: tuple[str, ...] = (
    "season_business_key",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "target_date",
)
FORECAST_BINDING_KEY: tuple[str, ...] = (
    "request_hash",
    "node_identity_hash",
    "season_business_key",
    "farm_business_key",
    "subfarm_business_key",
    "variety_business_key",
    "forecast_quantile",
    "horizon_days",
    "target_date",
    "forecast_run_identity",
)
FORECAST_BINDING_KEY_AUTHORITY_SOURCE = (
    "backend/app/rolling_backtest/signatures.py:s2_binding_key_hash"
)
FORECAST_SOURCE_KIND = "IncumbentForecastReplaySource"


class TrainValidationPairingMaterializationBlocker(StrEnum):
    NONE = "NONE"
    SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED = "SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED"
    OFFICIAL_PARTITION_BYTES_NOT_OBTAINED = "OFFICIAL_PARTITION_BYTES_NOT_OBTAINED"
    OFFICIAL_HASH_MISMATCH = "OFFICIAL_HASH_MISMATCH"
    OFFICIAL_COUNT_MISMATCH = "OFFICIAL_COUNT_MISMATCH"
    MALFORMED_PARTITION_BYTES = "MALFORMED_PARTITION_BYTES"
    NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS = "NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS"
    NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER = "NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER"
    REVIEWED_FORECAST_GRAIN_MISMATCH = "REVIEWED_FORECAST_GRAIN_MISMATCH"
    CROSS_PARTITION_SOURCE_ROW_IDENTITY = "CROSS_PARTITION_SOURCE_ROW_IDENTITY"
    DUPLICATE_ACTUAL_GRAIN_IN_PARTITION = "DUPLICATE_ACTUAL_GRAIN_IN_PARTITION"
    DUPLICATE_FORECAST_BINDING_KEY = "DUPLICATE_FORECAST_BINDING_KEY"
    NATIVE_FLOAT_IN_BINDING_ROW = "NATIVE_FLOAT_IN_BINDING_ROW"
    MEMBERSHIP_PROOF_VIOLATION = "MEMBERSHIP_PROOF_VIOLATION"


@dataclass(frozen=True, slots=True)
class PartitionRowMembershipProof:
    partition: Literal["TRAIN", "VALIDATION"]
    source_partition_identity_sha256: str
    source_partition_content_sha256: str
    source_row_identity: str


@dataclass(frozen=True, slots=True)
class OfficialPartitionRows:
    train_rows: tuple[MaterializableRow, ...]
    validation_rows: tuple[MaterializableRow, ...]
    train_content_sha256: str
    validation_content_sha256: str


@dataclass(frozen=True, slots=True)
class PartitionBindingMaterializationStats:
    partition: Literal["TRAIN", "VALIDATION"]
    source_row_count: int
    binding_row_count: int
    exact_paired_row_count: int
    not_computable_row_count: int
    excluded_row_count: int
    s2_binding_row_set_hash: str
    s2_run_identity: str
    s2_manifest_identity: str


@dataclass(frozen=True, slots=True)
class TrainValidationPairingMaterializationResult:
    completed: bool
    blocker: TrainValidationPairingMaterializationBlocker
    official_partitions: OfficialPartitionRows | None = None
    forecast_row_count: int = 0
    forecast_content_identity_sha256: str | None = None
    train_stats: PartitionBindingMaterializationStats | None = None
    validation_stats: PartitionBindingMaterializationStats | None = None
    train_evaluation_input: S3EvaluationInput | None = None
    validation_evaluation_input: S3EvaluationInput | None = None
    train_pairing_package: TrainValidationS3BindingPairingPackage | None = None
    validation_pairing_package: TrainValidationS3BindingPairingPackage | None = None
    train_membership_proofs: tuple[PartitionRowMembershipProof, ...] = ()
    validation_membership_proofs: tuple[PartitionRowMembershipProof, ...] = ()
    cross_partition_row_count: int = 0
    test_row_count: int = 0


@dataclass(frozen=True, slots=True)
class TrainValidationPairingMaterializationDeps:
    official_partitions: OfficialPartitionRows
    forecast_replay_entries: tuple[IncumbentForecastArtifactEntry, ...]
    forecast_provider: IncumbentDailyCurveProvider
    forecast_binding_authority: S2ForecastAuthorityBundle
    forecast_cutoff_authority_identity: str
    forecast_content_identity_sha256: str


GrainKey = tuple[str, str, str, str, date]
MembershipIndexEntry = tuple[MaterializableRow, PartitionRowMembershipProof]
MembershipIndex = dict[GrainKey, MembershipIndexEntry]
FinalizePartitionResult = tuple[
    S3EvaluationInput,
    TrainValidationS3BindingPairingPackage,
    PartitionBindingMaterializationStats,
]


def _parse_reviewed_cutoff() -> datetime:
    return datetime.fromisoformat(REVIEW_CUTOFF_AT)


def _reviewed_forecast_entries(
    replay_entries: tuple[IncumbentForecastArtifactEntry, ...],
) -> tuple[IncumbentForecastArtifactEntry, ...]:
    cutoff = _parse_reviewed_cutoff()
    accepted = project_incumbent_forecast_artifact_entries(replay_entries)
    filtered = tuple(
        entry
        for entry in accepted
        if entry.model_id == REVIEW_MODEL_ID
        and entry.forecast_quantile in REVIEW_QUANTILES
        and entry.forecast_cutoff_at == cutoff
    )
    if len(filtered) != len(REVIEW_QUANTILES):
        return ()
    return filtered


def load_official_partition_rows_from_content_bytes(
    *,
    train_content_bytes: bytes,
    validation_content_bytes: bytes,
) -> OfficialPartitionRows | TrainValidationPairingMaterializationBlocker:
    train_hash = content_sha256(train_content_bytes)
    validation_hash = content_sha256(validation_content_bytes)
    if (
        train_hash != OFFICIAL_TRAIN_CONTENT_SHA256
        or validation_hash != OFFICIAL_VALIDATION_CONTENT_SHA256
    ):
        return TrainValidationPairingMaterializationBlocker.OFFICIAL_HASH_MISMATCH
    try:
        train_rows = parse_partition_bytes(train_content_bytes)
        validation_rows = parse_partition_bytes(validation_content_bytes)
    except MalformedPartitionBytesError:
        return TrainValidationPairingMaterializationBlocker.MALFORMED_PARTITION_BYTES
    if (
        len(train_rows) != OFFICIAL_TRAIN_ROW_COUNT
        or len(validation_rows) != OFFICIAL_VALIDATION_ROW_COUNT
    ):
        return TrainValidationPairingMaterializationBlocker.OFFICIAL_COUNT_MISMATCH
    return OfficialPartitionRows(
        train_rows=train_rows,
        validation_rows=validation_rows,
        train_content_sha256=train_hash,
        validation_content_sha256=validation_hash,
    )


def _build_partition_s2_binding_request(
    aligned_grains: frozenset[tuple[str, str, str, str]],
    *,
    forecast_cutoff_at: datetime,
) -> S2HistoricalBacktestRequest:
    return S2HistoricalBacktestRequest(
        season_business_keys=tuple(sorted({grain[0] for grain in aligned_grains})),
        farm_business_keys=tuple(sorted({grain[1] for grain in aligned_grains})),
        subfarm_business_keys=tuple(sorted({grain[2] for grain in aligned_grains})),
        variety_business_keys=tuple(sorted({grain[3] for grain in aligned_grains})),
        master_identity_resolver_version="v0-3-s3-source-002-partition-materialization-v1",
        mapping_policy_version="v0-3-s3-source-002-partition-materialization-v1",
        resolved_identity_snapshot_hash=(
            ACCEPTED_SOURCE_DATASET_IDENTITY.materialized_dataset_identity_sha256
        ),
        authority_selection_policy_version=TRAIN_VAL_PAIRING_MATERIALIZATION_PRODUCER_V1,
        forecast_cutoff_at=forecast_cutoff_at,
        label_observation_cutoff_at=forecast_cutoff_at,
        label_visibility_mode="AS_OF_EVALUATION",
        requested_horizons_days=tuple(sorted(HORIZON_DAYS)),
    )


def _provisional_s2_binding_row_for_key_hash(
    request: S2HistoricalBacktestRequest,
    *,
    season_business_key: str,
    farm_business_key: str,
    subfarm_business_key: str,
    variety_business_key: str,
    forecast_quantile: Literal["P50", "P80", "P90"],
    horizon_days: int,
    target_date: date,
    forecast_authority: S2ForecastAuthorityBundle,
) -> S2HistoricalBindingRow:
    return S2HistoricalBindingRow(
        season_id=1,
        season_business_key=season_business_key,
        farm_business_key=farm_business_key,
        subfarm_business_key=subfarm_business_key,
        variety_business_key=variety_business_key,
        forecast_quantile=forecast_quantile,
        horizon_days=horizon_days,
        target_date=target_date,
        forecast_cutoff_at=request.forecast_cutoff_at,
        label_observation_cutoff_at=request.label_observation_cutoff_at,
        label_visibility_mode=request.label_visibility_mode,
        forecast_value_kg=Decimal("0"),
        actual_value_kg=None,
        forecast_authority=forecast_authority,
        actual_label=None,
        physical_alignment_status="UNVERIFIED",
        row_status="EXCLUDED",
        reason_code="MATERIALIZATION_BINDING_KEY_PROJECTION",
        authority_verification="SYNTHETIC_ENGINEERING",
        binding_key_hash="0" * 64,
        row_hash="0" * 64,
    )


def compute_canonical_forecast_binding_key_hash(
    request: S2HistoricalBacktestRequest,
    *,
    season_business_key: str,
    farm_business_key: str,
    subfarm_business_key: str,
    variety_business_key: str,
    forecast_quantile: Literal["P50", "P80", "P90"],
    horizon_days: int,
    target_date: date,
    forecast_authority: S2ForecastAuthorityBundle,
) -> str:
    provisional = _provisional_s2_binding_row_for_key_hash(
        request,
        season_business_key=season_business_key,
        farm_business_key=farm_business_key,
        subfarm_business_key=subfarm_business_key,
        variety_business_key=variety_business_key,
        forecast_quantile=forecast_quantile,
        horizon_days=horizon_days,
        target_date=target_date,
        forecast_authority=forecast_authority,
    )
    return s2_binding_key_hash(request, provisional)


def _forecast_provider_blocks_materialization(provider: IncumbentDailyCurveProvider) -> bool:
    return provider.is_placeholder_provider


def _zero_comparable_pairings(
    train_stats: PartitionBindingMaterializationStats,
    validation_stats: PartitionBindingMaterializationStats,
) -> bool:
    return (train_stats.exact_paired_row_count + validation_stats.exact_paired_row_count) == 0


def compute_s3_binding_row_hash(row: S3BindingRow) -> str:
    payload = {
        "forecast_business_key": row.forecast_business_key,
        "actual_physical_key": row.actual_physical_key,
        "stable_actual_identity": row.stable_actual_identity,
        "forecast_value_kg": row.forecast_value_kg,
        "actual_value_kg": row.actual_value_kg,
        "forecast_quantile": row.forecast_quantile.value,
        "forecast_horizon_days": row.forecast_horizon_days,
        "forecast_target_date": row.forecast_target_date,
        "forecast_cutoff_at": row.forecast_cutoff_at,
        "s2_status": row.s2_status,
        "season_business_key": row.season_business_key,
        "farm_business_key": row.farm_business_key,
        "subfarm_business_key": row.subfarm_business_key,
        "variety_business_key": row.variety_business_key,
        "model_identity": row.model_identity,
        "actual_visibility_timestamp": row.actual_visibility_timestamp,
    }
    return sha256_payload(payload)


def compute_s3_binding_row_set_hash(rows: tuple[S3BindingRow, ...]) -> str:
    from backend.app.forecast_quality.canonical import canonical_json_bytes

    row_hashes = sorted(compute_s3_binding_row_hash(row) for row in rows)
    return hashlib.sha256(canonical_json_bytes({"row_hashes": row_hashes})).hexdigest()


def compute_materialization_s2_run_identity(
    *,
    partition: Literal["TRAIN", "VALIDATION"],
    partition_identity_sha256: str,
    partition_content_sha256: str,
    binding_row_set_hash: str,
    forecast_content_identity_sha256: str,
) -> str:
    payload = {
        "producer_version": TRAIN_VAL_PAIRING_MATERIALIZATION_PRODUCER_V1,
        "partition": partition,
        "partition_identity_sha256": partition_identity_sha256,
        "partition_content_sha256": partition_content_sha256,
        "binding_row_set_hash": binding_row_set_hash,
        "forecast_content_identity_sha256": forecast_content_identity_sha256,
        "source_dataset_identity": {
            "dataset_id": ACCEPTED_SOURCE_DATASET_IDENTITY.dataset_id,
            "dataset_version": ACCEPTED_SOURCE_DATASET_IDENTITY.dataset_version,
            "materialized_dataset_identity_sha256": (
                ACCEPTED_SOURCE_DATASET_IDENTITY.materialized_dataset_identity_sha256
            ),
        },
    }
    return sha256_payload(payload)


def compute_materialization_s2_manifest_identity(
    *,
    partition: Literal["TRAIN", "VALIDATION"],
    s2_run_identity: str,
    binding_row_set_hash: str,
    forecast_cutoff_authority_identity: str,
) -> str:
    payload = {
        "producer_version": TRAIN_VAL_PAIRING_MATERIALIZATION_PRODUCER_V1,
        "partition": partition,
        "s2_run_identity": s2_run_identity,
        "binding_row_set_hash": binding_row_set_hash,
        "forecast_cutoff_authority_identity": forecast_cutoff_authority_identity,
        "actuals_authority_identity": V0_3_S3_ACTUALS_AUTHORITY,
    }
    return sha256_payload(payload)


def _grain_key(row: MaterializableRow) -> tuple[str, str, str, str, date]:
    return (
        row.season,
        row.farm,
        row.subfarm,
        row.variety,
        row.harvest_business_date,
    )


def _build_membership_index(
    *,
    partition: Literal["TRAIN", "VALIDATION"],
    partition_identity: PartitionIdentity,
    rows: tuple[MaterializableRow, ...],
) -> tuple[MembershipIndex, tuple[PartitionRowMembershipProof, ...]] | (
    TrainValidationPairingMaterializationBlocker
):
    index: MembershipIndex = {}
    proofs: list[PartitionRowMembershipProof] = []
    for row in rows:
        if is_forbidden_variety(row.variety) or is_bason_factory(row.farm):
            continue
        if row.harvest_business_date.month not in DEFAULT_IN_SEASON_MONTHS:
            continue
        proof = PartitionRowMembershipProof(
            partition=partition,
            source_partition_identity_sha256=partition_identity.partition_identity_sha256,
            source_partition_content_sha256=partition_identity.content_sha256,
            source_row_identity=row.source_row_identity,
        )
        key = _grain_key(row)
        if key in index:
            return TrainValidationPairingMaterializationBlocker.DUPLICATE_ACTUAL_GRAIN_IN_PARTITION
        index[key] = (row, proof)
        proofs.append(proof)
    return index, tuple(proofs)


def _aligned_grains(
    index: MembershipIndex,
) -> frozenset[tuple[str, str, str, str]]:
    return frozenset((key[0], key[1], key[2], key[3]) for key in index)


def _build_partition_binding_rows(
    *,
    partition: Literal["TRAIN", "VALIDATION"],
    membership_index: MembershipIndex,
    aligned_grains: frozenset[tuple[str, str, str, str]],
    forecast_entries: tuple[IncumbentForecastArtifactEntry, ...],
    forecast_provider: IncumbentDailyCurveProvider,
    s2_binding_request: S2HistoricalBacktestRequest,
    forecast_binding_authority: S2ForecastAuthorityBundle,
) -> tuple[tuple[S3BindingRow, ...], PartitionBindingMaterializationStats] | (
    TrainValidationPairingMaterializationBlocker
):
    binding_rows: list[S3BindingRow] = []
    seen_forecast_keys: set[str] = set()
    exact_paired = 0
    not_computable = 0
    excluded = 0

    for season, farm, subfarm, variety in sorted(aligned_grains):
        for forecast_entry in forecast_entries:
            if forecast_entry.model_id != REVIEW_MODEL_ID:
                continue
            cell = EvaluationInstanceCell(
                season=season,
                farm=farm,
                subfarm=subfarm,
                variety=variety,
                model_id=forecast_entry.model_id,
                forecast_cutoff_at=forecast_entry.forecast_cutoff_at,
                forecast_quantile=forecast_entry.forecast_quantile,
            )
            for horizon_days in sorted(HORIZON_DAYS):
                target_date = expected_forecast_target_date(
                    forecast_entry.forecast_cutoff_at,
                    horizon_days,
                )
                actual_lookup = membership_index.get((season, farm, subfarm, variety, target_date))
                forecast_lookup = forecast_provider.forecast_kg_for_day(
                    cell,
                    business_date=target_date,
                )
                forecast_key = compute_canonical_forecast_binding_key_hash(
                    s2_binding_request,
                    season_business_key=season,
                    farm_business_key=farm,
                    subfarm_business_key=subfarm,
                    variety_business_key=variety,
                    forecast_quantile=cast(
                        Literal["P50", "P80", "P90"],
                        forecast_entry.forecast_quantile,
                    ),
                    horizon_days=horizon_days,
                    target_date=target_date,
                    forecast_authority=forecast_binding_authority,
                )
                if forecast_key in seen_forecast_keys:
                    return (
                        TrainValidationPairingMaterializationBlocker.DUPLICATE_FORECAST_BINDING_KEY
                    )
                seen_forecast_keys.add(forecast_key)

                actual_row: MaterializableRow | None = None
                proof: PartitionRowMembershipProof | None = None
                if actual_lookup is not None:
                    actual_row, proof = actual_lookup
                    if proof.partition != partition:
                        return (
                            TrainValidationPairingMaterializationBlocker.MEMBERSHIP_PROOF_VIOLATION
                        )

                forecast_kg: Decimal | None = None
                actual_kg: Decimal | None = None
                actual_physical_key: str | None = None
                stable_actual_identity: str | None = None
                visibility: datetime | None = None
                status = "EXCLUDED"

                if actual_row is None:
                    status = "EXCLUDED"
                    excluded += 1
                elif (
                    forecast_lookup.availability != ForecastAvailability.AVAILABLE
                    or forecast_lookup.forecast_harvest_quantity_kg is None
                ):
                    status = "NOT_COMPUTABLE"
                    not_computable += 1
                else:
                    forecast_kg = forecast_lookup.forecast_harvest_quantity_kg
                    actual_kg = actual_row.actual_harvest_quantity_kg
                    if isinstance(forecast_kg, float) or isinstance(actual_kg, float):
                        return (
                            TrainValidationPairingMaterializationBlocker.NATIVE_FLOAT_IN_BINDING_ROW
                        )
                    actual_physical_key = actual_row.cleaned_row_identity
                    stable_actual_identity = actual_row.source_row_identity
                    visibility = forecast_entry.forecast_cutoff_at
                    status = "COMPARABLE"
                    exact_paired += 1

                binding_rows.append(
                    S3BindingRow(
                        forecast_business_key=forecast_key,
                        actual_physical_key=actual_physical_key,
                        stable_actual_identity=stable_actual_identity,
                        forecast_value_kg=forecast_kg,
                        actual_value_kg=actual_kg,
                        forecast_quantile=SupportedQuantile(forecast_entry.forecast_quantile),
                        forecast_horizon_days=horizon_days,
                        forecast_target_date=target_date,
                        forecast_cutoff_at=forecast_entry.forecast_cutoff_at,
                        s2_status=status,
                        season_business_key=season,
                        farm_business_key=farm,
                        subfarm_business_key=subfarm,
                        variety_business_key=variety,
                        model_identity=forecast_entry.model_id,
                        actual_visibility_timestamp=visibility,
                    )
                )

    binding_rows_tuple = tuple(sorted(binding_rows, key=lambda row: row.forecast_business_key))
    partition_identity = (
        ACCEPTED_TRAIN_PARTITION_IDENTITY
        if partition == "TRAIN"
        else ACCEPTED_VALIDATION_PARTITION_IDENTITY
    )
    row_set_hash = compute_s3_binding_row_set_hash(binding_rows_tuple)
    run_identity = compute_materialization_s2_run_identity(
        partition=partition,
        partition_identity_sha256=partition_identity.partition_identity_sha256,
        partition_content_sha256=partition_identity.content_sha256,
        binding_row_set_hash=row_set_hash,
        forecast_content_identity_sha256="",
    )
    stats = PartitionBindingMaterializationStats(
        partition=partition,
        source_row_count=len(membership_index),
        binding_row_count=len(binding_rows_tuple),
        exact_paired_row_count=exact_paired,
        not_computable_row_count=not_computable,
        excluded_row_count=excluded,
        s2_binding_row_set_hash=row_set_hash,
        s2_run_identity=run_identity,
        s2_manifest_identity="",
    )
    return binding_rows_tuple, stats


def _finalize_partition_materialization(
    *,
    partition: Literal["TRAIN", "VALIDATION"],
    partition_identity: PartitionIdentity,
    binding_rows: tuple[S3BindingRow, ...],
    stats: PartitionBindingMaterializationStats,
    forecast_content_identity_sha256: str,
    forecast_cutoff_authority_identity: str,
) -> FinalizePartitionResult:
    row_set_hash = compute_s3_binding_row_set_hash(binding_rows)
    run_identity = compute_materialization_s2_run_identity(
        partition=partition,
        partition_identity_sha256=partition_identity.partition_identity_sha256,
        partition_content_sha256=partition_identity.content_sha256,
        binding_row_set_hash=row_set_hash,
        forecast_content_identity_sha256=forecast_content_identity_sha256,
    )
    manifest_identity = compute_materialization_s2_manifest_identity(
        partition=partition,
        s2_run_identity=run_identity,
        binding_row_set_hash=row_set_hash,
        forecast_cutoff_authority_identity=forecast_cutoff_authority_identity,
    )
    evaluation_input = S3EvaluationInput(
        rows=binding_rows,
        s2_run_identity=run_identity,
        s2_manifest_identity=manifest_identity,
        s2_binding_row_set_hash=row_set_hash,
        metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        baseline_policy_version=FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )
    pairing_package = build_candidate_train_validation_pairing_package(
        partition=partition,
        partition_identity=partition_identity,
        evaluation_input=evaluation_input,
        forecast_cutoff_authority_identity=forecast_cutoff_authority_identity,
        exact_actual_pairing_policy_version=EXACT_ACTUAL_PAIRING_POLICY_V1,
        pairing_policy_version=TRAIN_VAL_PAIRING_POLICY_V1,
    )
    validate_published_pairing_package_invariants(pairing_package)
    assert verify_pairing_package_hash_replay(pairing_package)
    finalized_stats = PartitionBindingMaterializationStats(
        partition=stats.partition,
        source_row_count=stats.source_row_count,
        binding_row_count=stats.binding_row_count,
        exact_paired_row_count=stats.exact_paired_row_count,
        not_computable_row_count=stats.not_computable_row_count,
        excluded_row_count=stats.excluded_row_count,
        s2_binding_row_set_hash=row_set_hash,
        s2_run_identity=run_identity,
        s2_manifest_identity=manifest_identity,
    )
    return evaluation_input, pairing_package, finalized_stats


def materialize_train_validation_pairing_inputs(
    deps: TrainValidationPairingMaterializationDeps,
) -> TrainValidationPairingMaterializationResult:
    train_identity = ACCEPTED_TRAIN_PARTITION_IDENTITY
    validation_identity = ACCEPTED_VALIDATION_PARTITION_IDENTITY

    train_ids = {row.source_row_identity for row in deps.official_partitions.train_rows}
    validation_ids = {row.source_row_identity for row in deps.official_partitions.validation_rows}
    cross_partition = len(train_ids & validation_ids)

    if not deps.forecast_replay_entries:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS,
            official_partitions=deps.official_partitions,
            forecast_row_count=0,
            cross_partition_row_count=cross_partition,
        )

    reviewed_entries = _reviewed_forecast_entries(deps.forecast_replay_entries)
    if not reviewed_entries:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.REVIEWED_FORECAST_GRAIN_MISMATCH,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(deps.forecast_replay_entries),
            cross_partition_row_count=cross_partition,
        )

    if _forecast_provider_blocks_materialization(deps.forecast_provider):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(reviewed_entries),
            cross_partition_row_count=cross_partition,
        )

    train_index_result = _build_membership_index(
        partition="TRAIN",
        partition_identity=train_identity,
        rows=deps.official_partitions.train_rows,
    )
    if isinstance(train_index_result, TrainValidationPairingMaterializationBlocker):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=train_index_result,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(reviewed_entries),
            cross_partition_row_count=cross_partition,
        )
    train_index, train_proofs = train_index_result

    validation_index_result = _build_membership_index(
        partition="VALIDATION",
        partition_identity=validation_identity,
        rows=deps.official_partitions.validation_rows,
    )
    if isinstance(validation_index_result, TrainValidationPairingMaterializationBlocker):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=validation_index_result,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(reviewed_entries),
            cross_partition_row_count=cross_partition,
        )
    validation_index, validation_proofs = validation_index_result

    if cross_partition:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.CROSS_PARTITION_SOURCE_ROW_IDENTITY,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(reviewed_entries),
            train_membership_proofs=train_proofs,
            validation_membership_proofs=validation_proofs,
            cross_partition_row_count=cross_partition,
        )

    train_aligned_grains = _aligned_grains(train_index)
    validation_aligned_grains = _aligned_grains(validation_index)
    reviewed_cutoff = _parse_reviewed_cutoff()
    train_s2_request = _build_partition_s2_binding_request(
        train_aligned_grains,
        forecast_cutoff_at=reviewed_cutoff,
    )
    validation_s2_request = _build_partition_s2_binding_request(
        validation_aligned_grains,
        forecast_cutoff_at=reviewed_cutoff,
    )

    train_rows_result = _build_partition_binding_rows(
        partition="TRAIN",
        membership_index=train_index,
        aligned_grains=train_aligned_grains,
        forecast_entries=reviewed_entries,
        forecast_provider=deps.forecast_provider,
        s2_binding_request=train_s2_request,
        forecast_binding_authority=deps.forecast_binding_authority,
    )
    if isinstance(train_rows_result, TrainValidationPairingMaterializationBlocker):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=train_rows_result,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(reviewed_entries),
            train_membership_proofs=train_proofs,
            validation_membership_proofs=validation_proofs,
        )
    train_binding_rows, train_stats = train_rows_result

    validation_rows_result = _build_partition_binding_rows(
        partition="VALIDATION",
        membership_index=validation_index,
        aligned_grains=validation_aligned_grains,
        forecast_entries=reviewed_entries,
        forecast_provider=deps.forecast_provider,
        s2_binding_request=validation_s2_request,
        forecast_binding_authority=deps.forecast_binding_authority,
    )
    if isinstance(validation_rows_result, TrainValidationPairingMaterializationBlocker):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=validation_rows_result,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(reviewed_entries),
            train_membership_proofs=train_proofs,
            validation_membership_proofs=validation_proofs,
        )
    validation_binding_rows, validation_stats = validation_rows_result

    if _zero_comparable_pairings(train_stats, validation_stats):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER,
            official_partitions=deps.official_partitions,
            forecast_row_count=len(reviewed_entries),
            train_membership_proofs=train_proofs,
            validation_membership_proofs=validation_proofs,
            train_stats=train_stats,
            validation_stats=validation_stats,
        )

    train_eval, train_package, train_stats = _finalize_partition_materialization(
        partition="TRAIN",
        partition_identity=train_identity,
        binding_rows=train_binding_rows,
        stats=train_stats,
        forecast_content_identity_sha256=deps.forecast_content_identity_sha256,
        forecast_cutoff_authority_identity=deps.forecast_cutoff_authority_identity,
    )
    validation_eval, validation_package, validation_stats = _finalize_partition_materialization(
        partition="VALIDATION",
        partition_identity=validation_identity,
        binding_rows=validation_binding_rows,
        stats=validation_stats,
        forecast_content_identity_sha256=deps.forecast_content_identity_sha256,
        forecast_cutoff_authority_identity=deps.forecast_cutoff_authority_identity,
    )

    return TrainValidationPairingMaterializationResult(
        completed=True,
        blocker=TrainValidationPairingMaterializationBlocker.NONE,
        official_partitions=deps.official_partitions,
        forecast_row_count=len(reviewed_entries),
        forecast_content_identity_sha256=deps.forecast_content_identity_sha256,
        train_stats=train_stats,
        validation_stats=validation_stats,
        train_evaluation_input=train_eval,
        validation_evaluation_input=validation_eval,
        train_pairing_package=train_package,
        validation_pairing_package=validation_package,
        train_membership_proofs=train_proofs,
        validation_membership_proofs=validation_proofs,
        cross_partition_row_count=0,
        test_row_count=0,
    )


def materialize_train_validation_pairing_inputs_live() -> (
    TrainValidationPairingMaterializationResult
):
    attestation = attest_accepted_s2_train_val_source_002_row_level_read()
    if not attestation.attested:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED,
        )

    obtain = obtain_accepted_s2_train_val_content_bytes_from_bound_live_session()
    if (
        not obtain.obtained
        or obtain.train_content_bytes is None
        or obtain.validation_content_bytes is None
    ):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.OFFICIAL_PARTITION_BYTES_NOT_OBTAINED,
        )

    official = load_official_partition_rows_from_content_bytes(
        train_content_bytes=obtain.train_content_bytes,
        validation_content_bytes=obtain.validation_content_bytes,
    )
    if isinstance(official, TrainValidationPairingMaterializationBlocker):
        return TrainValidationPairingMaterializationResult(completed=False, blocker=official)

    replay_source = IncumbentForecastReplaySource()
    if replay_source.uses_harvest_date_as_forecast_cutoff:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS,
            official_partitions=official,
        )
    replay_entries = replay_source.obtain()
    if not replay_entries:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS,
            official_partitions=official,
            forecast_row_count=0,
        )

    reviewed_entries = _reviewed_forecast_entries(replay_entries)
    if not reviewed_entries:
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.REVIEWED_FORECAST_GRAIN_MISMATCH,
            official_partitions=official,
            forecast_row_count=len(replay_entries),
        )

    forecast_content_identity = compute_content_identity_sha256(rows=reviewed_entries)
    forecast_cutoff_authority = reviewed_grain_identity_set_identity_sha256()

    curve_obtain = obtain_live_incumbent_forecast_daily_curve_provider()
    if (
        not curve_obtain.obtained
        or curve_obtain.provider is None
        or curve_obtain.forecast_binding_authority is None
    ):
        return TrainValidationPairingMaterializationResult(
            completed=False,
            blocker=TrainValidationPairingMaterializationBlocker.NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER,
            official_partitions=official,
            forecast_row_count=len(reviewed_entries),
        )

    deps = TrainValidationPairingMaterializationDeps(
        official_partitions=official,
        forecast_replay_entries=replay_entries,
        forecast_provider=curve_obtain.provider,
        forecast_binding_authority=curve_obtain.forecast_binding_authority,
        forecast_cutoff_authority_identity=forecast_cutoff_authority,
        forecast_content_identity_sha256=forecast_content_identity,
    )
    return materialize_train_validation_pairing_inputs(deps)


def build_materialization_evidence_payload(
    result: TrainValidationPairingMaterializationResult,
    *,
    base_main_sha: str,
    user_gate: str = "可以",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "task_id": "V0_3_S3_B_TRAIN_VAL_PAIRING_MATERIALIZATION_R1",
        "base_main_sha": base_main_sha,
        "user_gate": user_gate,
        "materialization_completed": result.completed,
        "materialization_blocker": result.blocker.value,
        "forecast_source_kind": FORECAST_SOURCE_KIND,
        "forecast_authority": V0_3_S3_FORECASTS_AUTHORITY,
        "harvest_business_date_is_not_forecast_cutoff": (
            HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF
        ),
        "lawful_pit_visible_incumbent_daily_forecast_value_source": (
            LAWFUL_PIT_VISIBLE_INCUMBENT_DAILY_FORECAST_VALUE_SOURCE
        ),
        "actual_partition_lookup_key": list(ACTUAL_PARTITION_LOOKUP_KEY),
        "forecast_binding_key": list(FORECAST_BINDING_KEY),
        "forecast_binding_key_authority_source": FORECAST_BINDING_KEY_AUTHORITY_SOURCE,
        "existing_canonical_source_002_partition_row_parser": (
            EXISTING_CANONICAL_SOURCE_002_PARTITION_ROW_PARSER
        ),
        "forecast_row_count": result.forecast_row_count,
        "cross_partition_row_count": result.cross_partition_row_count,
        "test_row_count": result.test_row_count,
        "production_published_pairing_package_count": 0,
        "production_issued_partition_authority_record_count": 0,
        "issued_partition_authority_schema_version_count": 0,
        "s3_b_coverage_execution": "NOT_COMPUTABLE_OR_BLOCKED",
        "test_remains_sealed": True,
    }
    if result.official_partitions is not None:
        payload["train_source_row_count"] = len(result.official_partitions.train_rows)
        payload["validation_source_row_count"] = len(result.official_partitions.validation_rows)
        payload["train_official_content_sha256"] = result.official_partitions.train_content_sha256
        payload["validation_official_content_sha256"] = (
            result.official_partitions.validation_content_sha256
        )
    if result.train_stats is not None:
        payload["train_binding_row_count"] = result.train_stats.binding_row_count
        payload["train_exact_paired_row_count"] = result.train_stats.exact_paired_row_count
        payload["train_not_computable_row_count"] = result.train_stats.not_computable_row_count
        payload["train_s3_binding_row_set_hash"] = result.train_stats.s2_binding_row_set_hash
    if result.validation_stats is not None:
        payload["validation_binding_row_count"] = result.validation_stats.binding_row_count
        payload["validation_exact_paired_row_count"] = (
            result.validation_stats.exact_paired_row_count
        )
        payload["validation_not_computable_row_count"] = (
            result.validation_stats.not_computable_row_count
        )
        payload["validation_s3_binding_row_set_hash"] = (
            result.validation_stats.s2_binding_row_set_hash
        )
    if result.train_pairing_package is not None:
        payload["train_pairing_package_identity"] = (
            result.train_pairing_package.pairing_package_identity
        )
        payload["train_pairing_package_canonical_hash"] = (
            result.train_pairing_package.canonical_hash
        )
    if result.validation_pairing_package is not None:
        payload["validation_pairing_package_identity"] = (
            result.validation_pairing_package.pairing_package_identity
        )
        payload["validation_pairing_package_canonical_hash"] = (
            result.validation_pairing_package.canonical_hash
        )
    return payload
