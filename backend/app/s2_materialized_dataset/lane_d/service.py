"""Lane D materialized dataset persistence, load, and storage-backed rebuild."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from backend.app.db.base import Base
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
from backend.app.s2_materialized_dataset.lane_d.builder import (
    BuildTimestamps,
    MaterializedDatasetBuildError,
    build_materialized_dataset,
    materialize_partition_bytes,
    rows_for_partition,
)
from backend.app.s2_materialized_dataset.lane_d.manifest import (
    recompute_manifest_sha256_from_published,
)
from backend.app.s2_materialized_dataset.lane_d.partitions import FROZEN_PARTITIONS
from backend.app.s2_materialized_dataset.lane_d.schemas import (
    MaterializedDatasetResult,
    PartitionManifest,
)
from backend.app.s2_materialized_dataset.shared.contracts import (
    BUILDER_VERSION,
    DATASET_SCHEMA_VERSION,
    PARTITION_DATE_FIELD,
    SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED,
    SOURCE_002_EXPECTED_NON_EXCLUDED_GRAIN_COUNT,
    SOURCE_COHORT_ID,
    SOURCE_COHORT_MANIFEST_SHA256,
    MaterializableRow,
    PartitionName,
    QualityGateStatus,
    RebuildHashReplayStatus,
    UpstreamBundlePort,
)

logger = logging.getLogger(__name__)

IDFL_PIT_VISIBILITY_NOT_APPLICABLE_POLICY_VERSION = "v0-3-s2-idfl-pit-visibility-not-applicable-v1"


class MaterializedDatasetConflictError(Exception):
    """Raised when a dataset version identity conflicts with stored facts."""


class MaterializedDatasetStorageRebuildError(Exception):
    """Raised when storage-backed rebuild does not match persisted hashes."""


def _sqlite_bigint() -> Any:
    return BigInteger().with_variant(Integer(), "sqlite")


def _sha_check(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    return f"length({column}) = 64 AND lower({column}) = {column} AND length({expression}) = 0"


class S2MaterializedDatasetModel(Base):
    __tablename__ = "s2_materialized_dataset"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    materialized_dataset_identity_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_cohort_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_cohort_manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    raw_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    cleaning_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    correction_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    exclusion_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    revision_winner_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_dataset_version_identity: Mapped[str] = mapped_column(Text, nullable=False)
    builder_version: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    lineage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_gate_status: Mapped[str] = mapped_column(Text, nullable=False)
    build_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    build_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    upstream_snapshot_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    materializable_rows: Mapped[list[S2MaterializedMaterializableRowModel]] = relationship(
        back_populates="dataset",
        order_by="S2MaterializedMaterializableRowModel.row_sort_key",
    )
    partitions: Mapped[list[S2MaterializedPartitionModel]] = relationship(
        back_populates="dataset",
        order_by="S2MaterializedPartitionModel.partition_name",
    )

    __table_args__ = (
        UniqueConstraint(
            "materialized_dataset_identity_sha256",
            name="uq_s2_materialized_dataset_identity",
        ),
        UniqueConstraint(
            "dataset_id", "dataset_version", name="uq_s2_materialized_dataset_version"
        ),
        CheckConstraint(
            _sha_check("materialized_dataset_identity_sha256"),
            name="ck_s2_materialized_dataset_identity",
        ),
    )


class S2MaterializedMaterializableRowModel(Base):
    __tablename__ = "s2_materialized_materializable_row"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    materialized_dataset_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_materialized_dataset.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_sort_key: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    farm: Mapped[str] = mapped_column(Text, nullable=False)
    subfarm: Mapped[str] = mapped_column(Text, nullable=False)
    variety: Mapped[str] = mapped_column(Text, nullable=False)
    harvest_business_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_harvest_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_row_identity: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_row_identity: Mapped[str] = mapped_column(Text, nullable=False)
    pit_visibility_identity: Mapped[str] = mapped_column(Text, nullable=False)
    revision_winner_identity: Mapped[str] = mapped_column(Text, nullable=False)
    dataset: Mapped[S2MaterializedDatasetModel] = relationship(back_populates="materializable_rows")


class S2MaterializedPartitionModel(Base):
    __tablename__ = "s2_materialized_partition"

    id: Mapped[int] = mapped_column(_sqlite_bigint(), primary_key=True, autoincrement=True)
    materialized_dataset_id: Mapped[int] = mapped_column(
        _sqlite_bigint(),
        ForeignKey("s2_materialized_dataset.id", ondelete="RESTRICT"),
        nullable=False,
    )
    partition_name: Mapped[str] = mapped_column(Text, nullable=False)
    partition_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    partition_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    partition_date_field: Mapped[str] = mapped_column(Text, nullable=False)
    target_decision: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_grain: Mapped[str] = mapped_column(Text, nullable=False)
    split_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    materialized_partition_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    partition_identity_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    content_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    lineage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_gate_status: Mapped[str] = mapped_column(Text, nullable=False)
    rebuild_hash_replay_status: Mapped[str] = mapped_column(Text, nullable=False)
    dataset: Mapped[S2MaterializedDatasetModel] = relationship(back_populates="partitions")


@dataclass(frozen=True, slots=True)
class StoredUpstreamLaneA:
    source_cohort_id: str
    source_cohort_manifest_sha256: str
    raw_policy_version: str

    def lineage_identity_present(self) -> bool:
        return bool(
            self.source_cohort_id and self.source_cohort_manifest_sha256 and self.raw_policy_version
        )


@dataclass(frozen=True, slots=True)
class StoredUpstreamLaneB:
    cleaned_dataset_version_identity: str
    cleaning_policy_version: str
    correction_policy_version: str
    exclusion_policy_version: str
    rows: tuple[MaterializableRow, ...]

    def iter_materializable_rows(self) -> tuple[MaterializableRow, ...]:
        return self.rows

    def lineage_identity_present(self) -> bool:
        return bool(
            self.cleaned_dataset_version_identity
            and self.cleaning_policy_version
            and self.correction_policy_version
            and self.exclusion_policy_version
        )


@dataclass(frozen=True, slots=True)
class StoredUpstreamLaneC:
    visibility_policy_version: str
    revision_winner_policy_version: str

    def lineage_identity_present(self) -> bool:
        return bool(self.visibility_policy_version and self.revision_winner_policy_version)


@dataclass(frozen=True, slots=True)
class StoredUpstreamBundle:
    lane_a: StoredUpstreamLaneA
    lane_b: StoredUpstreamLaneB
    lane_c: StoredUpstreamLaneC


def _row_sort_key(row: MaterializableRow) -> tuple[str, str, str, str, str]:
    return (
        row.season,
        row.farm,
        row.subfarm,
        row.variety,
        row.harvest_business_date.isoformat(),
    )


def _upstream_snapshot_payload(upstream: UpstreamBundlePort) -> dict[str, object]:
    rows = upstream.lane_b.iter_materializable_rows()
    ordered_rows = sorted(rows, key=_row_sort_key)
    return {
        "cleaned_dataset_version_identity": upstream.lane_b.cleaned_dataset_version_identity,
        "cleaning_policy_version": upstream.lane_b.cleaning_policy_version,
        "correction_policy_version": upstream.lane_b.correction_policy_version,
        "exclusion_policy_version": upstream.lane_b.exclusion_policy_version,
        "materializable_rows": [
            {
                "actual_harvest_quantity_kg": row.actual_harvest_quantity_kg,
                "cleaned_row_identity": row.cleaned_row_identity,
                "farm": row.farm,
                "harvest_business_date": row.harvest_business_date,
                "pit_visibility_identity": row.pit_visibility_identity,
                "revision_winner_identity": row.revision_winner_identity,
                "season": row.season,
                "source_row_identity": row.source_row_identity,
                "subfarm": row.subfarm,
                "variety": row.variety,
            }
            for row in ordered_rows
        ],
        "raw_policy_version": upstream.lane_a.raw_policy_version,
        "revision_winner_policy_version": upstream.lane_c.revision_winner_policy_version,
        "source_cohort_id": upstream.lane_a.source_cohort_id,
        "source_cohort_manifest_sha256": upstream.lane_a.source_cohort_manifest_sha256,
        "visibility_policy_version": upstream.lane_c.visibility_policy_version,
    }


def compute_upstream_snapshot_sha256(upstream: UpstreamBundlePort) -> str:
    from backend.app.rolling_backtest.canonical import sha256_payload

    return sha256_payload(_upstream_snapshot_payload(upstream))


def _stored_upstream_from_bundle(upstream: UpstreamBundlePort) -> StoredUpstreamBundle:
    rows = tuple(sorted(upstream.lane_b.iter_materializable_rows(), key=_row_sort_key))
    return StoredUpstreamBundle(
        lane_a=StoredUpstreamLaneA(
            source_cohort_id=upstream.lane_a.source_cohort_id,
            source_cohort_manifest_sha256=upstream.lane_a.source_cohort_manifest_sha256,
            raw_policy_version=upstream.lane_a.raw_policy_version,
        ),
        lane_b=StoredUpstreamLaneB(
            cleaned_dataset_version_identity=upstream.lane_b.cleaned_dataset_version_identity,
            cleaning_policy_version=upstream.lane_b.cleaning_policy_version,
            correction_policy_version=upstream.lane_b.correction_policy_version,
            exclusion_policy_version=upstream.lane_b.exclusion_policy_version,
            rows=rows,
        ),
        lane_c=StoredUpstreamLaneC(
            visibility_policy_version=upstream.lane_c.visibility_policy_version,
            revision_winner_policy_version=upstream.lane_c.revision_winner_policy_version,
        ),
    )


def load_upstream_bundle_from_storage(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> tuple[S2MaterializedDatasetModel, StoredUpstreamBundle, BuildTimestamps]:
    dataset = session.scalar(
        select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == dataset_id,
            S2MaterializedDatasetModel.dataset_version == dataset_version,
        )
    )
    if dataset is None:
        raise MaterializedDatasetBuildError(
            f"materialized dataset not found: {dataset_id}/{dataset_version}"
        )
    rows = session.scalars(
        select(S2MaterializedMaterializableRowModel)
        .where(S2MaterializedMaterializableRowModel.materialized_dataset_id == dataset.id)
        .order_by(S2MaterializedMaterializableRowModel.row_sort_key)
    ).all()
    materializable_rows = tuple(
        MaterializableRow(
            season=row.season,
            farm=row.farm,
            subfarm=row.subfarm,
            variety=row.variety,
            harvest_business_date=row.harvest_business_date,
            actual_harvest_quantity_kg=row.actual_harvest_quantity_kg,
            source_row_identity=row.source_row_identity,
            cleaned_row_identity=row.cleaned_row_identity,
            pit_visibility_identity=row.pit_visibility_identity,
            revision_winner_identity=row.revision_winner_identity,
        )
        for row in rows
    )
    bundle = StoredUpstreamBundle(
        lane_a=StoredUpstreamLaneA(
            source_cohort_id=dataset.source_cohort_id,
            source_cohort_manifest_sha256=dataset.source_cohort_manifest_sha256,
            raw_policy_version=dataset.raw_policy_version,
        ),
        lane_b=StoredUpstreamLaneB(
            cleaned_dataset_version_identity=dataset.cleaned_dataset_version_identity,
            cleaning_policy_version=dataset.cleaning_policy_version,
            correction_policy_version=dataset.correction_policy_version,
            exclusion_policy_version=dataset.exclusion_policy_version,
            rows=materializable_rows,
        ),
        lane_c=StoredUpstreamLaneC(
            visibility_policy_version=dataset.visibility_policy_version,
            revision_winner_policy_version=dataset.revision_winner_policy_version,
        ),
    )
    timestamps = BuildTimestamps(
        started_at=dataset.build_started_at,
        completed_at=dataset.build_completed_at,
    )
    return dataset, bundle, timestamps


def _partition_manifest_from_model(
    dataset_row: S2MaterializedDatasetModel,
    partition_row: S2MaterializedPartitionModel,
) -> PartitionManifest:
    return PartitionManifest(
        dataset_id=dataset_row.dataset_id,
        dataset_version=dataset_row.dataset_version,
        partition_name=PartitionName(partition_row.partition_name),
        source_cohort_id=dataset_row.source_cohort_id,
        source_cohort_manifest_sha256=dataset_row.source_cohort_manifest_sha256,
        target_decision=partition_row.target_decision,
        canonical_grain=partition_row.canonical_grain,
        partition_date_field=PARTITION_DATE_FIELD,
        partition_start_date=partition_row.partition_start_date,
        partition_end_date=partition_row.partition_end_date,
        raw_policy_version=dataset_row.raw_policy_version,
        cleaning_policy_version=dataset_row.cleaning_policy_version,
        correction_policy_version=dataset_row.correction_policy_version,
        exclusion_policy_version=dataset_row.exclusion_policy_version,
        visibility_policy_version=dataset_row.visibility_policy_version,
        revision_winner_policy_version=dataset_row.revision_winner_policy_version,
        split_policy_version=partition_row.split_policy_version,
        builder_version=dataset_row.builder_version,
        dataset_schema_version=dataset_row.dataset_schema_version,
        manifest_schema_version=partition_row.manifest_schema_version,
        materialized_partition_schema_version=partition_row.materialized_partition_schema_version,
        row_count=partition_row.row_count,
        byte_count=partition_row.byte_count,
        content_sha256=partition_row.content_sha256,
        partition_identity_sha256=partition_row.partition_identity_sha256,
        manifest_sha256=partition_row.manifest_sha256,
        build_started_at=dataset_row.build_started_at,
        build_completed_at=dataset_row.build_completed_at,
        lineage_complete=partition_row.lineage_complete,
        quality_gate_status=QualityGateStatus(partition_row.quality_gate_status),
        rebuild_hash_replay_status=RebuildHashReplayStatus(
            partition_row.rebuild_hash_replay_status
        ),
    )


def load_materialized_dataset_result(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> MaterializedDatasetResult:
    dataset_row = session.scalar(
        select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == dataset_id,
            S2MaterializedDatasetModel.dataset_version == dataset_version,
        )
    )
    if dataset_row is None:
        raise MaterializedDatasetBuildError(
            f"materialized dataset not found: {dataset_id}/{dataset_version}"
        )
    partition_rows = session.scalars(
        select(S2MaterializedPartitionModel)
        .where(S2MaterializedPartitionModel.materialized_dataset_id == dataset_row.id)
        .order_by(S2MaterializedPartitionModel.partition_name)
    ).all()
    manifests = tuple(
        _partition_manifest_from_model(dataset_row, partition_row)
        for partition_row in partition_rows
    )
    return MaterializedDatasetResult(
        dataset_id=dataset_row.dataset_id,
        dataset_version=dataset_row.dataset_version,
        materialized_dataset_identity_sha256=dataset_row.materialized_dataset_identity_sha256,
        lineage_complete=dataset_row.lineage_complete,
        quality_gate_status=QualityGateStatus(dataset_row.quality_gate_status),
        partitions=manifests,
    )


def rebuild_materialized_dataset_from_storage(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> MaterializedDatasetResult:
    """Reload versioned upstream inputs from storage and rerun the D1 builder."""
    _dataset_row, upstream, timestamps = load_upstream_bundle_from_storage(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    return build_materialized_dataset(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        upstream=upstream,
        timestamps=timestamps,
    )


def verify_storage_rebuild_parity(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
) -> None:
    persisted = load_materialized_dataset_result(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    rebuilt = rebuild_materialized_dataset_from_storage(
        session,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
    )
    if (
        rebuilt.materialized_dataset_identity_sha256
        != persisted.materialized_dataset_identity_sha256
    ):
        raise MaterializedDatasetStorageRebuildError(
            "dataset identity mismatch after storage rebuild"
        )
    persisted_by_name = {manifest.partition_name: manifest for manifest in persisted.partitions}
    for rebuilt_manifest in rebuilt.partitions:
        stored_manifest = persisted_by_name[rebuilt_manifest.partition_name]
        if rebuilt_manifest.content_sha256 != stored_manifest.content_sha256:
            raise MaterializedDatasetStorageRebuildError(
                f"content_sha256 mismatch for {rebuilt_manifest.partition_name.value}"
            )
        if rebuilt_manifest.manifest_sha256 != stored_manifest.manifest_sha256:
            raise MaterializedDatasetStorageRebuildError(
                f"manifest_sha256 mismatch for {rebuilt_manifest.partition_name.value}"
            )
        if (
            recompute_manifest_sha256_from_published(stored_manifest)
            != stored_manifest.manifest_sha256
        ):
            raise MaterializedDatasetStorageRebuildError(
                f"stored manifest hash mismatch for {rebuilt_manifest.partition_name.value}"
            )


def persist_materialized_dataset(
    session: Session,
    *,
    dataset_id: str,
    dataset_version: str,
    upstream: UpstreamBundlePort,
    timestamps: BuildTimestamps | None = None,
) -> MaterializedDatasetResult:
    built = build_materialized_dataset(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        upstream=upstream,
        timestamps=timestamps,
    )
    snapshot_sha256 = compute_upstream_snapshot_sha256(upstream)
    existing = session.scalar(
        select(S2MaterializedDatasetModel).where(
            S2MaterializedDatasetModel.dataset_id == dataset_id,
            S2MaterializedDatasetModel.dataset_version == dataset_version,
        )
    )
    if existing is not None:
        if (
            existing.materialized_dataset_identity_sha256
            == built.materialized_dataset_identity_sha256
        ):
            return load_materialized_dataset_result(
                session,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
            )
        raise MaterializedDatasetConflictError(
            "dataset_id/version conflict: identity hash differs from persisted facts"
        )

    started = (
        timestamps.started_at if timestamps is not None else built.partitions[0].build_started_at
    )
    completed = (
        timestamps.completed_at
        if timestamps is not None
        else built.partitions[0].build_completed_at
    )
    stored_upstream = _stored_upstream_from_bundle(upstream)
    dataset_row = S2MaterializedDatasetModel(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        materialized_dataset_identity_sha256=built.materialized_dataset_identity_sha256,
        source_cohort_id=stored_upstream.lane_a.source_cohort_id,
        source_cohort_manifest_sha256=stored_upstream.lane_a.source_cohort_manifest_sha256,
        raw_policy_version=stored_upstream.lane_a.raw_policy_version,
        cleaning_policy_version=stored_upstream.lane_b.cleaning_policy_version,
        correction_policy_version=stored_upstream.lane_b.correction_policy_version,
        exclusion_policy_version=stored_upstream.lane_b.exclusion_policy_version,
        visibility_policy_version=stored_upstream.lane_c.visibility_policy_version,
        revision_winner_policy_version=stored_upstream.lane_c.revision_winner_policy_version,
        cleaned_dataset_version_identity=stored_upstream.lane_b.cleaned_dataset_version_identity,
        builder_version=BUILDER_VERSION,
        dataset_schema_version=DATASET_SCHEMA_VERSION,
        lineage_complete=built.lineage_complete,
        quality_gate_status=built.quality_gate_status.value,
        build_started_at=started,
        build_completed_at=completed,
        upstream_snapshot_sha256=snapshot_sha256,
    )
    session.add(dataset_row)
    session.flush()

    for sort_key, row in enumerate(stored_upstream.lane_b.rows):
        session.add(
            S2MaterializedMaterializableRowModel(
                materialized_dataset_id=dataset_row.id,
                row_sort_key=sort_key,
                season=row.season,
                farm=row.farm,
                subfarm=row.subfarm,
                variety=row.variety,
                harvest_business_date=row.harvest_business_date,
                actual_harvest_quantity_kg=row.actual_harvest_quantity_kg,
                source_row_identity=row.source_row_identity,
                cleaned_row_identity=row.cleaned_row_identity,
                pit_visibility_identity=row.pit_visibility_identity,
                revision_winner_identity=row.revision_winner_identity,
            )
        )

    manifest_by_name = {manifest.partition_name: manifest for manifest in built.partitions}
    for partition_spec in FROZEN_PARTITIONS:
        manifest = manifest_by_name[partition_spec.name]
        partition_bytes = materialize_partition_bytes(
            partition=partition_spec,
            upstream_rows=stored_upstream.lane_b.rows,
        )
        if partition_bytes.content_sha256 != manifest.content_sha256:
            raise MaterializedDatasetConflictError(
                f"partition bytes/hash mismatch for {manifest.partition_name.value}: "
                "content_sha256 differs from built manifest"
            )
        if len(partition_bytes.content_bytes) != manifest.byte_count:
            raise MaterializedDatasetConflictError(
                f"partition bytes/hash mismatch for {manifest.partition_name.value}: "
                "byte_count differs from built manifest"
            )
        if partition_bytes.row_count != manifest.row_count:
            raise MaterializedDatasetConflictError(
                f"partition bytes/hash mismatch for {manifest.partition_name.value}: "
                "row_count differs from built manifest"
            )
        session.add(
            S2MaterializedPartitionModel(
                materialized_dataset_id=dataset_row.id,
                partition_name=manifest.partition_name.value,
                partition_start_date=manifest.partition_start_date,
                partition_end_date=manifest.partition_end_date,
                partition_date_field=manifest.partition_date_field,
                target_decision=manifest.target_decision,
                canonical_grain=manifest.canonical_grain,
                split_policy_version=manifest.split_policy_version,
                manifest_schema_version=manifest.manifest_schema_version,
                materialized_partition_schema_version=manifest.materialized_partition_schema_version,
                row_count=manifest.row_count,
                byte_count=manifest.byte_count,
                content_sha256=manifest.content_sha256,
                partition_identity_sha256=manifest.partition_identity_sha256,
                manifest_sha256=manifest.manifest_sha256,
                content_bytes=partition_bytes.content_bytes,
                lineage_complete=manifest.lineage_complete,
                quality_gate_status=manifest.quality_gate_status.value,
                rebuild_hash_replay_status=manifest.rebuild_hash_replay_status.value,
            )
        )

    session.flush()
    return built


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


def partition_row_counts_for_e5_report(
    rows: tuple[MaterializableRow, ...],
) -> tuple[int, int, int]:
    """Return persisted TRAIN/VALIDATION row counts; TEST is always synthetic zero."""
    train = validation = 0
    for partition in FROZEN_PARTITIONS:
        if partition.name is PartitionName.TEST:
            continue
        selected = rows_for_partition(rows, partition)
        if partition.name is PartitionName.TRAIN:
            train = len(selected)
        elif partition.name is PartitionName.VALIDATION:
            validation = len(selected)
    return train, validation, 0


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
            e2=0,
            e3_grains=0,
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
    train_rows, val_rows, test_rows = partition_row_counts_for_e5_report(upstream.lane_b.rows)

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
