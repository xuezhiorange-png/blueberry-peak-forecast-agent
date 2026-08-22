"""Lane B cleaning projection and dataset-version builder (contract §4.4–§4.5)."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.lane_a.lineage import (
    controlled_ingest_source_002_from_environment,
    run_source_002_identity_verification,
)
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    fetch_import_batch_by_external_identity,
    fetch_source_row_content_index_for_batch,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SOURCE_002_COHORT_ID,
    SOURCE_002_CONTROLLED_EXTERNAL_BATCH_ID,
    SOURCE_002_DECLARED_ROW_COUNT,
    SOURCE_002_MAPPING_SNAPSHOT_HASH,
    SOURCE_002_SOURCE_SYSTEM,
    RawImportBatchIdentity,
    Source002IdentityVerificationStatus,
    SourceRowIdentity,
    SourceRowLineageInput,
)
from backend.app.s2_materialized_dataset.lane_a.source_row import (
    build_source_row_identity,
    iter_source_002_row_inputs,
)
from backend.app.s2_materialized_dataset.lane_b.correction_ledger import (
    build_correction_ledger_entries,
    correction_identities_for_row,
    effective_quantity_after_corrections,
)
from backend.app.s2_materialized_dataset.lane_b.exclusion_ledger import (
    build_exclusion_ledger_entries,
    exclusion_identities_for_row,
    is_row_excluded,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import (
    compute_canonical_grain_key_payload,
    compute_cleaned_dataset_version_content_hash,
    compute_cleaned_dataset_version_identity_hash,
    compute_cleaned_row_content_hash,
    compute_cleaned_row_identity_hash,
    compute_quality_report_identity_hash,
    compute_synthetic_raw_import_batch_identity_hash,
    compute_synthetic_raw_source_artifact_identity_hash,
    compute_synthetic_source_row_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_b.quality import (
    PreparedCleaningRow,
    evaluate_quality_findings,
    findings_for_source_row,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    SOURCE_002_CLEANING_DECISION_AUTHORITY,
    SOURCE_002_JULY_COHORT_EXCLUDED_ROW_COUNT,
    SOURCE_002_JULY_COHORT_EXCLUSION_REASON,
    SOURCE_002_MAPPED_SEASON_BUSINESS_KEY,
    SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY,
    CanonicalGrainCollisionBlockedError,
    CanonicalGrainKey,
    CleanedDatasetVersionRecord,
    CleanedRowRecord,
    CleaningBuildRequest,
    CleaningBuildResult,
    CorrectionLedgerEntryRecord,
    ExclusionCode,
    ExclusionLedgerEntryRecord,
    LaneASourceRowsNotMaterializedError,
    ManualCorrectionRequest,
    ManualExclusionRequest,
    QuantityPresenceStatus,
    Source002CleaningBlockedError,
    Source002CleaningResult,
    SyntheticSourceRowIdentity,
    SyntheticSourceRowInput,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CleanedDatasetVersionConflictError",
    "CleanedRowConflictError",
    "SOURCE_002_JULY_EXCLUSION_DATE",
    "SOURCE_002_SEASON_END",
    "SOURCE_002_SEASON_START",
    "assert_no_canonical_grain_collisions_or_fail",
    "assert_replay_parity",
    "build_canonical_grain_key",
    "build_cleaned_dataset",
    "build_july_cohort_exclusions",
    "build_source_002_cleaning_request",
    "canonical_grain_collision_groups",
    "clean_source_002_from_persisted",
    "controlled_clean_source_002_from_environment",
    "resolve_quantity_presence",
    "resolve_source_002_season_business_key",
    "source_row_input_from_persisted_lane_a",
]


SOURCE_002_SEASON_START = date(2025, 8, 1)
SOURCE_002_SEASON_END = date(2026, 6, 30)
SOURCE_002_JULY_EXCLUSION_DATE = date(2025, 7, 22)


class CleanedDatasetVersionConflictError(ValueError):
    """Raised when the same version identity would carry different content."""


class CleanedRowConflictError(ValueError):
    """Raised when duplicate grain keys or lineage conflicts appear."""


def duplicate_grain_groups(
    prepared_rows: tuple[PreparedCleaningRow, ...],
) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for prepared in prepared_rows:
        grain_key = "|".join(
            (
                str(prepared.canonical_grain_key_payload["season_business_key"]),
                str(prepared.canonical_grain_key_payload["farm_business_key"]),
                str(prepared.canonical_grain_key_payload["subfarm_business_key"]),
                str(prepared.canonical_grain_key_payload["variety_business_key"]),
                str(prepared.canonical_grain_key_payload["harvest_business_date"]),
            )
        )
        groups.setdefault(grain_key, []).append(prepared.source_row_identity_hash)
    return {key: tuple(sorted(values)) for key, values in groups.items() if len(values) > 1}


def assert_duplicate_grains_resolved_or_fail(
    *,
    duplicate_groups: dict[str, tuple[str, ...]],
    exclusion_entries: tuple[ExclusionLedgerEntryRecord, ...],
) -> None:
    for grain_key, row_hashes in sorted(duplicate_groups.items()):
        active = tuple(
            source_row_identity_hash
            for source_row_identity_hash in row_hashes
            if not is_row_excluded(
                source_row_identity_hash=source_row_identity_hash,
                entries=exclusion_entries,
            )
        )
        if len(active) > 1:
            raise CleanedRowConflictError(
                f"duplicate canonical grain without versioned exclusion disposition: {grain_key}"
            )


def should_publish_cleaned_row(
    *,
    source_row_identity_hash: str,
    grain_key: str,
    duplicate_groups: dict[str, tuple[str, ...]],
    exclusion_entries: tuple[ExclusionLedgerEntryRecord, ...],
) -> bool:
    if grain_key not in duplicate_groups:
        return True
    return not is_row_excluded(
        source_row_identity_hash=source_row_identity_hash,
        entries=exclusion_entries,
    )


def resolve_quantity_presence(source_row: SyntheticSourceRowInput) -> QuantityPresenceStatus:
    if source_row.actual_harvest_quantity_kg is None:
        return QuantityPresenceStatus.UNKNOWN_NOT_ZERO
    return QuantityPresenceStatus.KNOWN


def build_canonical_grain_key(source_row: SyntheticSourceRowInput) -> CanonicalGrainKey:
    return CanonicalGrainKey(
        season_business_key=source_row.season_business_key,
        farm_business_key=source_row.farm_business_key,
        subfarm_business_key=source_row.subfarm_business_key,
        variety_business_key=source_row.variety_business_key,
        harvest_business_date=source_row.harvest_business_date,
    )


def _source_row_identity_hash(source_row: SyntheticSourceRowInput) -> str:
    if source_row.persisted_source_row_identity_hash is not None:
        return source_row.persisted_source_row_identity_hash
    identity = source_row.identity.model_dump(mode="python")
    return compute_synthetic_source_row_identity_hash(identity)


def resolve_source_002_season_business_key(harvest_business_date: date) -> str:
    if harvest_business_date == SOURCE_002_JULY_EXCLUSION_DATE:
        return SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY
    if SOURCE_002_SEASON_START <= harvest_business_date <= SOURCE_002_SEASON_END:
        return SOURCE_002_MAPPED_SEASON_BUSINESS_KEY
    raise Source002CleaningBlockedError(
        f"harvest date {harvest_business_date.isoformat()} is outside governed season mapping"
    )


def source_row_input_from_persisted_lane_a(
    *,
    row_input: SourceRowLineageInput,
    persisted_identity: SourceRowIdentity,
) -> SyntheticSourceRowInput:
    business = row_input.business_content
    harvest_date = business.harvest_business_date
    return SyntheticSourceRowInput(
        identity=SyntheticSourceRowIdentity(
            raw_source_artifact_identity_hash=persisted_identity.raw_source_artifact_identity_hash,
            raw_import_batch_identity_hash=persisted_identity.raw_import_batch_identity_hash,
            external_logical_record_id=persisted_identity.external_logical_record_id,
            external_revision_id=persisted_identity.external_revision_id,
            revision_number=persisted_identity.revision_number,
            source_system=persisted_identity.source_system,
            source_row_identity_version=persisted_identity.source_row_identity_version,
            schema_version=persisted_identity.schema_version,
            source_version=persisted_identity.source_version,
            source_sheet_name=persisted_identity.source_sheet_name,
            source_row_number=persisted_identity.source_row_number,
        ),
        season_business_key=resolve_source_002_season_business_key(harvest_date),
        farm_business_key=business.farm_code,
        subfarm_business_key=business.subfarm_or_plot_code,
        variety_business_key=business.variety_code,
        harvest_business_date=harvest_date,
        actual_harvest_quantity_kg=business.actual_harvest_quantity_kg,
        # Lane A rejects missing weights; explicit zero kg is a known quantity.
        missing_record_semantics="KNOWN",
        persisted_source_row_identity_hash=persisted_identity.source_row_identity_hash,
    )


def build_july_cohort_exclusions(
    *,
    source_rows: tuple[SyntheticSourceRowInput, ...],
) -> tuple[ManualExclusionRequest, ...]:
    exclusions: list[ManualExclusionRequest] = []
    for source_row in source_rows:
        if source_row.harvest_business_date != SOURCE_002_JULY_EXCLUSION_DATE:
            continue
        source_hash = _source_row_identity_hash(source_row)
        exclusions.append(
            ManualExclusionRequest(
                exclusion_event_id=f"source-002-s1-july-cohort-exclusion:{source_hash}",
                source_row_identity_hash=source_hash,
                exclusion_code=ExclusionCode.BUSINESS_EXCLUSION,
                exclusion_reason_reference=SOURCE_002_JULY_COHORT_EXCLUSION_REASON,
                decision_authority_reference=SOURCE_002_CLEANING_DECISION_AUTHORITY,
            )
        )
    return tuple(sorted(exclusions, key=lambda item: item.exclusion_event_id))


def canonical_grain_collision_groups(
    source_rows: tuple[SyntheticSourceRowInput, ...],
) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for source_row in source_rows:
        if source_row.harvest_business_date == SOURCE_002_JULY_EXCLUSION_DATE:
            continue
        grain_key = build_canonical_grain_key(source_row).canonical_grain_key
        groups.setdefault(grain_key, []).append(_source_row_identity_hash(source_row))
    return {
        grain_key: tuple(sorted(row_hashes))
        for grain_key, row_hashes in groups.items()
        if len(row_hashes) > 1
    }


def assert_no_canonical_grain_collisions_or_fail(
    *,
    source_rows: tuple[SyntheticSourceRowInput, ...],
) -> int:
    conflicts = canonical_grain_collision_groups(source_rows)
    if not conflicts:
        return 0
    conflict_group_row_counts = tuple(
        (grain_key, len(row_hashes)) for grain_key, row_hashes in sorted(conflicts.items())
    )
    for grain_key, row_count in conflict_group_row_counts:
        print(
            f"SOURCE_002_GRAIN_CONFLICT_GROUP grain={grain_key} rows={row_count}",
            flush=True,
        )
    summary = "; ".join(f"{grain_key}={count}" for grain_key, count in conflict_group_row_counts)
    raise CanonicalGrainCollisionBlockedError(
        (
            f"unresolved canonical grain collisions: {len(conflicts)} groups ({summary}); "
            "Lane C winner selection required"
        ),
        conflict_group_count=len(conflicts),
        conflict_group_row_counts=conflict_group_row_counts,
    )


def _resolve_lineage_identity_hashes(
    request: CleaningBuildRequest,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if request.persisted_raw_source_artifact_identity_hashes:
        return (
            tuple(sorted(request.persisted_raw_source_artifact_identity_hashes)),
            tuple(sorted(request.persisted_raw_import_batch_identity_hashes)),
        )
    artifact_hashes = tuple(
        sorted(
            compute_synthetic_raw_source_artifact_identity_hash(artifact.model_dump(mode="python"))
            for artifact in request.raw_source_artifacts
        )
    )
    batch_hashes = tuple(
        sorted(
            compute_synthetic_raw_import_batch_identity_hash(batch.model_dump(mode="python"))
            for batch in request.raw_import_batches
        )
    )
    return artifact_hashes, batch_hashes


def _verify_persisted_lane_a_batch(
    session: Session,
    *,
    batch: RawImportBatchIdentity,
    parsed_identities: tuple[SourceRowIdentity, ...],
) -> None:
    if batch.source_cohort_id != SOURCE_002_COHORT_ID:
        raise Source002CleaningBlockedError("SOURCE_002 batch cohort binding mismatch")
    if len(batch.source_row_identity_hashes) != SOURCE_002_DECLARED_ROW_COUNT:
        raise LaneASourceRowsNotMaterializedError(
            "SOURCE_002 import batch row count does not match the frozen declaration"
        )
    if len(parsed_identities) != SOURCE_002_DECLARED_ROW_COUNT:
        raise LaneASourceRowsNotMaterializedError(
            "SOURCE_002 parsed row identities do not match the frozen declaration"
        )
    persisted_hashes = set(batch.source_row_identity_hashes)
    content_index = fetch_source_row_content_index_for_batch(
        session,
        raw_import_batch_identity_hash=batch.raw_import_batch_identity_hash,
    )
    for identity in parsed_identities:
        if identity.source_row_identity_hash not in persisted_hashes:
            raise LaneASourceRowsNotMaterializedError(
                "SOURCE_002 parsed row identity is not present in the persisted import batch"
            )
        existing_contents = content_index.get(identity.source_row_identity_hash)
        if existing_contents is None or identity.content_sha256 not in existing_contents:
            raise LaneASourceRowsNotMaterializedError(
                "SOURCE_002 row lineage is not materialized in Lane A persistence"
            )


def build_source_002_cleaning_request(
    session: Session,
    *,
    artifact_bytes: bytes,
    batch: RawImportBatchIdentity,
    manual_corrections: tuple[ManualCorrectionRequest, ...] = (),
) -> CleaningBuildRequest:
    from backend.app.s2_materialized_dataset.lane_b.hashes import (
        CLEANED_SCHEMA_VERSION,
        CLEANING_POLICY_VERSION,
        CLEANING_PROJECTION_VERSION,
        CORRECTION_POLICY_VERSION,
        CORRECTION_SCHEMA_VERSION,
        EXCLUSION_POLICY_VERSION,
        EXCLUSION_SCHEMA_VERSION,
        QUALITY_POLICY_VERSION,
        QUALITY_RULE_VERSION,
        QUALITY_SCHEMA_VERSION,
    )

    row_inputs = iter_source_002_row_inputs(
        artifact_bytes,
        source_column_mapping_snapshot_hash=SOURCE_002_MAPPING_SNAPSHOT_HASH,
    )
    artifact_hash = batch.raw_source_artifact_identity_hash
    batch_hash = batch.raw_import_batch_identity_hash
    parsed_identities = tuple(
        build_source_row_identity(
            artifact_identity_hash=artifact_hash,
            batch_identity_hash=batch_hash,
            row_input=row_input,
        )
        for row_input in row_inputs
    )
    _verify_persisted_lane_a_batch(
        session,
        batch=batch,
        parsed_identities=parsed_identities,
    )

    source_rows = tuple(
        source_row_input_from_persisted_lane_a(
            row_input=row_input,
            persisted_identity=identity,
        )
        for row_input, identity in zip(row_inputs, parsed_identities, strict=True)
    )
    july_exclusions = build_july_cohort_exclusions(source_rows=source_rows)
    assert_no_canonical_grain_collisions_or_fail(source_rows=source_rows)
    return CleaningBuildRequest(
        source_cohort_id=SOURCE_002_COHORT_ID,
        persisted_raw_source_artifact_identity_hashes=(artifact_hash,),
        persisted_raw_import_batch_identity_hashes=(batch_hash,),
        source_rows=source_rows,
        mapping_registry_hash=SOURCE_002_MAPPING_SNAPSHOT_HASH,
        cleaning_policy_version=CLEANING_POLICY_VERSION,
        quality_policy_version=QUALITY_POLICY_VERSION,
        correction_policy_version=CORRECTION_POLICY_VERSION,
        exclusion_policy_version=EXCLUSION_POLICY_VERSION,
        cleaned_schema_version=CLEANED_SCHEMA_VERSION,
        cleaning_projection_version=CLEANING_PROJECTION_VERSION,
        quality_schema_version=QUALITY_SCHEMA_VERSION,
        correction_schema_version=CORRECTION_SCHEMA_VERSION,
        exclusion_schema_version=EXCLUSION_SCHEMA_VERSION,
        quality_rule_version=QUALITY_RULE_VERSION,
        manual_corrections=manual_corrections,
        manual_exclusions=july_exclusions,
    )


def _fetch_source_002_controlled_batch(
    session: Session,
    *,
    artifact_identity_hash: str,
) -> RawImportBatchIdentity:
    batch = fetch_import_batch_by_external_identity(
        session,
        raw_source_artifact_identity_hash=artifact_identity_hash,
        source_system=SOURCE_002_SOURCE_SYSTEM,
        external_batch_id=SOURCE_002_CONTROLLED_EXTERNAL_BATCH_ID,
    )
    if batch is None:
        raise LaneASourceRowsNotMaterializedError(
            "SOURCE_002 controlled import batch is not materialized in Lane A"
        )
    return batch


def _emit_source_002_run_report(
    *,
    ingest_first_seen_row_count: int,
    ingest_replay_row_count: int,
    july_excluded_row_count: int,
    canonical_non_excluded_row_count: int,
    grain_conflict_group_count: int,
) -> None:
    report = (
        "SOURCE_002_E3_REPORT "
        f"e2_first_seen={ingest_first_seen_row_count} "
        f"e2_exact_replay={ingest_replay_row_count} "
        f"july_excluded={july_excluded_row_count} "
        f"canonical_non_excluded={canonical_non_excluded_row_count} "
        f"grain_conflict_groups={grain_conflict_group_count}"
    )
    logger.info(report)
    print(report, flush=True)


def _canonical_cleaned_row_count(cleaning: CleaningBuildResult) -> int:
    return sum(1 for row in cleaning.cleaned_rows if not row.is_excluded)


def clean_source_002_from_persisted(
    session: Session,
    *,
    artifact_bytes: bytes,
    artifact_identity_hash: str,
) -> Source002CleaningResult:
    batch = _fetch_source_002_controlled_batch(
        session,
        artifact_identity_hash=artifact_identity_hash,
    )
    request = build_source_002_cleaning_request(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    cleaning = build_cleaned_dataset(request)
    july_count = sum(
        1
        for row in request.source_rows
        if row.harvest_business_date == SOURCE_002_JULY_EXCLUSION_DATE
    )
    grain_conflict_group_count = len(canonical_grain_collision_groups(request.source_rows))
    return Source002CleaningResult(
        ingest_source_row_count=len(request.source_rows),
        ingest_first_seen_row_count=0,
        ingest_replay_row_count=0,
        raw_source_row_count=len(request.source_rows),
        canonical_source_row_count=_canonical_cleaned_row_count(cleaning),
        july_excluded_row_count=july_count,
        grain_conflict_group_count=grain_conflict_group_count,
        cleaning=cleaning,
    )


def controlled_clean_source_002_from_environment(
    session: Session,
    *,
    search_roots: tuple[Path, ...] = (),
    persist: bool = True,
) -> Source002CleaningResult:
    from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
        verify_source_002_frozen_object_identity,
    )
    from backend.app.s2_materialized_dataset.lane_b.persistence import persist_cleaning_build_result

    verification = run_source_002_identity_verification(search_roots=search_roots)
    if verification.status != Source002IdentityVerificationStatus.PASS:
        raise Source002CleaningBlockedError(
            "SOURCE_002 E3 cleaning requires a passing E1 identity verification"
        )
    _, artifact_bytes, _ = verify_source_002_frozen_object_identity(search_roots=search_roots)
    if artifact_bytes is None:
        raise Source002CleaningBlockedError(
            "SOURCE_002 E3 cleaning requires verified immutable artifact bytes"
        )

    ingest_result = controlled_ingest_source_002_from_environment(
        session,
        search_roots=search_roots,
    )
    batch = ingest_result.batch_registration.identity
    try:
        request = build_source_002_cleaning_request(
            session,
            artifact_bytes=artifact_bytes,
            batch=batch,
        )
    except CanonicalGrainCollisionBlockedError as exc:
        _emit_source_002_run_report(
            ingest_first_seen_row_count=ingest_result.first_seen_row_count,
            ingest_replay_row_count=ingest_result.replay_row_count,
            july_excluded_row_count=SOURCE_002_JULY_COHORT_EXCLUDED_ROW_COUNT,
            canonical_non_excluded_row_count=0,
            grain_conflict_group_count=exc.conflict_group_count,
        )
        raise
    cleaning = build_cleaned_dataset(request)
    if persist:
        persist_cleaning_build_result(session, cleaning)
    july_count = sum(
        1
        for row in request.source_rows
        if row.harvest_business_date == SOURCE_002_JULY_EXCLUSION_DATE
    )
    grain_conflict_group_count = len(canonical_grain_collision_groups(request.source_rows))
    canonical_non_excluded = _canonical_cleaned_row_count(cleaning)
    _emit_source_002_run_report(
        ingest_first_seen_row_count=ingest_result.first_seen_row_count,
        ingest_replay_row_count=ingest_result.replay_row_count,
        july_excluded_row_count=july_count,
        canonical_non_excluded_row_count=canonical_non_excluded,
        grain_conflict_group_count=grain_conflict_group_count,
    )
    return Source002CleaningResult(
        ingest_source_row_count=ingest_result.source_row_count,
        ingest_first_seen_row_count=ingest_result.first_seen_row_count,
        ingest_replay_row_count=ingest_result.replay_row_count,
        raw_source_row_count=len(request.source_rows),
        canonical_source_row_count=canonical_non_excluded,
        july_excluded_row_count=july_count,
        grain_conflict_group_count=grain_conflict_group_count,
        cleaning=cleaning,
    )


def _prepare_rows(request: CleaningBuildRequest) -> tuple[PreparedCleaningRow, ...]:
    prepared: list[PreparedCleaningRow] = []
    for source_row in request.source_rows:
        grain = build_canonical_grain_key(source_row)
        prepared.append(
            PreparedCleaningRow(
                source_row_identity_hash=_source_row_identity_hash(source_row),
                canonical_grain_key_payload=compute_canonical_grain_key_payload(
                    season_business_key=grain.season_business_key,
                    farm_business_key=grain.farm_business_key,
                    subfarm_business_key=grain.subfarm_business_key,
                    variety_business_key=grain.variety_business_key,
                    harvest_business_date=grain.harvest_business_date,
                ),
                source_row=source_row,
                quantity_presence_status=resolve_quantity_presence(source_row),
            )
        )
    return tuple(sorted(prepared, key=lambda item: item.source_row_identity_hash))


def _grain_key_text(grain: CanonicalGrainKey) -> str:
    return grain.canonical_grain_key


def _build_cleaned_row_record(
    *,
    prepared: PreparedCleaningRow,
    request: CleaningBuildRequest,
    version_identity_hash: str,
    exclusion_entries: tuple[ExclusionLedgerEntryRecord, ...],
    correction_entries: tuple[CorrectionLedgerEntryRecord, ...],
    quality_finding_hashes: tuple[str, ...],
) -> CleanedRowRecord:
    grain = build_canonical_grain_key(prepared.source_row)
    excluded = is_row_excluded(
        source_row_identity_hash=prepared.source_row_identity_hash,
        entries=exclusion_entries,
    )
    source_quantity = prepared.source_row.actual_harvest_quantity_kg
    effective_quantity = effective_quantity_after_corrections(
        source_row_identity_hash=prepared.source_row_identity_hash,
        source_quantity=source_quantity,
        manual_corrections=request.manual_corrections,
    )
    if excluded:
        effective_quantity = None

    correction_hashes = correction_identities_for_row(
        correction_entries,
        source_row_identity_hash=prepared.source_row_identity_hash,
    )
    exclusion_hashes = exclusion_identities_for_row(
        exclusion_entries,
        source_row_identity_hash=prepared.source_row_identity_hash,
    )

    content_hash = compute_cleaned_row_content_hash(
        source_row_identity_hash=prepared.source_row_identity_hash,
        canonical_grain_key=prepared.canonical_grain_key_payload,
        cleaning_projection_version=request.cleaning_projection_version,
        cleaned_row_schema_version=request.cleaned_schema_version,
        cleaning_policy_version=request.cleaning_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        source_actual_harvest_quantity_kg=source_quantity,
        effective_actual_harvest_quantity_kg=effective_quantity,
        quantity_presence_status=prepared.quantity_presence_status.value,
        is_excluded=excluded,
        quality_finding_identity_hashes=quality_finding_hashes,
        correction_ledger_entry_identity_hashes=correction_hashes,
        exclusion_ledger_entry_identity_hashes=exclusion_hashes,
    )
    row_identity_hash = compute_cleaned_row_identity_hash(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        source_row_identity_hash=prepared.source_row_identity_hash,
        canonical_grain_key=prepared.canonical_grain_key_payload,
        cleaning_projection_version=request.cleaning_projection_version,
        cleaned_row_schema_version=request.cleaned_schema_version,
        cleaning_policy_version=request.cleaning_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        cleaned_row_content_hash=content_hash,
    )
    return CleanedRowRecord(
        cleaned_row_identity_hash=row_identity_hash,
        cleaned_row_content_hash=content_hash,
        cleaned_dataset_version_identity_hash=version_identity_hash,
        source_row_identity_hash=prepared.source_row_identity_hash,
        canonical_grain_key=grain,
        cleaning_projection_version=request.cleaning_projection_version,
        cleaned_row_schema_version=request.cleaned_schema_version,
        cleaning_policy_version=request.cleaning_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        source_actual_harvest_quantity_kg=source_quantity,
        effective_actual_harvest_quantity_kg=effective_quantity,
        quantity_presence_status=prepared.quantity_presence_status,
        is_excluded=excluded,
        quality_finding_identity_hashes=quality_finding_hashes,
        correction_ledger_entry_identity_hashes=correction_hashes,
        exclusion_ledger_entry_identity_hashes=exclusion_hashes,
    )


def build_cleaned_dataset(request: CleaningBuildRequest) -> CleaningBuildResult:
    artifact_hashes, batch_hashes = _resolve_lineage_identity_hashes(request)
    prepared_rows = _prepare_rows(request)
    source_row_hashes = tuple(item.source_row_identity_hash for item in prepared_rows)
    duplicate_groups = duplicate_grain_groups(prepared_rows)

    version_identity_hash = compute_cleaned_dataset_version_identity_hash(
        source_cohort_id=request.source_cohort_id,
        raw_import_batch_identity_hashes=batch_hashes,
        cleaning_policy_version=request.cleaning_policy_version,
        quality_policy_version=request.quality_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        mapping_registry_hash=request.mapping_registry_hash,
        cleaned_schema_version=request.cleaned_schema_version,
    )

    source_values_by_row = {
        prepared.source_row_identity_hash: prepared.source_row.actual_harvest_quantity_kg
        for prepared in prepared_rows
    }
    correction_entries = build_correction_ledger_entries(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        correction_policy_version=request.correction_policy_version,
        correction_schema_version=request.correction_schema_version,
        source_values_by_row=source_values_by_row,
        manual_corrections=request.manual_corrections,
    )
    exclusion_entries = build_exclusion_ledger_entries(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        exclusion_policy_version=request.exclusion_policy_version,
        exclusion_schema_version=request.exclusion_schema_version,
        manual_exclusions=request.manual_exclusions,
    )

    assert_duplicate_grains_resolved_or_fail(
        duplicate_groups=duplicate_groups,
        exclusion_entries=exclusion_entries,
    )

    publishable_rows = tuple(
        prepared
        for prepared in prepared_rows
        if should_publish_cleaned_row(
            source_row_identity_hash=prepared.source_row_identity_hash,
            grain_key=_grain_key_text(build_canonical_grain_key(prepared.source_row)),
            duplicate_groups=duplicate_groups,
            exclusion_entries=exclusion_entries,
        )
    )

    draft_rows = tuple(
        _build_cleaned_row_record(
            prepared=prepared,
            request=request,
            version_identity_hash=version_identity_hash,
            exclusion_entries=exclusion_entries,
            correction_entries=correction_entries,
            quality_finding_hashes=(),
        )
        for prepared in publishable_rows
    )
    cleaned_row_identity_by_source = {
        row.source_row_identity_hash: row.cleaned_row_identity_hash for row in draft_rows
    }

    quality_findings = evaluate_quality_findings(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        quality_policy_version=request.quality_policy_version,
        quality_schema_version=request.quality_schema_version,
        prepared_rows=prepared_rows,
        cleaned_row_identity_by_source=cleaned_row_identity_by_source,
        duplicate_groups=duplicate_groups,
        exclusion_entries=exclusion_entries,
    )

    cleaned_rows_tuple = tuple(
        sorted(
            (
                _build_cleaned_row_record(
                    prepared=prepared,
                    request=request,
                    version_identity_hash=version_identity_hash,
                    exclusion_entries=exclusion_entries,
                    correction_entries=correction_entries,
                    quality_finding_hashes=findings_for_source_row(
                        quality_findings,
                        source_row_identity_hash=prepared.source_row_identity_hash,
                    ),
                )
                for prepared in publishable_rows
            ),
            key=lambda item: item.cleaned_row_identity_hash,
        )
    )

    final_cleaned_row_identity_by_source = {
        row.source_row_identity_hash: row.cleaned_row_identity_hash for row in cleaned_rows_tuple
    }
    quality_findings = tuple(
        sorted(
            (
                finding.model_copy(
                    update={
                        "cleaned_row_identity_hash": final_cleaned_row_identity_by_source.get(
                            finding.source_row_identity_hash
                        )
                    }
                )
                for finding in quality_findings
            ),
            key=lambda item: item.quality_finding_identity_hash,
        )
    )

    quality_report_identity_hash = compute_quality_report_identity_hash(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        quality_policy_version=request.quality_policy_version,
        finding_identity_hashes=(
            finding.quality_finding_identity_hash for finding in quality_findings
        ),
    )

    content_hash = compute_cleaned_dataset_version_content_hash(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        raw_source_artifact_identity_hashes=artifact_hashes,
        raw_import_batch_identity_hashes=batch_hashes,
        source_row_identity_hashes=source_row_hashes,
        quality_report_identity_hash=quality_report_identity_hash,
        correction_ledger_identity_hashes=(
            entry.correction_ledger_entry_identity_hash for entry in correction_entries
        ),
        exclusion_ledger_identity_hashes=(
            entry.exclusion_ledger_entry_identity_hash for entry in exclusion_entries
        ),
        cleaned_row_content_hashes=(row.cleaned_row_content_hash for row in cleaned_rows_tuple),
    )

    version = CleanedDatasetVersionRecord(
        cleaned_dataset_version_identity_hash=version_identity_hash,
        cleaned_dataset_version_content_hash=content_hash,
        source_cohort_id=request.source_cohort_id,
        mapping_registry_hash=request.mapping_registry_hash,
        cleaning_policy_version=request.cleaning_policy_version,
        quality_policy_version=request.quality_policy_version,
        correction_policy_version=request.correction_policy_version,
        exclusion_policy_version=request.exclusion_policy_version,
        cleaned_schema_version=request.cleaned_schema_version,
        raw_source_artifact_identity_hashes=artifact_hashes,
        raw_import_batch_identity_hashes=batch_hashes,
        source_row_identity_hashes=source_row_hashes,
        quality_report_identity_hash=quality_report_identity_hash,
        correction_ledger_identity_hashes=tuple(
            entry.correction_ledger_entry_identity_hash for entry in correction_entries
        ),
        exclusion_ledger_identity_hashes=tuple(
            entry.exclusion_ledger_entry_identity_hash for entry in exclusion_entries
        ),
        cleaned_row_identity_hashes=tuple(
            row.cleaned_row_identity_hash for row in cleaned_rows_tuple
        ),
        cleaned_row_content_hashes=tuple(
            row.cleaned_row_content_hash for row in cleaned_rows_tuple
        ),
        row_count=len(cleaned_rows_tuple),
        excluded_row_count=sum(1 for row in cleaned_rows_tuple if row.is_excluded),
        unknown_quantity_row_count=sum(
            1
            for row in cleaned_rows_tuple
            if row.quantity_presence_status == QuantityPresenceStatus.UNKNOWN_NOT_ZERO
        ),
    )

    return CleaningBuildResult(
        version=version,
        cleaned_rows=cleaned_rows_tuple,
        quality_findings=quality_findings,
        correction_ledger_entries=correction_entries,
        exclusion_ledger_entries=exclusion_entries,
    )


def assert_replay_parity(left: CleaningBuildResult, right: CleaningBuildResult) -> None:
    if left.version != right.version:
        raise CleanedDatasetVersionConflictError(
            "same inputs must reproduce identical cleaned dataset version hashes"
        )
    if left.cleaned_rows != right.cleaned_rows:
        raise CleanedDatasetVersionConflictError("cleaned row replay mismatch")
    if left.quality_findings != right.quality_findings:
        raise CleanedDatasetVersionConflictError("quality finding replay mismatch")
    if left.correction_ledger_entries != right.correction_ledger_entries:
        raise CleanedDatasetVersionConflictError("correction ledger replay mismatch")
    if left.exclusion_ledger_entries != right.exclusion_ledger_entries:
        raise CleanedDatasetVersionConflictError("exclusion ledger replay mismatch")
