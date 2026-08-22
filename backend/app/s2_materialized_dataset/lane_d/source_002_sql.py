"""SOURCE_002 controlled SQL materialization for Lane D (E5)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SOURCE_002_COHORT_ID,
    SOURCE_002_DECLARED_ROW_COUNT,
    SOURCE_002_IMPORT_POLICY_VERSION,
    RawImportBatchIdentity,
)
from backend.app.s2_materialized_dataset.lane_b.cleaning import (
    SOURCE_002_JULY_EXCLUSION_DATE,
    build_canonical_grain_key,
    build_source_002_cleaning_request,
    reconcile_source_002_kg_sums_or_fail,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import (
    CORRECTION_POLICY_VERSION,
    EXCLUSION_POLICY_VERSION,
    compute_collapsed_grain_source_row_identity_hash,
    digest,
)
from backend.app.s2_materialized_dataset.lane_b.persistence import (
    S2CleanedDatasetVersionModel,
    S2CleanedRowModel,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    SOURCE_002_CLEANING_POLICY_VERSION,
    QuantityPresenceStatus,
)
from backend.app.s2_materialized_dataset.lane_c.persistence import (
    S2IdflLabelSideWinnerDecisionModel,
    S2PitVisibilityDecisionModel,
    count_idfl_label_side_winner_sql_rows,
    count_revision_winner_sql_rows,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    VISIBILITY_BOUNDARY,
    IdflLabelSideContext,
)
from backend.app.s2_materialized_dataset.lane_d.builder import BuildTimestamps, rows_for_partition
from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS
from backend.app.s2_materialized_dataset.lane_d.service import (
    StoredUpstreamBundle,
    StoredUpstreamLaneA,
    StoredUpstreamLaneB,
    StoredUpstreamLaneC,
    persist_materialized_dataset,
    verify_storage_rebuild_parity,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED,
    SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    SOURCE_COHORT_ID,
    SOURCE_COHORT_MANIFEST_SHA256,
    MaterializableRow,
    PartitionName,
)

logger = logging.getLogger(__name__)

IDFL_PIT_VISIBILITY_NOT_APPLICABLE_POLICY_VERSION = "v0-3-s2-idfl-pit-visibility-not-applicable-v1"


class Source002E5MaterializationError(Exception):
    """Raised when SOURCE_002 controlled SQL materialization cannot proceed."""


@dataclass(frozen=True, slots=True)
class Source002SqlBoundaryCounts:
    idfl_sql: int
    non_excluded_grains: int
    kg_equal: bool
    pit_sql: int
    old_winner_sql: int


@dataclass(frozen=True, slots=True)
class Source002E5Report:
    e2: int
    e3_grains: int
    e3_kg_equal: bool
    idfl_sql: int
    pit_sql: int
    old_winner_sql: int
    train_rows: int
    val_rows: int
    test_rows: int
    dataset_identity: str | None
    rebuild_parity: str

    def format_line(self) -> str:
        identity = self.dataset_identity or "OBJECT_MISSING"
        return (
            "SOURCE_002_E5_REPORT "
            f"e2={self.e2} "
            f"e3_grains={self.e3_grains} "
            f"e3_kg_equal={'true' if self.e3_kg_equal else 'false'} "
            f"idfl_sql={self.idfl_sql} "
            f"pit_sql={self.pit_sql} "
            f"old_winner_sql={self.old_winner_sql} "
            f"train_rows={self.train_rows} "
            f"val_rows={self.val_rows} "
            f"test_rows={self.test_rows} "
            f"dataset_identity={identity} "
            f"rebuild_parity={self.rebuild_parity}"
        )


def count_pit_visibility_sql_rows(session: Session) -> int:
    return int(
        session.scalar(sa.select(func.count()).select_from(S2PitVisibilityDecisionModel)) or 0
    )


def count_non_excluded_cleaned_grain_sql_rows(session: Session) -> int:
    version = _fetch_latest_source_002_cleaned_version(session)
    return int(
        session.scalar(
            select(func.count())
            .select_from(S2CleanedRowModel)
            .where(
                S2CleanedRowModel.cleaned_dataset_version_id == version.id,
                S2CleanedRowModel.is_excluded.is_(False),
            )
        )
        or 0
    )


def compute_idfl_pit_visibility_not_applicable_identity() -> str:
    """Deterministic NOT_APPLICABLE digest from the frozen IDFL visibility boundary."""
    return sha256_payload(
        {
            "policy_version": IDFL_PIT_VISIBILITY_NOT_APPLICABLE_POLICY_VERSION,
            "visibility_boundary": VISIBILITY_BOUNDARY,
            "visibility_boundary_constant": VISIBILITY_BOUNDARY,
            "pit_status": "NOT_APPLICABLE_NOT_PERSISTED",
        }
    )


def compute_grain_revision_winner_identity(
    contributor_idfl_content_sha256: tuple[str, ...] | list[str],
) -> str:
    """Deterministic grain-level revision winner digest from sorted IDFL content hashes."""
    sorted_hashes = tuple(sorted(contributor_idfl_content_sha256))
    if len(sorted_hashes) == 1:
        return sorted_hashes[0]
    return digest({"contributor_idfl_content_sha256": sorted_hashes})


def _row_sort_key(row: MaterializableRow) -> tuple[str, str, str, str, str]:
    return (
        row.season,
        row.farm,
        row.subfarm,
        row.variety,
        row.harvest_business_date.isoformat(),
    )


def _fetch_latest_source_002_cleaned_version(session: Session) -> S2CleanedDatasetVersionModel:
    version = session.scalar(
        select(S2CleanedDatasetVersionModel)
        .where(S2CleanedDatasetVersionModel.source_cohort_id == SOURCE_002_COHORT_ID)
        .order_by(S2CleanedDatasetVersionModel.created_at.desc())
        .limit(1)
    )
    if version is None:
        raise Source002E5MaterializationError(
            "SOURCE_002 cleaned dataset version is not materialized in SQL"
        )
    return version


def _verify_kg_equal_from_sql_and_replay(
    session: Session,
    *,
    artifact_bytes: bytes,
    batch: RawImportBatchIdentity,
) -> bool:
    from backend.app.s2_materialized_dataset.lane_b.cleaning import build_cleaned_dataset
    from backend.app.s2_materialized_dataset.lane_b.schemas import Source002GrainKgSumBlockedError

    request, _ = build_source_002_cleaning_request(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    cleaning = build_cleaned_dataset(request)
    try:
        reconcile_source_002_kg_sums_or_fail(
            source_rows=request.source_rows,
            cleaning=cleaning,
        )
    except Source002GrainKgSumBlockedError:
        return False
    return True


def verify_source_002_sql_boundaries(
    session: Session,
    *,
    artifact_bytes: bytes,
    batch: RawImportBatchIdentity,
) -> Source002SqlBoundaryCounts:
    """Fail-closed boundary oracle for SOURCE_002 E5 SQL consumption."""
    if not SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED:
        raise Source002E5MaterializationError(
            "SOURCE_002 controlled SQL materialization is not enabled"
        )

    idfl_sql = count_idfl_label_side_winner_sql_rows(session)
    pit_sql = count_pit_visibility_sql_rows(session)
    old_winner_sql = count_revision_winner_sql_rows(session)
    non_excluded_grains = count_non_excluded_cleaned_grain_sql_rows(session)
    kg_equal = _verify_kg_equal_from_sql_and_replay(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )

    counts = Source002SqlBoundaryCounts(
        idfl_sql=idfl_sql,
        non_excluded_grains=non_excluded_grains,
        kg_equal=kg_equal,
        pit_sql=pit_sql,
        old_winner_sql=old_winner_sql,
    )
    if idfl_sql != SOURCE_002_DECLARED_ROW_COUNT:
        raise Source002E5MaterializationError(
            f"IDFL SQL count mismatch: expected {SOURCE_002_DECLARED_ROW_COUNT}, got {idfl_sql}"
        )
    if non_excluded_grains != SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT:
        raise Source002E5MaterializationError(
            "non-excluded grain count mismatch: "
            f"expected {SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT}, got {non_excluded_grains}"
        )
    if not kg_equal:
        raise Source002E5MaterializationError("B kg_equal is not true")
    if pit_sql != 0:
        raise Source002E5MaterializationError(f"PIT SQL must be 0 for SOURCE_002 E5, got {pit_sql}")
    if old_winner_sql != 0:
        raise Source002E5MaterializationError(
            f"old revision winner SQL must be 0 for SOURCE_002 E5, got {old_winner_sql}"
        )
    return counts


def _build_collapsed_grain_contributor_index(
    session: Session,
    *,
    artifact_bytes: bytes,
    batch: RawImportBatchIdentity,
) -> dict[str, tuple[str, ...]]:
    request, _ = build_source_002_cleaning_request(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    groups: dict[str, list[str]] = {}
    for source_row in request.source_rows:
        if source_row.harvest_business_date == SOURCE_002_JULY_EXCLUSION_DATE:
            continue
        contributor_hash = source_row.persisted_source_row_identity_hash
        if contributor_hash is None:
            raise Source002E5MaterializationError(
                "Lane A replay row is missing persisted source_row_identity_hash"
            )
        grain_key = build_canonical_grain_key(source_row).canonical_grain_key
        groups.setdefault(grain_key, []).append(contributor_hash)

    index: dict[str, tuple[str, ...]] = {}
    for contributor_hashes in groups.values():
        sorted_hashes = tuple(sorted(contributor_hashes))
        collapsed = compute_collapsed_grain_source_row_identity_hash(sorted_hashes)
        index[collapsed] = sorted_hashes
    return index


def load_source_002_materializable_rows_from_sql(
    session: Session,
    *,
    artifact_bytes: bytes,
    batch: RawImportBatchIdentity,
) -> tuple[MaterializableRow, ...]:
    """Build materializable rows by joining A lineage replay, B cleaned SQL, and C IDFL SQL."""
    verify_source_002_sql_boundaries(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    version = _fetch_latest_source_002_cleaned_version(session)
    cleaned_rows = session.scalars(
        select(S2CleanedRowModel)
        .where(
            S2CleanedRowModel.cleaned_dataset_version_id == version.id,
            S2CleanedRowModel.is_excluded.is_(False),
        )
        .order_by(
            S2CleanedRowModel.season_business_key,
            S2CleanedRowModel.farm_business_key,
            S2CleanedRowModel.subfarm_business_key,
            S2CleanedRowModel.variety_business_key,
            S2CleanedRowModel.harvest_business_date,
        )
    ).all()

    idfl_by_identity = {
        row.source_row_identity_hash: row.content_sha256
        for row in session.scalars(select(S2IdflLabelSideWinnerDecisionModel)).all()
    }
    grain_index = _build_collapsed_grain_contributor_index(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    pit_identity = compute_idfl_pit_visibility_not_applicable_identity()

    materializable: list[MaterializableRow] = []
    for cleaned in cleaned_rows:
        if cleaned.quantity_presence_status == QuantityPresenceStatus.UNKNOWN_NOT_ZERO.value:
            raise Source002E5MaterializationError(
                "UNKNOWN_NOT_ZERO cleaned grain must not enter MaterializableRow"
            )
        effective = cleaned.effective_actual_harvest_quantity_kg
        if effective is None:
            raise Source002E5MaterializationError(
                "non-excluded cleaned grain is missing effective kilogram quantity"
            )

        collapsed_hash = cleaned.source_row_identity_hash
        contributors = grain_index.get(collapsed_hash)
        if contributors is None:
            raise Source002E5MaterializationError(
                f"grain contributor mapping missing for cleaned identity {collapsed_hash}"
            )

        idfl_hashes: list[str] = []
        for contributor in contributors:
            idfl_hash = idfl_by_identity.get(contributor)
            if idfl_hash is None:
                raise Source002E5MaterializationError(
                    f"IDFL SQL row missing for contributor {contributor}"
                )
            idfl_hashes.append(idfl_hash)

        materializable.append(
            MaterializableRow(
                season=cleaned.season_business_key,
                farm=cleaned.farm_business_key,
                subfarm=cleaned.subfarm_business_key,
                variety=cleaned.variety_business_key,
                harvest_business_date=cleaned.harvest_business_date,
                actual_harvest_quantity_kg=effective,
                source_row_identity=collapsed_hash,
                cleaned_row_identity=cleaned.cleaned_row_identity_hash,
                pit_visibility_identity=pit_identity,
                revision_winner_identity=compute_grain_revision_winner_identity(idfl_hashes),
            )
        )

    return tuple(sorted(materializable, key=_row_sort_key))


def build_source_002_upstream_bundle_from_sql(
    session: Session,
    *,
    artifact_bytes: bytes,
    batch: RawImportBatchIdentity,
) -> StoredUpstreamBundle:
    rows = load_source_002_materializable_rows_from_sql(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    version = _fetch_latest_source_002_cleaned_version(session)
    label_context = IdflLabelSideContext()
    return StoredUpstreamBundle(
        lane_a=StoredUpstreamLaneA(
            source_cohort_id=SOURCE_COHORT_ID,
            source_cohort_manifest_sha256=SOURCE_COHORT_MANIFEST_SHA256,
            raw_policy_version=SOURCE_002_IMPORT_POLICY_VERSION,
        ),
        lane_b=StoredUpstreamLaneB(
            cleaned_dataset_version_identity=version.cleaned_dataset_version_identity_hash,
            cleaning_policy_version=SOURCE_002_CLEANING_POLICY_VERSION,
            correction_policy_version=CORRECTION_POLICY_VERSION,
            exclusion_policy_version=EXCLUSION_POLICY_VERSION,
            rows=rows,
        ),
        lane_c=StoredUpstreamLaneC(
            visibility_policy_version=label_context.visibility_policy_version,
            revision_winner_policy_version=label_context.revision_winner_policy_version,
        ),
    )


def _partition_row_counts(
    rows: tuple[MaterializableRow, ...],
) -> tuple[int, int, int]:
    train = validation = test = 0
    for partition in FROZEN_PARTITIONS:
        selected = rows_for_partition(rows, partition)
        if partition.name is PartitionName.TRAIN:
            train = len(selected)
        elif partition.name is PartitionName.VALIDATION:
            validation = len(selected)
        elif partition.name is PartitionName.TEST:
            test = len(selected)
    return train, validation, test


def _fetch_source_002_controlled_batch_from_sql(session: Session) -> RawImportBatchIdentity:
    from backend.app.s2_materialized_dataset.lane_a.persistence import (
        S2RawImportBatchModel,
        fetch_import_batch_by_identity_hash,
    )
    from backend.app.s2_materialized_dataset.lane_a.schemas import (
        SOURCE_002_CONTROLLED_EXTERNAL_BATCH_ID,
    )

    batch_model = session.scalar(
        select(S2RawImportBatchModel).where(
            S2RawImportBatchModel.external_batch_id == SOURCE_002_CONTROLLED_EXTERNAL_BATCH_ID
        )
    )
    if batch_model is None:
        raise Source002E5MaterializationError(
            "SOURCE_002 controlled import batch is not materialized in SQL"
        )
    batch = fetch_import_batch_by_identity_hash(
        session,
        raw_import_batch_identity_hash=batch_model.raw_import_batch_identity_hash,
    )
    if batch is None:
        raise Source002E5MaterializationError(
            "SOURCE_002 controlled import batch identity is not resolvable from SQL"
        )
    return batch


def _default_source_002_e5_search_roots() -> tuple[Path, ...]:
    workspace_root = Path(__file__).resolve().parents[4]
    return (
        Path("/tmp"),
        Path("/tmp/source-002-custody"),
        workspace_root,
    )


def _resolve_source_002_e5_search_roots(
    search_roots: tuple[Path, ...],
) -> tuple[Path, ...]:
    if search_roots:
        return search_roots
    return _default_source_002_e5_search_roots()


def _source_002_frozen_object_available(search_roots: tuple[Path, ...]) -> bool:
    from backend.app.s2_materialized_dataset.lane_a.schemas import (
        Source002IdentityVerificationStatus,
    )
    from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
        verify_source_002_frozen_object_identity,
    )

    record, artifact_bytes, _ = verify_source_002_frozen_object_identity(search_roots=search_roots)
    return record.status == Source002IdentityVerificationStatus.PASS and artifact_bytes is not None


def controlled_materialize_source_002_from_environment(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
    search_roots: tuple[Path, ...] = (),
    persist: bool = True,
    timestamps: BuildTimestamps | None = None,
) -> Source002E5Report:
    """Warm A/B/C controlled SQL tables and materialize SOURCE_002 for Lane D."""
    if not SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED:
        raise Source002E5MaterializationError(
            "SOURCE_002 controlled SQL materialization is not enabled"
        )

    resolved_roots = _resolve_source_002_e5_search_roots(search_roots)
    if not _source_002_frozen_object_available(resolved_roots):
        print("OBJECT_MISSING", flush=True)
        return Source002E5Report(
            e2=SOURCE_002_DECLARED_ROW_COUNT,
            e3_grains=SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
            e3_kg_equal=False,
            idfl_sql=0,
            pit_sql=0,
            old_winner_sql=0,
            train_rows=0,
            val_rows=0,
            test_rows=0,
            dataset_identity=None,
            rebuild_parity="OBJECT_MISSING",
        )

    from backend.app.s2_materialized_dataset.lane_a.source_artifact import (
        verify_source_002_frozen_object_identity,
    )
    from backend.app.s2_materialized_dataset.lane_c.persistence import (
        controlled_persist_source_002_idfl_from_environment,
    )

    _, artifact_bytes, _ = verify_source_002_frozen_object_identity(search_roots=resolved_roots)
    if artifact_bytes is None:
        raise Source002E5MaterializationError("SOURCE_002 frozen artifact bytes are unavailable")

    controlled_persist_source_002_idfl_from_environment(
        session,
        search_roots=resolved_roots,
        persist=persist,
    )

    batch = _fetch_source_002_controlled_batch_from_sql(session)
    boundary = verify_source_002_sql_boundaries(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    upstream = build_source_002_upstream_bundle_from_sql(
        session,
        artifact_bytes=artifact_bytes,
        batch=batch,
    )
    train_rows, val_rows, test_rows = _partition_row_counts(upstream.lane_b.rows)

    dataset_identity: str | None = None
    rebuild_parity = "NOT_RUN"
    if persist:
        built = persist_materialized_dataset(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            upstream=upstream,
            timestamps=timestamps,
        )
        dataset_identity = built.materialized_dataset_identity_sha256
        try:
            verify_storage_rebuild_parity(
                session,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
            )
            rebuild_parity = "PASS"
        except Exception:
            rebuild_parity = "FAIL"

    report = Source002E5Report(
        e2=SOURCE_002_DECLARED_ROW_COUNT,
        e3_grains=boundary.non_excluded_grains,
        e3_kg_equal=boundary.kg_equal,
        idfl_sql=boundary.idfl_sql,
        pit_sql=boundary.pit_sql,
        old_winner_sql=boundary.old_winner_sql,
        train_rows=train_rows,
        val_rows=val_rows,
        test_rows=test_rows,
        dataset_identity=dataset_identity,
        rebuild_parity=rebuild_parity,
    )
    line = report.format_line()
    logger.info(line)
    print(line, flush=True)
    return report


__all__ = [
    "Source002E5MaterializationError",
    "Source002E5Report",
    "Source002SqlBoundaryCounts",
    "build_source_002_upstream_bundle_from_sql",
    "compute_grain_revision_winner_identity",
    "compute_idfl_pit_visibility_not_applicable_identity",
    "controlled_materialize_source_002_from_environment",
    "count_non_excluded_cleaned_grain_sql_rows",
    "count_pit_visibility_sql_rows",
    "load_source_002_materializable_rows_from_sql",
    "verify_source_002_sql_boundaries",
]
